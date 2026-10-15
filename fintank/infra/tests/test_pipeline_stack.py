import json
from pathlib import Path

import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Template

from pipeline_stack import ASL_DIR, PipelineStack, asl_placeholders

ENV = cdk.Environment(account="123456789012", region="us-east-1")


def synth(**kwargs):
    app = cdk.App()
    stack = PipelineStack(app, "Test", env=ENV, alert_email="ops@example.com", **kwargs)
    return stack, Template.from_stack(stack)


@pytest.fixture(scope="module")
def built():
    return synth()


def test_no_nat_gateway(built):
    built[1].resource_count_is("AWS::EC2::NatGateway", 0)


def test_task_security_group_has_no_inbound_rules(built):
    template = built[1]
    template.resource_count_is("AWS::EC2::SecurityGroupIngress", 0)
    for sg in template.find_resources("AWS::EC2::SecurityGroup").values():
        assert "SecurityGroupIngress" not in sg["Properties"]


def test_run_task_size(built):
    built[1].has_resource_properties("AWS::ECS::TaskDefinition", {
        "Family": "fintank-run", "Cpu": "4096", "Memory": "16384",
        "EphemeralStorage": {"SizeInGiB": 150}})


def test_state_bucket_locked_down(built):
    built[1].has_resource_properties("AWS::S3::Bucket", {
        "VersioningConfiguration": {"Status": "Enabled"},
        "PublicAccessBlockConfiguration": {
            "BlockPublicAcls": True, "BlockPublicPolicy": True,
            "IgnorePublicAcls": True, "RestrictPublicBuckets": True}})


def test_schedules_off_by_default_and_on_by_context():
    _, template = synth()
    schedules = template.find_resources("AWS::Scheduler::Schedule").values()
    assert sorted(s["Properties"]["State"] for s in schedules) == ["DISABLED", "DISABLED"]
    _, template = synth(weekly_schedule=True, news_schedule=True)
    schedules = template.find_resources("AWS::Scheduler::Schedule").values()
    assert {s["Properties"]["ScheduleExpression"]: s["Properties"]["State"]
            for s in schedules} == {"cron(0 10 ? * SAT *)": "ENABLED",
                                    "cron(30 9 * * ? *)": "ENABLED"}


def role_of(template, family):
    for td in template.find_resources("AWS::ECS::TaskDefinition").values():
        if td["Properties"]["Family"] == family:
            return td["Properties"]["TaskRoleArn"]["Fn::GetAtt"][0]
    raise AssertionError(family)


def roles_writing_live_bucket(template):
    writers = set()
    for policy in template.find_resources("AWS::IAM::Policy").values():
        for statement in policy["Properties"]["PolicyDocument"]["Statement"]:
            actions = statement["Action"]
            actions = [actions] if isinstance(actions, str) else actions
            if (any(a.startswith(("s3:Put", "s3:DeleteObject", "s3:Abort")) for a in actions)
                    and "thetradingfloor" in json.dumps(statement["Resource"])):
                writers |= {r["Ref"] for r in policy["Properties"]["Roles"]}
    return writers


def test_only_publish_and_news_can_write_the_live_bucket(built):
    template = built[1]
    writers = roles_writing_live_bucket(template)
    assert role_of(template, "fintank-run") not in writers
    assert role_of(template, "fintank-publish") in writers
    assert role_of(template, "fintank-news") in writers


def test_alerts_go_to_the_email(built):
    built[1].has_resource_properties("AWS::SNS::Subscription", {
        "Protocol": "email", "Endpoint": "ops@example.com"})


@pytest.mark.parametrize("name", ["weekly.asl.json", "news.asl.json"])
def test_asl_placeholders_are_all_substituted(built, name):
    stack, _ = built
    assert asl_placeholders(ASL_DIR / name) == set(stack.substitutions[name])


@pytest.mark.parametrize("name", ["weekly.asl.json", "news.asl.json"])
def test_asl_is_valid_jsonata_json_after_substitution(name):
    text = (ASL_DIR / name).read_text()
    for key in asl_placeholders(ASL_DIR / name):
        value = {"SubnetIds": '["subnet-1"]', "NotifyStart": "true"}.get(key, "x")
        text = text.replace("${" + key + "}", value)
    definition = json.loads(text)
    assert definition["QueryLanguage"] == "JSONata"
    states = definition["States"]
    for state in states.values():
        for target in [state.get("Next"), state.get("Default")] + [
                c["Next"] for c in state.get("Choices", []) + state.get("Catch", [])]:
            assert target is None or target in states, target
