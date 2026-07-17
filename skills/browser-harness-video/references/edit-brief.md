# Edit brief schema

`edit-brief.json` contains editorial choices only. The compiler owns timing,
camera, motion, typography, colors, browser framing, cursor, and click effects.

```json
{
  "task": "Extract the top five stories and comments",
  "summary": "Collect each discussion and save structured JSON.",
  "plan": ["Collect stories", "Capture discussions", "Verify JSON"],
  "actions": [
    {
      "event": 3,
      "frameEvent": 2,
      "afterEvent": 4,
      "chapter": 0,
      "route": "Hacker News / Front page",
      "afterRoute": "Hacker News / Discussion",
      "narration": "Open the first discussion.",
      "label": "Open discussion"
    },
    {
      "event": 8,
      "chapter": 1,
      "route": "Hacker News / Discussion",
      "narration": "Capture the complete comment tree."
    }
  ],
  "explanations": [
    {
      "afterAction": 1,
      "title": "Why the first approach failed",
      "summary": "The selector was too broad.",
      "observed": "Navigation links appeared in the result",
      "mistake": "I selected every page link",
      "correction": "Restrict extraction to story rows"
    }
  ],
  "outcomeTitle": "Five discussions captured",
  "outcomeSummary": "The requested JSON is verified.",
  "outcomes": ["Five current stories saved", "Comment trees preserved"],
  "privacy": {
    "reviewedFrames": ["0002.jpg", "0004.jpg", "0008.jpg"],
    "redact": {
      "0008.jpg": [{"x": 10, "y": 10, "w": 120, "h": 32}]
    }
  }
}
```

Rules:

- `event`, `frameEvent`, and `afterEvent` are one-based entries in
  `recording-summary.json`. `event` supplies real action coordinates;
  `frameEvent` may choose a cleaner pre-action frame; `afterEvent` shows the
  visible consequence in the same beat.
- Every action needs `event`, a zero-based `chapter`, and a short semantic
  `route`. Optional fields are `frameEvent`, `afterEvent`, `afterRoute`,
  `narration`, `label`, `detour`, `error`, `context`, and `showTyping`.
- Narration is at most seven words. Add it only when the thought changes.
- `context: true` requests an orientation shot. The compiler decides its scale.
- `showTyping: true` reveals the exact original non-password typing event.
  Omit it unless that text has been inspected and is safe, authentic evidence.
- Explanations are inserted after `afterAction` and always reveal Observed,
  Mistake, then Correction.
- Outcomes must describe verified results, never intentions.
- `privacy.reviewedFrames` must cover every source and result frame used by the
  cut. Redaction rectangles use page CSS pixels and require `x`, `y`, `w`, `h`;
  optional `fill` and `stroke` must be opaque six-digit hex (or `stroke: false`).
- A normal cut has a 22-second budget. Shorten copy or remove redundant actions
  if compilation exceeds it; viewers can pause for detail.
- Any unlisted field is rejected. In particular, do not author `dur`, `zoom`,
  `wide`, `cameraCut`, `errorMotion`, `frameStyle`, `motion`, `bg`, fonts,
  cursor coordinates, or click timing.
