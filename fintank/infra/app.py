#!/usr/bin/env python3
"""cdk deploy --profile fintank -c alert_email=you@example.com [-c …]

Context flags (all optional except alert_email):
  always_hold=true|false        hold every weekly run for approval (go-live guard)
  news_notify=all|warnings_only email for every news run, or only problems
  weekly_schedule=on|off        enable the Saturday schedule
  news_schedule=on|off          enable the daily news schedule
  s3_endpoint=on|off            off if the default VPC already has an S3 endpoint
"""
import os

import aws_cdk as cdk

from pipeline_stack import PipelineStack

app = cdk.App()
ctx = app.node.try_get_context
alert_email = ctx("alert_email")
if not alert_email:
    raise SystemExit("pass -c alert_email=you@example.com")

PipelineStack(
    app, "FintankPipeline",
    env=cdk.Environment(account=os.environ["CDK_DEFAULT_ACCOUNT"], region="us-east-1"),
    alert_email=alert_email,
    always_hold=str(ctx("always_hold")).lower() != "false",
    news_notify=ctx("news_notify") or "all",
    weekly_schedule=ctx("weekly_schedule") == "on",
    news_schedule=ctx("news_schedule") == "on",
    s3_endpoint=ctx("s3_endpoint") != "off",
)
app.synth()
