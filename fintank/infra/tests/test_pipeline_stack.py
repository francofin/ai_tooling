import json
from pathlib import Path

import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Template

from pipeline_stack import ASL_DIR, PipelineStack, asl_placeholders

ASL_FILES = ["weekly.asl.json", "news.asl.json", "earnings.asl.json",
             "earnings-backfill.asl.json"]
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
    assert sorted(s["Properties"]["State"] for s in schedules) == ["DISABLED"] * 3
    _, template = synth(weekly_schedule=True, news_schedule=True)
    schedules = template.find_resources("AWS::Scheduler::Schedule").values()
    assert {s["Properties"]["ScheduleExpression"]: s["Properties"]["State"]
            for s in schedules} == {"cron(0 10 ? * SAT *)": "ENABLED",
                                    "cron(30 9 * * ? *)": "ENABLED",
                                    "cron(0 11 * * ? *)": "DISABLED"}
    _, template = synth(earnings_schedule=True)
    schedules = template.find_resources("AWS::Scheduler::Schedule").values()
    assert {s["Properties"]["ScheduleExpression"]: s["Properties"]["State"]
            for s in schedules}["cron(0 11 * * ? *)"] == "ENABLED"


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


def test_only_publish_news_and_earnings_can_write_the_live_bucket(built):
    template = built[1]
    writers = roles_writing_live_bucket(template)
    assert role_of(template, "fintank-run") not in writers
    assert role_of(template, "fintank-publish") in writers
    assert role_of(template, "fintank-news") in writers
    earnings = role_of(template, "fintank-earnings")
    assert earnings in writers
    live_puts = set()
    for actions, resources in statements_of(template, earnings):
        if any(a.startswith(("s3:Put", "s3:Delete", "s3:Abort")) for a in actions):
            live_puts |= {r for r in resources if "thetradingfloor" in r}
    assert live_puts == {"arn:aws:s3:::thetradingfloor/earnings_notes/*"}


def test_earnings_task_has_anthropic_secret_and_small_size(built):
    template = built[1]
    (td,) = [t["Properties"] for t in template.find_resources("AWS::ECS::TaskDefinition").values()
             if t["Properties"]["Family"] == "fintank-earnings"]
    assert (td["Cpu"], td["Memory"]) == ("512", "1024")
    assert "EphemeralStorage" not in td
    secrets = {s["Name"] for s in td["ContainerDefinitions"][0]["Secrets"]}
    assert secrets == {"FMP_API", "ANTHROPIC_API_KEY"}
    assert "/fintank/pipeline/ANTHROPIC_API_KEY" in json.dumps(template.to_json())


def test_earnings_role_can_delete_only_the_lock(built):
    template = built[1]
    state = f"<{logical_id(template, 'AWS::S3::Bucket')}>"
    deletes = []
    for actions, resources in statements_of(template, role_of(template, "fintank-earnings")):
        if any(a.startswith("s3:Delete") for a in actions):
            deletes.append((actions, resources))
    assert deletes == [(["s3:DeleteObject"], [f"{state}/earnings/lock.json"])]


def _asl(name):
    return json.loads((ASL_DIR / name).read_text().replace("${SubnetIds}", '["subnet-1"]'))


def _reachable(states, start, blocked):
    seen, todo = set(), [start]
    while todo:
        n = todo.pop()
        if n in seen or n in blocked or n is None:
            continue
        seen.add(n)
        s = states[n]
        todo += [s.get("Next"), s.get("Default")] + [
            c["Next"] for c in s.get("Choices", []) + s.get("Catch", [])]
    return seen


def test_backfill_machine_waits_for_approval_before_publish():
    d = _asl("earnings-backfill.asl.json")
    states = d["States"]
    assert "Publish" in _reachable(states, d["StartAt"], set())
    assert "Publish" not in _reachable(states, d["StartAt"], {"WaitForApproval"})
    wait = states["WaitForApproval"]
    assert wait["Resource"].endswith("putObject.waitForTaskToken")
    assert wait["TimeoutSeconds"] == 604800
    assert d["TimeoutSeconds"] == 777600 > wait["TimeoutSeconds"]
    cmd = states["Publish"]["Arguments"]["Overrides"]["ContainerOverrides"][0]["Command"]
    assert "'earnings-backfill', 'publish'" in cmd


def test_backfill_loop_has_26h_limit():
    d = _asl("earnings-backfill.asl.json")
    states = d["States"]
    assert states["WaitPoll"]["Seconds"] == 1800
    (choice,) = states["TooLong?"]["Choices"]
    assert "93600000" in choice["Condition"] and "$submitted_at" in choice["Condition"]
    assert choice["Next"] == "NotifyFailed"
    assert states["TooLong?"]["Default"] == "WaitPoll"


def test_alerts_go_to_the_email(built):
    built[1].has_resource_properties("AWS::SNS::Subscription", {
        "Protocol": "email", "Endpoint": "ops@example.com"})


@pytest.mark.parametrize("name", ASL_FILES)
def test_asl_placeholders_are_all_substituted(built, name):
    stack, _ = built
    assert asl_placeholders(ASL_DIR / name) == set(stack.substitutions[name])


@pytest.mark.parametrize("name", ASL_FILES)
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


def render(value):
    """A CloudFormation ARN expression as a readable string."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(render(v) for v in value)
    if "Fn::Join" in value:
        sep, parts = value["Fn::Join"]
        return sep.join(render(p) for p in parts)
    if "Fn::GetAtt" in value:
        return f"<{value['Fn::GetAtt'][0]}>"
    if "Ref" in value:
        return "aws" if value["Ref"] == "AWS::Partition" else f"<{value['Ref']}>"
    raise AssertionError(value)


def statements_of(template, role_logical_id):
    for policy in template.find_resources("AWS::IAM::Policy").values():
        if {"Ref": role_logical_id} in policy["Properties"]["Roles"]:
            for statement in policy["Properties"]["PolicyDocument"]["Statement"]:
                actions = statement["Action"]
                resources = statement["Resource"]
                yield ([actions] if isinstance(actions, str) else actions,
                       [render(r) for r in (resources if isinstance(resources, list)
                                            else [resources])])


def logical_id(template, resource_type):
    (lid,) = template.find_resources(resource_type).keys()
    return lid


def test_publish_role_cannot_delete_anything(built):
    template = built[1]
    for actions, resources in statements_of(template, role_of(template, "fintank-publish")):
        assert not [a for a in actions if a.startswith("s3:Delete")], (actions, resources)


def test_publish_role_writes_only_live_objects_and_run_bookkeeping(built):
    template = built[1]
    state = f"<{logical_id(template, 'AWS::S3::Bucket')}>"
    puts = set()
    for actions, resources in statements_of(template, role_of(template, "fintank-publish")):
        if any(a.startswith("s3:Put") for a in actions):
            puts |= set(resources)
    assert puts == {"arn:aws:s3:::thetradingfloor/*", f"{state}/runs/*",
                    f"{state}/state/live-manifest.json",
                    f"{state}/state/last-published-report.json"}


def test_publish_role_has_no_object_version_access(built):
    template = built[1]
    for actions, _ in statements_of(template, role_of(template, "fintank-publish")):
        assert "s3:GetObjectVersion" not in actions


def test_topic_policy_lets_events_and_cloudwatch_publish(built):
    template = built[1]
    principals = set()
    for policy in template.find_resources("AWS::SNS::TopicPolicy").values():
        for statement in policy["Properties"]["PolicyDocument"]["Statement"]:
            if "sns:Publish" in json.dumps(statement["Action"]):
                principals.add(statement["Principal"]["Service"])
    assert {"events.amazonaws.com", "cloudwatch.amazonaws.com"} <= principals


def test_runs_expire_after_45_days(built):
    rules = [r for b in built[1].find_resources("AWS::S3::Bucket").values()
             for r in b["Properties"]["LifecycleConfiguration"]["Rules"]]
    (runs,) = [r for r in rules if r.get("Prefix") == "runs/"]
    assert runs["ExpirationInDays"] == 45


@pytest.mark.parametrize("name,states", [
    ("weekly.asl.json", ["CheckBusy", "NotifyStarted"]),
    ("news.asl.json", ["NotifyStarted"]),
    ("earnings.asl.json", ["RunEarnings"]),
    ("earnings-backfill.asl.json", ["Submit", "ReadStatus", "CheckTask", "Stage",
                                    "ReadVerdict", "Publish", "DiscardedTask"]),
])
def test_early_states_report_failures(name, states):
    definition = json.loads((ASL_DIR / name).read_text().replace("${SubnetIds}", "[]"))
    for state in states:
        catch = definition["States"][state].get("Catch", [])
        assert [c["Next"] for c in catch if c["ErrorEquals"] == ["States.ALL"]] == \
            ["NotifyFailed"], state


def test_weekly_failure_email_explains_republish():
    text = (ASL_DIR / "weekly.asl.json").read_text()
    assert "python -m pipelines publish ' & $run_id" in text
    assert "python -m pipelines rollback ' & $run_id" in text


def test_app_validates_news_notify():
    from app import stack_options
    base = {"alert_email": "ops@example.com"}
    assert stack_options(base.get)["news_notify"] == "all"
    assert stack_options({**base, "news_notify": "warnings_only"}.get)["news_notify"] \
        == "warnings_only"
    with pytest.raises(SystemExit, match="news_notify"):
        stack_options({**base, "news_notify": "sometimes"}.get)
    with pytest.raises(SystemExit, match="alert_email"):
        stack_options({}.get)


def test_news_machine_passes_search_flag_from_input():
    definition = json.loads((ASL_DIR / "news.asl.json").read_text()
                            .replace("${SubnetIds}", '["subnet-1"]')
                            .replace("${NotifyStart}", "true"))
    states = definition["States"]
    assert "--search" in states["Init"]["Assign"]["search"]
    command = states["RunNews"]["Arguments"]["Overrides"]["ContainerOverrides"][0]["Command"]
    assert "$search" in command


def test_backfill_retries_only_the_idempotent_check():
    states = _asl("earnings-backfill.asl.json")["States"]
    assert states["CheckTask"]["Retry"] == [{"ErrorEquals": ["States.ALL"], "MaxAttempts": 2,
                                             "IntervalSeconds": 300, "BackoffRate": 1}]
    for name in ("Submit", "Stage", "Publish"):
        assert "Retry" not in states[name], name


def test_backfill_failure_email_explains_recovery():
    msg = _asl("earnings-backfill.asl.json")["States"]["NotifyFailed"]["Arguments"]["Message"]
    assert "paid Claude batch may still be in flight" in msg
    assert "stay blocked" in msg
    assert "earnings-backfill check|stage|discarded --run-id ' & $run_id" in msg


def test_backfill_nothing_to_do_email_reports_targets_and_tokens():
    states = _asl("earnings-backfill.asl.json")["States"]
    assign = states["ReadStatus"]["Assign"]
    assert assign["status_doc"] == "{% $parse($states.result.Body) %}"
    msg = states["NotifyNothingToDo"]["Arguments"]["Message"]
    assert "$string($status_doc.targets)" in msg
    assert "$string($status_doc.estimated_input_tokens)" in msg
    assert "Nothing was generated" in msg


def test_backfill_force_reaches_only_the_submit_task():
    states = _asl("earnings-backfill.asl.json")["States"]
    assert "'--force'" in states["Init"]["Assign"]["force"]
    commands = {name: s["Arguments"]["Overrides"]["ContainerOverrides"][0]["Command"]
                for name, s in states.items()
                if s.get("Resource", "").endswith("ecs:runTask.sync")}
    assert "$force" in commands.pop("Submit")
    assert not any("$force" in c for c in commands.values())
