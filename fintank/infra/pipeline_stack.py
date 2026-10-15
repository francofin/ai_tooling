"""Fintank pipeline infrastructure. Design and setup instructions:
docs/superpowers/specs/2026-10-14-automated-data-pipeline-design.md"""
from __future__ import annotations

import json
import re
from pathlib import Path

from aws_cdk import (CfnOutput, Duration, RemovalPolicy, Stack)
from aws_cdk import aws_cloudwatch as cw
from aws_cdk import aws_cloudwatch_actions as cw_actions
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecr_assets as ecr_assets
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_scheduler as scheduler
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as subs
from aws_cdk import aws_sqs as sqs
from aws_cdk import aws_ssm as ssm
from aws_cdk import aws_stepfunctions as sfn
from constructs import Construct

HERE = Path(__file__).resolve().parent
IMAGE_DIR = HERE.parent / "backend" / "pipelines"
ASL_DIR = HERE / "statemachines"
LIVE_BUCKET = "thetradingfloor"
WEEKLY_NAME = "fintank-weekly-data-run"
NEWS_NAME = "fintank-daily-news"
CONTAINER = "app"                       # the ASL container overrides use this name
WEEKLY_CRON = "cron(0 10 ? * SAT *)"
NEWS_CRON = "cron(30 9 * * ? *)"
LOG_GROUP = "/fintank/pipeline"


def asl_placeholders(path) -> set[str]:
    return set(re.findall(r"\$\{(\w+)\}", Path(path).read_text()))


class PipelineStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, *, alert_email: str,
                 always_hold: bool = True, news_notify: str = "all",
                 weekly_schedule: bool = False, news_schedule: bool = False,
                 s3_endpoint: bool = True, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── Network: default VPC, public subnets, no NAT gateway (~$32/month saved).
        vpc = ec2.Vpc.from_lookup(self, "DefaultVpc", is_default=True)
        if s3_endpoint:
            vpc.add_gateway_endpoint("S3Endpoint",
                                     service=ec2.GatewayVpcEndpointAwsService.S3)
        task_sg = ec2.SecurityGroup(self, "TaskSg", vpc=vpc, allow_all_outbound=True,
                                    description="Fintank pipeline tasks: outbound only")
        subnet_ids = vpc.select_subnets(subnet_type=ec2.SubnetType.PUBLIC).subnet_ids

        # ── Storage.
        state_bucket = s3.Bucket(
            self, "StateBucket", bucket_name=f"fintank-pipeline-{self.account}",
            versioned=True, encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL, enforce_ssl=True,
            removal_policy=RemovalPolicy.RETAIN,
            lifecycle_rules=[
                s3.LifecycleRule(id="ExpireRuns", prefix="runs/",
                                 expiration=Duration.days(90)),
                s3.LifecycleRule(id="ExpireOldVersions",
                                 noncurrent_version_expiration=Duration.days(14)),
            ])
        live_bucket = s3.Bucket.from_bucket_name(self, "LiveBucket", LIVE_BUCKET)

        # ── Alerts.
        topic = sns.Topic(self, "Alerts", topic_name="fintank-pipeline-alerts")
        topic.add_subscription(subs.EmailSubscription(alert_email))

        # ── Containers.
        cluster = ecs.Cluster(self, "Cluster", vpc=vpc, cluster_name="fintank-pipeline")
        image = ecs.ContainerImage.from_asset(str(IMAGE_DIR),
                                              platform=ecr_assets.Platform.LINUX_AMD64)
        log_group = logs.LogGroup(self, "Logs", log_group_name=LOG_GROUP,
                                  retention=logs.RetentionDays.ONE_MONTH,
                                  removal_policy=RemovalPolicy.DESTROY)
        secrets = {
            name: ecs.Secret.from_ssm_parameter(
                ssm.StringParameter.from_secure_string_parameter_attributes(
                    self, f"Param{name}", parameter_name=f"/fintank/pipeline/{name}"))
            for name in ("FMP_API", "FRED_API", "SERPAPI_KEY")
        }
        environment = {
            "PIPELINE_DATA_ROOT": "/data",
            "STATE_BUCKET": state_bucket.bucket_name,
            "LIVE_BUCKET": LIVE_BUCKET,
            "SNS_TOPIC_ARN": topic.topic_arn,
            "ALWAYS_HOLD": "true" if always_hold else "false",
            "NEWS_NOTIFY": news_notify,
        }

        def task_definition(name, cpu, memory, disk, secret_names):
            td = ecs.FargateTaskDefinition(
                self, f"{name.title()}Task", family=f"fintank-{name}",
                cpu=cpu, memory_limit_mib=memory, ephemeral_storage_gib=disk,
                runtime_platform=ecs.RuntimePlatform(
                    cpu_architecture=ecs.CpuArchitecture.X86_64,
                    operating_system_family=ecs.OperatingSystemFamily.LINUX))
            td.add_container(CONTAINER, image=image, environment=environment,
                             secrets={k: secrets[k] for k in secret_names},
                             logging=ecs.LogDriver.aws_logs(stream_prefix=name,
                                                            log_group=log_group))
            return td

        run_td = task_definition("run", 4096, 16384, 150, ("FMP_API", "FRED_API"))
        publish_td = task_definition("publish", 512, 1024, None, ())
        news_td = task_definition("news", 512, 1024, None, ("FMP_API", "SERPAPI_KEY"))

        # Least privilege: only publish and news can write the live bucket.
        state_bucket.grant_read_write(run_td.task_role)
        topic.grant_publish(run_td.task_role)

        state_bucket.grant_read_write(publish_td.task_role)
        live_bucket.grant_read_write(publish_td.task_role)
        publish_td.task_role.add_to_principal_policy(iam.PolicyStatement(
            actions=["s3:GetBucketVersioning", "s3:GetObjectVersion"],
            resources=[live_bucket.bucket_arn, live_bucket.arn_for_objects("*")]))
        topic.grant_publish(publish_td.task_role)

        live_bucket.grant_put(news_td.task_role, "news_json_articles/*")
        state_bucket.grant_read_write(news_td.task_role, "runs/*")
        topic.grant_publish(news_td.task_role)

        # ── Step Functions.
        sm_role = iam.Role(self, "StateMachineRole",
                           assumed_by=iam.ServicePrincipal("states.amazonaws.com"))
        for td in (run_td, publish_td, news_td):
            sm_role.add_to_policy(iam.PolicyStatement(
                actions=["ecs:RunTask"], resources=[td.task_definition_arn]))
            sm_role.add_to_policy(iam.PolicyStatement(
                actions=["iam:PassRole"],
                resources=[td.task_role.role_arn, td.obtain_execution_role().role_arn]))
        sm_role.add_to_policy(iam.PolicyStatement(
            actions=["ecs:StopTask", "ecs:DescribeTasks"], resources=["*"]))
        sm_role.add_to_policy(iam.PolicyStatement(
            actions=["events:PutTargets", "events:PutRule", "events:DescribeRule"],
            resources=[f"arn:aws:events:{self.region}:{self.account}:rule/"
                       "StepFunctionsGetEventsForECSTaskRule"]))
        sm_role.add_to_policy(iam.PolicyStatement(
            actions=["states:ListExecutions"],
            resources=[f"arn:aws:states:{self.region}:{self.account}:stateMachine:{n}"
                       for n in (WEEKLY_NAME, NEWS_NAME)]))
        topic.grant_publish(sm_role)
        state_bucket.grant_read_write(sm_role, "runs/*")

        common = {
            "ClusterArn": cluster.cluster_arn,
            "SubnetIds": json.dumps(subnet_ids),
            "SecurityGroupId": task_sg.security_group_id,
            "TopicArn": topic.topic_arn,
        }
        self.substitutions = {
            "weekly.asl.json": {**common, "StateBucket": state_bucket.bucket_name,
                                "RunTaskDefinitionArn": run_td.task_definition_arn,
                                "PublishTaskDefinitionArn": publish_td.task_definition_arn},
            "news.asl.json": {**common, "NewsTaskDefinitionArn": news_td.task_definition_arn,
                              "NotifyStart": "true" if news_notify == "all" else "false"},
        }
        weekly = sfn.StateMachine(
            self, "Weekly", state_machine_name=WEEKLY_NAME, role=sm_role,
            definition_body=sfn.DefinitionBody.from_file(str(ASL_DIR / "weekly.asl.json")),
            definition_substitutions=self.substitutions["weekly.asl.json"])
        news = sfn.StateMachine(
            self, "News", state_machine_name=NEWS_NAME, role=sm_role,
            definition_body=sfn.DefinitionBody.from_file(str(ASL_DIR / "news.asl.json")),
            definition_substitutions=self.substitutions["news.asl.json"])

        # ── Schedules, with a dead-letter queue for runs that never start.
        dlq = sqs.Queue(self, "SchedulerDlq", queue_name="fintank-pipeline-scheduler-dlq",
                        retention_period=Duration.days(14), enforce_ssl=True)
        scheduler_role = iam.Role(self, "SchedulerRole",
                                  assumed_by=iam.ServicePrincipal("scheduler.amazonaws.com"))
        weekly.grant_start_execution(scheduler_role)
        news.grant_start_execution(scheduler_role)
        dlq.grant_send_messages(scheduler_role)
        for cid, name, cron, machine, enabled in (
                ("WeeklySchedule", WEEKLY_NAME, WEEKLY_CRON, weekly, weekly_schedule),
                ("NewsSchedule", NEWS_NAME, NEWS_CRON, news, news_schedule)):
            scheduler.CfnSchedule(
                self, cid, name=name, state="ENABLED" if enabled else "DISABLED",
                schedule_expression=cron, schedule_expression_timezone="UTC",
                flexible_time_window=scheduler.CfnSchedule.FlexibleTimeWindowProperty(mode="OFF"),
                target=scheduler.CfnSchedule.TargetProperty(
                    arn=machine.state_machine_arn, role_arn=scheduler_role.role_arn,
                    input="{}",
                    dead_letter_config=scheduler.CfnSchedule.DeadLetterConfigProperty(
                        arn=dlq.queue_arn),
                    retry_policy=scheduler.CfnSchedule.RetryPolicyProperty(
                        maximum_retry_attempts=3, maximum_event_age_in_seconds=3600)))

        never_started = cw.Alarm(
            self, "ScheduleNeverStarted",
            alarm_description="A Fintank pipeline schedule failed to start its run",
            metric=dlq.metric_approximate_number_of_messages_visible(
                period=Duration.minutes(5)),
            threshold=0, evaluation_periods=1,
            comparison_operator=cw.ComparisonOperator.GREATER_THAN_THRESHOLD,
            treat_missing_data=cw.TreatMissingData.NOT_BREACHING)
        never_started.add_alarm_action(cw_actions.SnsAction(topic))

        # Timeouts and aborts skip the state machines' own failure email.
        events.Rule(
            self, "ExecutionTimedOutOrAborted",
            event_pattern=events.EventPattern(
                source=["aws.states"],
                detail_type=["Step Functions Execution Status Change"],
                detail={"status": ["TIMED_OUT", "ABORTED"],
                        "stateMachineArn": [weekly.state_machine_arn,
                                            news.state_machine_arn]}),
            targets=[targets.SnsTopic(topic, message=events.RuleTargetInput.from_text(
                f"Fintank pipeline execution {events.EventField.from_path('$.detail.name')} "
                f"ended {events.EventField.from_path('$.detail.status')}: "
                f"{events.EventField.from_path('$.detail.executionArn')}"))])

        CfnOutput(self, "StateBucketName", value=state_bucket.bucket_name)
        CfnOutput(self, "WeeklyStateMachine", value=weekly.state_machine_arn)
        CfnOutput(self, "NewsStateMachine", value=news.state_machine_arn)
