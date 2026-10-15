"""Where run bookkeeping lives: the state bucket on AWS, a local folder for dry
runs. Both stores speak the same small interface, so the runner doesn't care."""
from __future__ import annotations

import json
import os
import shutil

import boto3
from botocore.exceptions import ClientError

REGION = "us-east-1"
LIVE_MANIFEST = "state/live-manifest.json"
LAST_PUBLISHED_REPORT = "state/last-published-report.json"


def run_key(run_id: str, name: str) -> str:
    return f"runs/{run_id}/{name}"


def aws_client(service: str):
    """The one place AWS clients are built — tests monkeypatch it."""
    return boto3.client(service, region_name=REGION)


def default_state_bucket(sts=None) -> str:
    """$STATE_BUCKET, else the CDK stack's fintank-pipeline-<account-id>."""
    if os.getenv("STATE_BUCKET"):
        return os.environ["STATE_BUCKET"]
    sts = sts or aws_client("sts")
    return f"fintank-pipeline-{sts.get_caller_identity()['Account']}"


def live_bucket() -> str:
    return os.getenv("LIVE_BUCKET", "thetradingfloor")


def _is_missing(error: ClientError) -> bool:
    return error.response.get("Error", {}).get("Code") in ("NoSuchKey", "404", "NotFound")


class LocalStore:
    def __init__(self, base_dir: str):
        self.base = base_dir

    def _path(self, key: str) -> str:
        return os.path.join(self.base, *key.split("/"))

    def get_json(self, key, default=None):
        try:
            with open(self._path(key)) as f:
                return json.load(f)
        except FileNotFoundError:
            return default

    def put_json(self, key, data):
        path = self._path(key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def put_file(self, key, local_path):
        path = self._path(key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        shutil.copyfile(local_path, path)

    def exists(self, key):
        return os.path.exists(self._path(key))

    def list_prefixes(self, prefix):
        folder = self._path(prefix.rstrip("/"))
        if not os.path.isdir(folder):
            return []
        return sorted(f"{prefix}{name}/" for name in os.listdir(folder)
                      if os.path.isdir(os.path.join(folder, name)))

    def url(self, key):
        return self._path(key)


class S3Store:
    def __init__(self, bucket: str, client=None):
        self.bucket = bucket
        self.client = client or aws_client("s3")

    def get_json(self, key, default=None):
        try:
            body = self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except ClientError as e:
            if _is_missing(e):
                return default
            raise
        return json.loads(body)

    def put_json(self, key, data):
        self.client.put_object(Bucket=self.bucket, Key=key,
                               Body=json.dumps(data, indent=2, default=str).encode(),
                               ContentType="application/json")

    def put_file(self, key, local_path):
        self.client.upload_file(local_path, self.bucket, key)

    def exists(self, key):
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as e:
            if _is_missing(e):
                return False
            raise

    def list_prefixes(self, prefix):
        paginator = self.client.get_paginator("list_objects_v2")
        prefixes = []
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix, Delimiter="/"):
            prefixes += [p["Prefix"] for p in page.get("CommonPrefixes", [])]
        return sorted(prefixes)

    def url(self, key):
        return (f"https://s3.console.aws.amazon.com/s3/object/{self.bucket}"
                f"?region={REGION}&prefix={key}")
