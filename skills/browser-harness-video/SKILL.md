---
name: browser-harness-video
description: Turn browser-harness session recordings into trustworthy, privacy-safe explanatory videos. Use when a user asks or nudges the agent to show, record, demo, explain, or make a video of browser work, or when editing, retiming, narrating, reviewing, redacting, or exporting a requested recording folder. Do not trigger merely because browser work was significant.
---

# Browser-harness video

Use the captured browser frames as evidence and the shared compiler/renderer as
the house style. Never reenact a completed task or fabricate a cleaner result.

## Capture the right task

When the user asks for a video before browser work begins:

1. Start an explicit recording before the first browser action:
   `start_recording("short-task-name", title="Viewer-facing task")`.
2. Keep the exact directory printed by `start_recording()`. Do not rediscover
   it with `recordings --latest` and do not hand a video editor “latest.”
3. Complete and verify the task, then call `stop_recording()`.
4. Initialize that exact directory with `--require-explicit`.

When the request arrives after the task, an existing automatic recording may
be used only after its `meta.json`, timestamps, frames, and pages are verified
to match the just-completed task. If no matching evidence exists, say it was
not captured. Never replay the task merely to manufacture footage.

If subagents are available, post-production may be delegated after the final
browser action. Give the editor the original task and exact recording path.
The editor must use `BH_RECORD=0`, must not operate the live task page, and must
return the verified MP4 path and review result.

## Build the cut

From the repository root, after recording has stopped:

```bash
uv run skills/browser-harness-video/scripts/init_video.py <recording-dir> --require-explicit
```

Omit `--require-explicit` only for a verified post-task automatic recording.
Initialization drops URLs, hides every typed value from
`recording-summary.json`, and hashes the immutable source evidence.

Read `recording-summary.json`, inspect the relevant source frames, then write
`edit-brief.json` using [references/edit-brief.md](references/edit-brief.md).
Keep only actions that change the viewer's mental model.

Run the single blocking review command:

```bash
uv run skills/browser-harness-video/scripts/render_video.py review <recording-dir>
```

Review recompiles `composition.js` from the brief, verifies source hashes,
checks the renderer in normal and reduced motion, checks every exact click and
result state, and creates:

- `video-review-contact-sheet.jpg` — the one overview to inspect
- `.privacy-review/` — every used masked frame at full resolution; keep local

Fix the brief or shared compiler if review fails. Never hand-edit generated
`composition.js` or the copied `video.html`.

After inspecting the overview and every full-resolution privacy frame:

```bash
uv run skills/browser-harness-video/scripts/render_video.py export <recording-dir> --reviewed
```

The exporter never overwrites an existing render. For an intentional rerender,
pass a new name such as `--output video-v2.mp4`.

Export refuses stale or modified inputs, creates H.264 `video.mp4`, fully
decodes it, checks duration, and writes `renderer-final-contact-sheet.jpg`.
Inspect the final sheet before sharing the MP4.

## Editorial contract

- Start with the task and a 2–5 step plan. End with achieved, verified outcomes.
- Use a causal chain: intent → action → visible result.
- Narration is optional, sticky, and at most seven words. Let one thought span
  several raw frames; viewers can pause for forensic detail.
- For a useful wrong turn, show exactly `Observed`, `Mistake`, `Correction` in
  that order. Remove waits and retries that add no understanding.
- Pair a click with its `afterEvent` whenever possible. The renderer owns fast
  click feedback and holds the resulting end state before a text card.
- Use `context: true` only for orientation. The compiler owns camera cuts,
  cursor scale, zoom, pan, pacing, typography, colors, and layout.
- Keep captured frames unlabelled. Subtitles and progress stay outside the app.
- Use short semantic route labels. Never display a raw URL or invent a tab,
  route, timestamp, user value, browser state, or successful outcome.

## Privacy contract

- Treat private identities, customer or tenant data, credentials, tokens,
  IDs, raw SPA routes, and unrelated people as sensitive by default.
- Typed text is private by default, including ordinary non-password inputs.
  Set `showTyping: true` only after inspecting the original event and deciding
  the exact text is safe and important evidence. Password fields can never be
  revealed. This opt-in is what preserves authentic typing such as a public
  search phrase without allowing arbitrary tokens into the video by default.
- Public task evidence such as article authors, post text, and link domains is
  not secret merely because it contains usernames or domains.
- Use opaque page-coordinate masks; blur and pixelation are not secret-safe.
  List every used frame in `privacy.reviewedFrames` only after inspecting its
  final masked version at full resolution.

## Shared implementation

- `scripts/init_video.py` — safe summary and source manifest
- `scripts/compose_video.py` — strict brief compiler
- `scripts/render_video.py` — review, export, and MP4 verification
- `scripts/video_policy.py` — shared route, parsing, hash, and privacy policy
- `assets/house-style.json` — pacing and motion constants
- `../../interaction-skills/video-template.html` — deterministic renderer

Make general improvements in these shared files. Keep recording-specific
story and masks in `edit-brief.json`.
