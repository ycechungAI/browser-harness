"""Shared safety and provenance checks for browser-harness videos."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


ROUTE_UNSAFE = re.compile(
    r"@|[?#]|://|onmicrosoft|(?:tenant|user|object)[_-]?id|"
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
OPAQUE_HEX = re.compile(r"^#[0-9a-f]{6}$", re.IGNORECASE)
COMPOSITION_PREFIX = "window.COMPOSITION ="
SOURCE_MANIFEST = "video-source.json"


class VideoPolicyError(ValueError):
    """A generated video artifact is unsafe, stale, or malformed."""


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VideoPolicyError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise VideoPolicyError(f"{path} must contain a JSON object")
    return value


def load_composition(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise VideoPolicyError(f"cannot read {path}: {exc}") from exc
    if not text.startswith(COMPOSITION_PREFIX) or not text.endswith(";"):
        raise VideoPolicyError(f"{path} is not a generated composition")
    try:
        value = json.loads(text[len(COMPOSITION_PREFIX) : -1].strip())
    except json.JSONDecodeError as exc:
        raise VideoPolicyError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise VideoPolicyError(f"{path} must set a JSON object")
    return value


def used_frames(composition: dict[str, Any]) -> list[str]:
    ordered: list[str] = []
    for beat in composition.get("beats") or []:
        for key in ("frame", "after"):
            frame = beat.get(key)
            if frame and frame not in ordered:
                ordered.append(str(frame))
    return ordered


def source_files(recording: Path) -> list[Path]:
    required = [
        recording / "events.jsonl",
        recording / "meta.json",
        recording / "recording-summary.json",
    ]
    frames = sorted(path for path in recording.glob("*.jpg") if path.stem.isdigit())
    return [path for path in required if path.is_file()] + frames


def write_source_manifest(recording: Path) -> dict[str, Any]:
    meta_path = recording / "meta.json"
    meta = load_json(meta_path) if meta_path.is_file() else {}
    files = source_files(recording)
    manifest = {
        "recording": recording.name,
        "started": meta.get("started"),
        "explicit": meta_path.is_file() and meta.get("auto") is not True,
        "files": {path.name: file_hash(path) for path in files},
    }
    (recording / SOURCE_MANIFEST).write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def verify_source_manifest(recording: Path) -> dict[str, Any]:
    manifest = load_json(recording / SOURCE_MANIFEST)
    if manifest.get("recording") != recording.name:
        raise VideoPolicyError("recording directory does not match video-source.json")
    expected = manifest.get("files")
    if not isinstance(expected, dict):
        raise VideoPolicyError("video-source.json has no source hashes")
    actual_paths = source_files(recording)
    actual_names = {path.name for path in actual_paths}
    if actual_names != set(expected):
        raise VideoPolicyError("recording source files changed after initialization")
    for path in actual_paths:
        if expected.get(path.name) != file_hash(path):
            raise VideoPolicyError(
                f"recording source changed after initialization: {path.name}"
            )
    return manifest
