#!/usr/bin/env python3
"""Compile editorial choices into the deterministic browser video house style."""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any

from video_policy import OPAQUE_HEX, ROUTE_UNSAFE, VideoPolicyError, load_json as policy_load_json, used_frames


SKILL = Path(__file__).resolve().parents[1]
STYLE_PATH = SKILL / "assets" / "house-style.json"
ACTION_KEYS = {
    "event",
    "frameEvent",
    "afterEvent",
    "chapter",
    "route",
    "afterRoute",
    "narration",
    "label",
    "detour",
    "error",
    "context",
    "showTyping",
}
BRIEF_KEYS = {
    "task",
    "summary",
    "plan",
    "actions",
    "explanations",
    "outcomeTitle",
    "outcomeSummary",
    "outcomes",
    "privacy",
}
PRIVACY_KEYS = {"reviewedFrames", "redact"}
EXPLANATION_KEYS = {
    "afterAction",
    "title",
    "summary",
    "observed",
    "mistake",
    "correction",
}
TYPE_HELPERS = {"type_text", "fill", "fill_input"}
CLICK_HELPERS = {"click_at_xy"}
REDACTION_KEYS = {"x", "y", "w", "h", "fill", "stroke", "radius", "pad"}


class BriefError(ValueError):
    """An edit brief violates the deliberately small authoring contract."""


def load_json(path: Path) -> dict[str, Any]:
    try:
        return policy_load_json(path)
    except VideoPolicyError as exc:
        raise BriefError(str(exc)) from exc


def reject_unknown(value: dict[str, Any], allowed: set[str], where: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise BriefError(f"{where} has unsupported field(s): {', '.join(unknown)}")


def require_text(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BriefError(f"{where} must be non-empty text")
    return value.strip()


def require_text_list(value: Any, where: str, low: int, high: int) -> list[str]:
    if not isinstance(value, list) or not low <= len(value) <= high:
        raise BriefError(f"{where} must contain {low}–{high} items")
    return [require_text(item, f"{where}[{index}]") for index, item in enumerate(value)]


def words(value: Any) -> int:
    return len(re.findall(r"\S+", str(value or "")))


def card_duration(
    title: str,
    summary: str | None,
    details: list[str],
    kind: str,
    reading_wpm: float,
) -> float:
    text = " ".join(part for part in (title, summary, *details) if part)
    base = 4.5 if kind in {"intro", "outcome"} else 4.0
    return round(max(base, 0.4 + words(text) * 60 / reading_wpm), 3)


def validate_narration(value: Any, where: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise BriefError(f"{where} must be text")
    if words(value) > 7:
        raise BriefError(f"{where} exceeds seven words")
    return value.strip()


def optional_text(value: Any, where: str) -> str | None:
    if value is None:
        return None
    return require_text(value, where)


def event_at(events: list[dict[str, Any]], number: Any, where: str) -> dict[str, Any]:
    if not isinstance(number, int) or isinstance(number, bool):
        raise BriefError(f"{where} must be a one-based integer")
    if number < 1 or number > len(events):
        raise BriefError(f"{where} is outside recording-summary.json")
    event = events[number - 1]
    if not event.get("frame"):
        raise BriefError(f"{where} has no captured frame")
    return event


def event_target(event: dict[str, Any]) -> dict[str, float] | None:
    cursor = event.get("cursor")
    if isinstance(cursor, dict) and cursor.get("x") is not None and cursor.get("y") is not None:
        return {"x": float(cursor["x"]), "y": float(cursor["y"])}
    box = event.get("box")
    if isinstance(box, dict) and all(box.get(key) is not None for key in ("x", "y", "w", "h")):
        return {
            "x": float(box["x"]) + float(box["w"]) * 0.3,
            "y": float(box["y"]) + float(box["h"]) / 2,
        }
    return None


def require_matching_viewport(event: dict[str, Any], viewport: dict[str, Any], where: str) -> None:
    candidate = event.get("viewport") or {}
    if candidate.get("w") != viewport.get("w") or candidate.get("h") != viewport.get("h"):
        raise BriefError(f"{where} uses a different viewport; split or normalize the recording first")


def default_action_duration(beat: dict[str, Any], pacing: dict[str, Any]) -> float:
    base = 0.7
    if beat.get("click"):
        base = 1.15
    if beat.get("after"):
        base = max(base, 1.4)
    typing = beat.get("type")
    if typing:
        base = max(base, 0.6 + len(str(typing.get("text") or "")) * 0.035)
    narration = beat.get("narration")
    if narration:
        base = max(
            base,
            float(pacing["captionBaseSeconds"])
            + float(pacing["captionSecondsPerWord"]) * words(narration),
        )
    return round(base, 3)


def duration_budget(
    action_count: int,
    explanation_count: int,
    raw_to_card_count: int,
    pacing: dict[str, Any],
) -> float:
    budget = float(pacing["baseDurationBudget"])
    budget += max(0, action_count - 5) * float(pacing["extraActionSeconds"])
    budget += max(0, explanation_count - 1) * float(
        pacing["extraExplanationSeconds"]
    )
    budget += raw_to_card_count * float(pacing["rawToCardHoldSeconds"])
    return round(min(budget, float(pacing["maximumDurationBudget"])), 3)


def add_raw_to_card_holds(beats: list[dict[str, Any]], pacing: dict[str, Any]) -> int:
    hold = float(pacing["rawToCardHoldSeconds"])
    count = 0
    for beat, next_beat in zip(beats, beats[1:]):
        if beat.get("card") or not next_beat.get("card"):
            continue
        beat["endStateHold"] = hold
        beat["dur"] = round(float(beat["dur"]) + hold, 3)
        count += 1
    return count


def compile_action(
    action: dict[str, Any],
    index: int,
    events: list[dict[str, Any]],
    plan: list[str],
    first_ts: float,
    previous_target: dict[str, float] | None,
    viewport: dict[str, float],
    pacing: dict[str, Any],
    revealed_text: dict[int, str],
) -> tuple[dict[str, Any], dict[str, float] | None]:
    if not isinstance(action, dict):
        raise BriefError(f"actions[{index}] must be an object")
    reject_unknown(action, ACTION_KEYS, f"actions[{index}]")
    if "showTyping" in action and not isinstance(action["showTyping"], bool):
        raise BriefError(f"actions[{index}].showTyping must be true or false")
    event = event_at(events, action.get("event"), f"actions[{index}].event")
    require_matching_viewport(event, viewport, f"actions[{index}].event")
    frame_event = event
    if action.get("frameEvent") is not None:
        frame_event = event_at(
            events, action["frameEvent"], f"actions[{index}].frameEvent"
        )
        require_matching_viewport(frame_event, viewport, f"actions[{index}].frameEvent")
    chapter = action.get("chapter")
    if not isinstance(chapter, int) or isinstance(chapter, bool) or not 0 <= chapter < len(plan):
        raise BriefError(f"actions[{index}].chapter must index plan")
    route = require_text(action.get("route"), f"actions[{index}].route")
    if ROUTE_UNSAFE.search(route):
        raise BriefError(f"actions[{index}].route must be semantic, not a raw URL or identity")

    beat: dict[str, Any] = {
        "frame": frame_event["frame"],
        "route": route,
        "chapter": chapter,
    }
    after_number = action.get("afterEvent")
    if after_number is not None:
        after = event_at(events, after_number, f"actions[{index}].afterEvent")
        require_matching_viewport(after, viewport, f"actions[{index}].afterEvent")
        beat["after"] = after["frame"]
        after_route = action.get("afterRoute")
        if after_route is not None:
            after_route = require_text(after_route, f"actions[{index}].afterRoute")
            if ROUTE_UNSAFE.search(after_route):
                raise BriefError(f"actions[{index}].afterRoute must be semantic")
            beat["afterRoute"] = after_route

    narration = validate_narration(action.get("narration"), f"actions[{index}].narration")
    if narration is not None:
        beat["narration"] = narration
    if action.get("label") is not None:
        beat["label"] = require_text(action["label"], f"actions[{index}].label")
    if action.get("detour") is True:
        beat["detour"] = True
    if action.get("error") is True:
        beat["error"] = True

    helper = str(event.get("helper") or "")
    cursor = event.get("cursor")
    if helper in CLICK_HELPERS:
        if not isinstance(cursor, dict) or cursor.get("x") is None or cursor.get("y") is None:
            raise BriefError(f"actions[{index}] identifies a click without captured coordinates")
        beat["cursor"] = {"x": cursor["x"], "y": cursor["y"]}
        beat["click"] = True
    elif helper in TYPE_HELPERS:
        box = event.get("box")
        if not isinstance(box, dict) or not all(box.get(key) is not None for key in ("x", "y", "w", "h")):
            raise BriefError(f"actions[{index}] identifies typing without a captured box")
        show_typing = action.get("showTyping") is True
        if show_typing and event.get("password"):
            raise BriefError(f"actions[{index}].showTyping cannot reveal a password field")
        source_line = event.get("sourceLine")
        if show_typing and source_line not in revealed_text:
            raise BriefError(f"actions[{index}].showTyping requires the original typed event")
        beat["type"] = {
            "box": {key: box[key] for key in ("x", "y", "w", "h")},
            "text": revealed_text[source_line] if show_typing else "••••••",
            **({} if show_typing else {"redact": True}),
        }
    elif action.get("showTyping") is not None:
        raise BriefError(f"actions[{index}].showTyping requires a typing event")

    target = event_target(event)
    if action.get("context") is True and not (beat.get("click") or beat.get("type")):
        beat["wide"] = True
    elif target and previous_target:
        distance = math.hypot(target["x"] - previous_target["x"], target["y"] - previous_target["y"])
        diagonal = math.hypot(float(viewport["w"]), float(viewport["h"]))
        if distance > diagonal * 0.58:
            beat["cameraCut"] = True

    ts = event.get("ts")
    if isinstance(ts, (int, float)):
        beat["t"] = round(max(0.0, float(ts) - first_ts), 3)
    beat["dur"] = default_action_duration(beat, pacing)
    return beat, target or previous_target


def validate_privacy(reviewed: list[str], redact: dict[str, Any], composition: dict[str, Any]) -> None:
    frames = used_frames(composition)
    for frame in (*frames, *reviewed, *redact):
        if Path(frame).name != frame or not frame.lower().endswith(".jpg"):
            raise BriefError(f"invalid frame name: {frame}")
    if len(reviewed) != len(set(reviewed)):
        raise BriefError("privacy.reviewedFrames contains duplicates")
    missing = [frame for frame in frames if frame not in reviewed]
    if missing:
        raise BriefError("privacy review missing: " + ", ".join(missing))
    unknown = sorted(set(redact) - set(frames))
    if unknown:
        raise BriefError("privacy.redact lists unused frames: " + ", ".join(unknown))
    for frame, rectangles in redact.items():
        if not isinstance(rectangles, list):
            raise BriefError(f"privacy.redact.{frame} must be a list")
        for index, rectangle in enumerate(rectangles):
            where = f"privacy.redact.{frame}[{index}]"
            if not isinstance(rectangle, dict):
                raise BriefError(f"{where} must be an object")
            reject_unknown(rectangle, REDACTION_KEYS, where)
            for key in ("x", "y", "w", "h"):
                value = rectangle.get(key)
                if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
                    raise BriefError(f"{where}.{key} must be a finite number")
            if rectangle["w"] <= 0 or rectangle["h"] <= 0:
                raise BriefError(f"{where} must have positive width and height")
            for key in ("fill", "stroke"):
                value = rectangle.get(key)
                if value is not None and value is not False and (
                    not isinstance(value, str) or not OPAQUE_HEX.fullmatch(value)
                ):
                    raise BriefError(f"{where}.{key} must be false or opaque six-digit hex")


def compile_brief(summary: dict[str, Any], brief: dict[str, Any], style: dict[str, Any], revealed_text: dict[int, str] | None = None) -> dict[str, Any]:
    reject_unknown(brief, BRIEF_KEYS, "edit brief")
    task = require_text(brief.get("task"), "task")
    summary_text = optional_text(brief.get("summary"), "summary")
    plan = require_text_list(brief.get("plan"), "plan", 2, 5)
    outcomes = require_text_list(brief.get("outcomes"), "outcomes", 1, 5)
    actions = brief.get("actions")
    if not isinstance(actions, list) or not actions:
        raise BriefError("actions must contain at least one action")
    events = summary.get("events")
    if not isinstance(events, list) or not events:
        raise BriefError("recording-summary.json has no events")
    first_action = actions[0]
    if not isinstance(first_action, dict):
        raise BriefError("actions[0] must be an object")
    viewport_event = event_at(
        events,
        first_action.get("frameEvent", first_action.get("event")),
        "actions[0].frameEvent" if "frameEvent" in first_action else "actions[0].event",
    )
    if not (viewport_event.get("viewport") or {}).get("w") or not (viewport_event.get("viewport") or {}).get("h"):
        raise BriefError("recording-summary.json has no viewport")
    viewport = viewport_event["viewport"]
    first_ts = next(
        (float(event["ts"]) for event in events if isinstance(event.get("ts"), (int, float))),
        0.0,
    )

    privacy = brief.get("privacy")
    if not isinstance(privacy, dict):
        raise BriefError("privacy must be an object")
    reject_unknown(privacy, PRIVACY_KEYS, "privacy")
    reviewed = privacy.get("reviewedFrames")
    if not isinstance(reviewed, list) or not all(isinstance(frame, str) for frame in reviewed):
        raise BriefError("privacy.reviewedFrames must be a list of frame names")
    redact = privacy.get("redact") or {}
    if not isinstance(redact, dict):
        raise BriefError("privacy.redact must be an object")

    explanations = brief.get("explanations") or []
    if not isinstance(explanations, list):
        raise BriefError("explanations must be a list")
    pacing = style["pacing"]
    reading_wpm = float(style["readingWpm"])
    explanation_by_action: dict[int, list[dict[str, Any]]] = {}
    revealed_text = revealed_text or {}
    for index, explanation in enumerate(explanations):
        if not isinstance(explanation, dict):
            raise BriefError(f"explanations[{index}] must be an object")
        reject_unknown(explanation, EXPLANATION_KEYS, f"explanations[{index}]")
        after_action = explanation.get("afterAction")
        if not isinstance(after_action, int) or isinstance(after_action, bool) or not 1 <= after_action <= len(actions):
            raise BriefError(f"explanations[{index}].afterAction must index actions")
        title = require_text(explanation.get("title"), f"explanations[{index}].title")
        sub = optional_text(explanation.get("summary"), f"explanations[{index}].summary")
        points = [
            {"label": "Observed", "text": require_text(explanation.get("observed"), f"explanations[{index}].observed")},
            {"label": "Mistake", "text": require_text(explanation.get("mistake"), f"explanations[{index}].mistake")},
            {"label": "Correction", "text": require_text(explanation.get("correction"), f"explanations[{index}].correction")},
        ]
        card = {
            "card": True,
            "kind": "explanation",
            "title": title,
            **({"sub": sub} if sub is not None else {}),
            "points": points,
            "dur": card_duration(
                title,
                sub,
                [part for point in points for part in (point["label"], point["text"])],
                "explanation",
                reading_wpm,
            ),
        }
        explanation_by_action.setdefault(after_action, []).append(card)

    intro = {
        "card": True,
        "kind": "intro",
        "title": task,
        **({"sub": summary_text} if summary_text is not None else {}),
        "dur": card_duration(task, summary_text, plan, "intro", reading_wpm),
    }
    beats: list[dict[str, Any]] = [intro]
    previous_target = None
    for index, action in enumerate(actions):
        beat, previous_target = compile_action(
            action, index, events, plan, first_ts, previous_target, viewport, pacing, revealed_text
        )
        beats.append(beat)
        beats.extend(explanation_by_action.get(index + 1, []))

    outcome_title = require_text(brief.get("outcomeTitle") or "Task complete", "outcomeTitle")
    outcome_summary = optional_text(brief.get("outcomeSummary"), "outcomeSummary")
    beats.append(
        {
            "card": True,
            "kind": "outcome",
            "title": outcome_title,
            **({"sub": outcome_summary} if outcome_summary is not None else {}),
            "outcomes": outcomes,
            "dur": card_duration(
                outcome_title, outcome_summary, outcomes, "outcome", reading_wpm
            ),
        }
    )

    raw_to_card_count = add_raw_to_card_holds(beats, pacing)
    budget = duration_budget(
        len(actions), len(explanations), raw_to_card_count, pacing
    )
    duration = round(sum(float(beat["dur"]) for beat in beats), 3)
    if duration > budget + 0.001:
        raise BriefError(
            f"compiled video is {duration:.1f}s; house-style budget is "
            f"{budget:.1f}s. Shorten card copy, remove redundant actions, or set "
            "narration only when the thought changes; viewers can pause for detail"
        )

    house_privacy = style["privacy"]
    composition = {
        "schemaVersion": style["version"],
        "viewport": {"w": viewport["w"], "h": viewport["h"]},
        "cursorStart": style["cursorStart"],
        "frameStyle": style["frameStyle"],
        "readingWpm": style["readingWpm"],
        "pacing": pacing,
        "durationBudget": budget,
        "bg": style["background"],
        "plan": plan,
        "motion": style["motion"],
        "privacy": {
            "reviewedFrames": reviewed,
            "pad": house_privacy["pad"],
            "mask": house_privacy["mask"],
        },
        "redact": redact,
        "beats": beats,
    }
    validate_privacy(reviewed, redact, composition)
    return composition


def write_composition(path: Path, composition: dict[str, Any]) -> None:
    body = json.dumps(composition, indent=2, ensure_ascii=False)
    path.write_text(f"window.COMPOSITION = {body};\n", encoding="utf-8")


def load_revealed_text(events_path: Path) -> dict[int, str]:
    revealed: dict[int, str] = {}
    try:
        lines = events_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise BriefError(f"cannot read {events_path}: {exc}") from exc
    for source_line, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise BriefError(f"cannot read {events_path}: {exc}") from exc
        if event.get("helper") in TYPE_HELPERS and event.get("input") != "password":
            text = event.get("text")
            if text is not None:
                revealed[source_line] = str(text)
    return revealed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("recording", type=Path)
    parser.add_argument("--brief", default="edit-brief.json")
    parser.add_argument("--output", default="composition.js")
    args = parser.parse_args()
    recording = args.recording.expanduser().resolve()
    try:
        summary = load_json(recording / "recording-summary.json")
        brief = load_json(recording / args.brief)
        style = load_json(STYLE_PATH)
        composition = compile_brief(summary, brief, style, load_revealed_text(recording / "events.jsonl"))
        write_composition(recording / args.output, composition)
    except BriefError as exc:
        parser.error(str(exc))
    print(f"composition: {recording / args.output}")
    print(f"schema: {composition['schemaVersion']}")
    print(f"beats: {len(composition['beats'])}")
    print(
        "duration: "
        f"{sum(beat['dur'] for beat in composition['beats']):.1f}s / "
        f"{composition['durationBudget']:.1f}s budget"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
