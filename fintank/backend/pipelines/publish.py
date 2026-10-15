"""Diff → stage → publish → rollback.

The live bucket is only ever written by publish(), by server-side copies of
files a run staged in the state bucket — so an approval days later needs no
local data. Which files changed is decided against state/live-manifest.json
({key: sha256}), which publish() and rollback() keep current (plan ruling R1).
Every published object also carries its sha256 as x-amz-meta-sha256."""
from __future__ import annotations

import hashlib
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from botocore.exceptions import ClientError

from pipelines.outputs import DATASET_ORDER
from pipelines.report import now_iso
from pipelines.store import LAST_PUBLISHED_REPORT, LIVE_MANIFEST, S3Store, run_key


def sha256_file(path: str, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def diff_outputs(outputs, live_manifest: dict, workers: int = 8) -> list[dict]:
    """Outputs whose content differs from what live holds, in input order."""
    with ThreadPoolExecutor(workers) as pool:
        hashes = list(pool.map(lambda o: sha256_file(o.local_path), outputs))
    return [{"key": o.key, "local_path": o.local_path, "dataset": o.dataset, "sha256": h}
            for o, h in zip(outputs, hashes) if live_manifest.get(o.key) != h]


def stage_changed(client, state_bucket, run_id, changed, workers=32, log=print) -> None:
    def upload(entry):
        client.upload_file(entry["local_path"], state_bucket,
                           run_key(run_id, f"stage/{entry['key']}"))

    with ThreadPoolExecutor(workers) as pool:
        list(pool.map(upload, changed))
    ordered = sorted(changed, key=lambda e: DATASET_ORDER.index(e["dataset"]))
    S3Store(state_bucket, client).put_json(run_key(run_id, "stage-manifest.json"), {
        "run_id": run_id,
        "files": [{k: e[k] for k in ("key", "sha256", "dataset")} for e in ordered],
    })
    log(f"staged {len(changed)} changed files for {run_id}")


def _current_version(client, bucket, key):
    try:
        return client.head_object(Bucket=bucket, Key=key).get("VersionId")
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
            return None
        raise


def publish(client, state_bucket, live_bucket, run_id, workers=32, log=print) -> dict:
    versioning = client.get_bucket_versioning(Bucket=live_bucket).get("Status")
    if versioning != "Enabled":
        raise RuntimeError(f"s3://{live_bucket} versioning is {versioning or 'off'} — "
                           "enable it first (setup step 3), or rollback is impossible")
    store = S3Store(state_bucket, client)
    staged = store.get_json(run_key(run_id, "stage-manifest.json"))
    if staged is None:
        raise RuntimeError(f"nothing staged for {run_id}")
    live = store.get_json(LIVE_MANIFEST, {})
    published = []

    def copy(entry):
        previous = _current_version(client, live_bucket, entry["key"])
        response = client.copy_object(
            Bucket=live_bucket, Key=entry["key"],
            CopySource={"Bucket": state_bucket,
                        "Key": run_key(run_id, f"stage/{entry['key']}")},
            Metadata={"sha256": entry["sha256"]}, MetadataDirective="REPLACE")
        return {"key": entry["key"], "dataset": entry["dataset"],
                "sha256": entry["sha256"], "previous_sha256": live.get(entry["key"]),
                "previous_version": previous, "new_version": response.get("VersionId")}

    for dataset in DATASET_ORDER:
        group = [f for f in staged["files"] if f["dataset"] == dataset]
        if not group:
            continue
        with ThreadPoolExecutor(workers) as pool:
            done = list(pool.map(copy, group))
        published += done
        for entry in done:
            live[entry["key"]] = entry["sha256"]
        # Checkpoint after each dataset so a crash mid-publish can still be rolled back.
        store.put_json(run_key(run_id, "publish-manifest.json"),
                       {"run_id": run_id, "published_at": now_iso(), "files": published})
        store.put_json(LIVE_MANIFEST, live)
        log(f"published {len(done)} {dataset} files")

    store.put_json(run_key(run_id, "publish-manifest.json"),
                   {"run_id": run_id, "published_at": now_iso(), "files": published})
    report = store.get_json(run_key(run_id, "report.json"))
    if report is not None:
        store.put_json(LAST_PUBLISHED_REPORT, report)
    by_dataset = Counter(e["dataset"] for e in published)
    return {"published": len(published),
            "by_dataset": {d: by_dataset[d] for d in DATASET_ORDER if by_dataset[d]}}


def rollback(client, state_bucket, live_bucket, run_id, log=print) -> int:
    store = S3Store(state_bucket, client)
    manifest = store.get_json(run_key(run_id, "publish-manifest.json"))
    if manifest is None:
        raise RuntimeError(f"{run_id} has no publish manifest — nothing to roll back")
    live = store.get_json(LIVE_MANIFEST, {})
    for entry in reversed(manifest["files"]):
        key = entry["key"]
        if entry["previous_version"]:
            client.copy_object(Bucket=live_bucket, Key=key, MetadataDirective="COPY",
                               CopySource={"Bucket": live_bucket, "Key": key,
                                           "VersionId": entry["previous_version"]})
            if entry["previous_sha256"]:
                live[key] = entry["previous_sha256"]
            else:
                live.pop(key, None)       # pre-manifest object: next run re-diffs it
        else:
            client.delete_object(Bucket=live_bucket, Key=key)
            live.pop(key, None)
    store.put_json(LIVE_MANIFEST, live)
    store.put_json(run_key(run_id, "rollback.json"),
                   {"rolled_back_at": now_iso(), "files": len(manifest["files"])})
    log(f"rolled back {len(manifest['files'])} files from {run_id}")
    return len(manifest["files"])
