#!/usr/bin/env python3
"""Prepare a browser-harness recording for deterministic video editing."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

from video_policy import VideoPolicyError, write_source_manifest


ROOT = Path(__file__).resolve().parents[3]
TEMPLATE = ROOT / "interaction-skills" / "video-template.html"
SENSITIVE = re.compile(
    r"@|onmicrosoft\.com|(?:tenant|user|object)[_-]?id|"
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
TYPE_HELPERS = {"type_text", "fill", "fill_input"}


def safe_route_hint(_url: str) -> str:
    """Return a private placeholder; the editor authors meaning from frames.

    URL hosts and paths can contain customer domains, tenant IDs, emails, and
    opaque application state. Guessing a product-specific route here also makes
    an unrelated recording look fabricated.
    """
    return "Browser"


def safe_text(event: dict) -> str | None:
    value = event.get("text")
    if value is None:
        return None
    if event.get("helper") in TYPE_HELPERS:
        return "<typed text hidden>"
    value = str(value)
    if event.get("input") == "password" or SENSITIVE.search(value):
        return "<sensitive>"
    return value[:120]


def safe_label(value: object) -> str | None:
    if value is None:
        return None
    value = str(value)
    return "<sensitive>" if SENSITIVE.search(value) else value[:120]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("recording", type=Path)
    parser.add_argument(
        "--require-explicit",
        action="store_true",
        help="reject an automatic/background recording",
    )
    args = parser.parse_args()
    recording = args.recording.expanduser().resolve()
    events_path = recording / "events.jsonl"
    if not events_path.is_file():
        parser.error(f"missing {events_path}")
    meta_path = recording / "meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.is_file() else {}
    if args.require_explicit and (not meta_path.is_file() or meta.get("auto") is True):
        parser.error(
            "this is not an explicit recording; use the exact directory returned "
            "by start_recording() for a video requested before the task"
        )

    shutil.copy2(TEMPLATE, recording / "video.html")
    events = []
    for source_line, line in enumerate(
        events_path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        raw = json.loads(line)
        if not raw.get("frame"):
            continue
        events.append(
            {
                "frame": raw["frame"],
                "sourceLine": source_line,
                "helper": raw.get("helper"),
                "ts": raw.get("ts"),
                "route": safe_route_hint(str(raw.get("url") or "")),
                "tab": safe_label(raw.get("title")),
                "viewport": {"w": raw.get("w"), "h": raw.get("h")},
                "cursor": (
                    {"x": raw.get("x"), "y": raw.get("y")}
                    if raw.get("x") is not None and raw.get("y") is not None
                    else None
                ),
                "box": raw.get("box"),
                "text": safe_text(raw),
                "textLength": len(str(raw.get("text") or "")),
                "typed": raw.get("helper") in TYPE_HELPERS,
                "password": raw.get("input") == "password",
                "sensitive": bool(
                    raw.get("helper") in TYPE_HELPERS
                    or raw.get("input") == "password"
                    or SENSITIVE.search(str(raw.get("text") or ""))
                ),
            }
        )

    summary = {
        "recording": recording.name,
        "title": safe_label(meta.get("title")),
        "eventCount": len(events),
        "events": events,
    }
    output = recording / "recording-summary.json"
    output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    try:
        write_source_manifest(recording)
    except VideoPolicyError as exc:
        parser.error(str(exc))
    print(f"renderer: {recording / 'video.html'}")
    print(f"summary:  {output}")
    print(f"source:   {recording / 'video-source.json'}")
    print("next:     write edit-brief.json, then run render_video.py review")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
