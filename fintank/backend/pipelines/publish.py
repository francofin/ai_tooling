"""Diff → stage → publish → rollback.

The live bucket is only ever written by publish(), by server-side copies of
files a run staged in the state bucket — so an approval days later needs no
local data. Which files changed is decided against state/live-manifest.json
({key: sha256}), which publish() and rollback() keep current (plan ruling R1).
Every published object also carries its sha256 as x-amz-meta-sha256."""
from __future__ import annotations

import datetime as dt
import hashlib
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

from botocore.exceptions import ClientError

from pipelines.outputs import DATASET_ORDER
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


def _current_version(client, bucket, key) -> tuple[bool, str | None]:
    """(existed, version id). An object written before versioning was enabled
    exists with no version id (S3 calls it the "null" version)."""
    try:
        version = client.head_object(Bucket=bucket, Key=key).get("VersionId")
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
            return False, None
        raise
    return True, (None if version in (None, "null") else version)


def _now_precise() -> str:
    # Microseconds: rollback orders runs by published_at, and two publishes
    # can land in the same second.
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds")


def publish(client, state_bucket, live_bucket, run_id, workers=32, log=print) -> dict:
    """Copy a run's staged files live. Safe to re-run after a failure: keys
    already live with the staged content are skipped, and the publish manifest
    keeps each key's EARLIEST previous version, so rollback still restores
    what was live before this run first touched it."""
    versioning = client.get_bucket_versioning(Bucket=live_bucket).get("Status")
    if versioning != "Enabled":
        raise RuntimeError(f"s3://{live_bucket} versioning is {versioning or 'off'} — "
                           "enable it first (setup step 3), or rollback is impossible")
    store = S3Store(state_bucket, client)
    staged = store.get_json(run_key(run_id, "stage-manifest.json"))
    if staged is None:
        raise RuntimeError(f"nothing staged for {run_id}")
    live = store.get_json(LIVE_MANIFEST, {})
    manifest_key = run_key(run_id, "publish-manifest.json")
    earlier = store.get_json(manifest_key) or {}
    record = {f["key"]: f for f in earlier.get("files", [])}   # insertion-ordered
    published = []

    def copy(entry):
        existed, previous = _current_version(client, live_bucket, entry["key"])
        response = client.copy_object(
            Bucket=live_bucket, Key=entry["key"],
            CopySource={"Bucket": state_bucket,
                        "Key": run_key(run_id, f"stage/{entry['key']}")},
            Metadata={"sha256": entry["sha256"]}, MetadataDirective="REPLACE")
        return {"key": entry["key"], "dataset": entry["dataset"],
                "sha256": entry["sha256"], "previous_sha256": live.get(entry["key"]),
                "previous_existed": existed, "previous_version": previous,
                "new_version": response.get("VersionId")}

    def note(done):
        prior = record.get(done["key"])
        if prior is not None:           # a re-publish: keep the original "before"
            for field in ("previous_sha256", "previous_version"):
                done[field] = prior.get(field)
            done["previous_existed"] = prior.get(
                "previous_existed", prior.get("previous_version") is not None)
        record[done["key"]] = done
        live[done["key"]] = done["sha256"]
        published.append(done)

    def checkpoint():
        store.put_json(manifest_key, {"run_id": run_id, "published_at": _now_precise(),
                                      "files": list(record.values())})
        store.put_json(LIVE_MANIFEST, live)

    for dataset in DATASET_ORDER:
        group = [f for f in staged["files"] if f["dataset"] == dataset
                 and live.get(f["key"]) != f["sha256"]]
        if not group:
            continue
        error = None
        with ThreadPoolExecutor(workers) as pool:
            for future in as_completed([pool.submit(copy, e) for e in group]):
                try:
                    note(future.result())
                except Exception as e:  # noqa: BLE001 — re-raised after the checkpoint
                    error = error or e
        # Checkpoint after each dataset — and before re-raising — so a crash
        # mid-publish loses no record of what was already copied.
        checkpoint()
        if error is not None:
            raise error
        log(f"published {len(group)} {dataset} files")

    checkpoint()
    report = store.get_json(run_key(run_id, "report.json"))
    if report is not None:
        store.put_json(LAST_PUBLISHED_REPORT, report)
    by_dataset = Counter(e["dataset"] for e in published)
    return {"published": len(published),
            "by_dataset": {d: by_dataset[d] for d in DATASET_ORDER if by_dataset[d]}}


def _parse_time(value):
    return dt.datetime.fromisoformat(value) if value else None


def newer_runs_touching(store, run_id, manifest) -> list[str]:
    """Runs published after `run_id` (and not since rolled back) that changed
    any of the same live keys — rolling `run_id` back under them would put
    stale versions live."""
    mine = _parse_time(manifest.get("published_at"))
    keys = {f["key"] for f in manifest["files"]}
    newer = []
    for prefix in store.list_prefixes("runs/"):
        other = prefix.split("/")[1]
        if other == run_id:
            continue
        theirs = store.get_json(run_key(other, "publish-manifest.json"))
        if not theirs or not keys & {f["key"] for f in theirs["files"]}:
            continue
        published_at = _parse_time(theirs.get("published_at"))
        if mine is not None and (published_at is None or published_at <= mine):
            continue
        undone = store.get_json(run_key(other, "rollback.json"))
        if undone and published_at and \
                _parse_time(undone.get("rolled_back_at")) >= published_at:
            continue
        newer.append(other)
    return sorted(newer)


def rollback(client, state_bucket, live_bucket, run_id, force=False, log=print) -> int:
    store = S3Store(state_bucket, client)
    manifest = store.get_json(run_key(run_id, "publish-manifest.json"))
    if manifest is None:
        raise RuntimeError(f"{run_id} has no publish manifest — nothing to roll back")
    if not force:
        newer = newer_runs_touching(store, run_id, manifest)
        if newer:
            raise RuntimeError(
                f"{', '.join(newer)} published after {run_id} and changed the same "
                f"files — roll back the latest run first, or pass --force to restore "
                f"{run_id}'s previous versions anyway")
    live = store.get_json(LIVE_MANIFEST, {})
    for entry in reversed(manifest["files"]):
        key = entry["key"]
        existed = entry.get("previous_existed", entry["previous_version"] is not None)
        if existed:
            client.copy_object(Bucket=live_bucket, Key=key, MetadataDirective="COPY",
                               CopySource={"Bucket": live_bucket, "Key": key,
                                           "VersionId": entry["previous_version"] or "null"})
            if entry["previous_sha256"]:
                live[key] = entry["previous_sha256"]
            else:
                live.pop(key, None)       # pre-manifest object: next run re-diffs it
        else:
            client.delete_object(Bucket=live_bucket, Key=key)
            live.pop(key, None)
    store.put_json(LIVE_MANIFEST, live)
    store.put_json(run_key(run_id, "rollback.json"),
                   {"rolled_back_at": _now_precise(), "files": len(manifest["files"])})
    log(f"rolled back {len(manifest['files'])} files from {run_id}")
    return len(manifest["files"])
