"""The pipeline's raw inputs live in the state bucket as one .tar.zst per
folder ("unit"): the merged FMP/FRED JSON, the index price parquets the index
fetcher self-detects from, the constituent lists and the revenue segments.

A run pulls every unit, then pushes back only the units a stage changed — so a
crashed run resumes from its last finished fetch stage. Built parquets are not
state: every run rebuilds them from the JSON."""
from __future__ import annotations

import os
import shutil
import tarfile
import tempfile

import zstandard as zstd

STATE_PREFIX = "state/"
SUFFIX = ".tar.zst"
# Split one level down so a prices-only change doesn't re-upload statements.
SPLIT_ROOTS = ("stock_data_json",)
WHOLE_UNITS = ("index_data", "stock_data/revenue_segments")


def state_units(root: str) -> list[str]:
    units = []
    for split in SPLIT_ROOTS:
        base = os.path.join(root, split)
        if os.path.isdir(base):
            units += [f"{split}/{name}" for name in sorted(os.listdir(base))
                      if os.path.isdir(os.path.join(base, name))]
    units += [u for u in WHOLE_UNITS if os.path.isdir(os.path.join(root, u))]
    return units


def archive_key(unit: str) -> str:
    return f"{STATE_PREFIX}{unit}{SUFFIX}"


def _changed_since(root: str, unit: str, since: float) -> bool:
    for dirpath, _, names in os.walk(os.path.join(root, unit)):
        for name in names:
            if os.path.getmtime(os.path.join(dirpath, name)) > since:
                return True
    return False


def _write_archive(root: str, unit: str, out_path: str) -> None:
    compressor = zstd.ZstdCompressor(level=3, threads=-1)
    with open(out_path, "wb") as fh, compressor.stream_writer(fh) as zw, \
            tarfile.open(fileobj=zw, mode="w|") as tar:
        tar.add(os.path.join(root, unit), arcname=unit)


def _extract_archive(path: str, root: str) -> None:
    with open(path, "rb") as fh, zstd.ZstdDecompressor().stream_reader(fh) as zr, \
            tarfile.open(fileobj=zr, mode="r|") as tar:
        tar.extractall(root, filter="data")


def push(client, bucket, root, units=None, since=None, log=print) -> list[str]:
    """Archive and upload units. With `since` (epoch seconds), only units
    holding a file modified after it."""
    units = state_units(root) if units is None else units
    pushed = []
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "unit" + SUFFIX)
        for unit in units:
            if since is not None and not _changed_since(root, unit, since):
                continue
            _write_archive(root, unit, out)
            size_mb = os.path.getsize(out) / 1e6
            client.upload_file(out, bucket, archive_key(unit))
            os.remove(out)
            pushed.append(unit)
            log(f"state: pushed {unit} ({size_mb:,.1f} MB)")
    return pushed


def pull(client, bucket, root, log=print) -> list[str]:
    """Download and unpack every unit, replacing each local unit folder."""
    paginator = client.get_paginator("list_objects_v2")
    keys = [obj["Key"]
            for page in paginator.paginate(Bucket=bucket, Prefix=STATE_PREFIX)
            for obj in page.get("Contents", [])
            if obj["Key"].endswith(SUFFIX)]
    restored = []
    os.makedirs(root, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        local = os.path.join(tmp, "unit" + SUFFIX)
        for key in sorted(keys):
            unit = key[len(STATE_PREFIX):-len(SUFFIX)]
            client.download_file(bucket, key, local)
            shutil.rmtree(os.path.join(root, unit), ignore_errors=True)
            _extract_archive(local, root)
            os.remove(local)
            restored.append(unit)
            log(f"state: pulled {unit}")
    return restored
