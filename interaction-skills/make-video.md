# Making a video from a recording

Turn a session recording (see `start_recording()` / `stop_recording()`) into a
short, engaging, Screen-Studio-style video. You are the editor: you read the
trace, decide the story, write the composition, watch your own cut, and
iterate. The template renders it; taste comes from you.

A recording is a folder of numbered JPEG frames plus `events.jsonl` — one line
per action with `helper`, click `x`/`y`, the focused-input `box`, typed `text`,
`url`, viewport `w`/`h`, and the post-action `frame` filename.

## Editor's brief

- **As short as possible, no shorter.** Omit `dur` — the template computes the
  readability floor per beat: `max(action minimum, 0.45 + 0.28 × caption words)`
  (~3.5 words/sec + recognition time). Only set `dur` to go *longer* (payoff
  shots). A 4-minute session should land around 20s.
- **Hook in 2 seconds.** Title card over the first beat, then straight into
  action. Cut everything that doesn't advance the story — loads, waits,
  retries, and "result" holds (the next beat's frame already shows the result).
- **Zoom on intent.** Every click gets a camera punch-in on the click point
  (`zoom: {x, y, scale: 1.6-1.9}`); every typed field gets a punch-in on its
  `box`. Pull wide (`zoom` omitted) on navigations and reveals.
- **Captions carry the narrative.** Short, present tense, personality over
  literalism: "Plot twist: the cart wasn't empty" beats "Deleting item 2 of 3".
  One idea per caption. Not every beat needs one.
- **Mistakes are content — and must be unmissable.** Set `error: true` on the
  beat: the template gives it a red vignette, an `⚠ ERROR` chip, a shake, and a
  red caption pill. Zoom in on the *evidence* (the wrong text, the failed
  state) so the viewer can read it, and caption it honestly. Keep one if you
  have one.
- **Camera calm beats camera clever.** Hold static shots; give consecutive
  actions in the same region the SAME zoom target (zero motion between them).
  One thing moves at a time — the template sequences camera → cursor → click →
  result for you.
- **End on the payoff + flex.** Final state wide, then outro:
  "Done in 4m 28s" (`outro` / `outroSub`).

## Beat conventions

The composition is `window.COMPOSITION = {title, outro, outroSub, viewport,
beats: [...]}` — schema documented at the top of the template. Timing rules:

- A **click beat** shows the frame *before* the click (the previous event's
  `frame`), with `cursor: {x, y}`, `click: true`, and a `zoom` on the same
  point. The **next beat** shows the result frame — that's the reaction shot.
- A **typing beat** shows the pre-typing frame with `type: {box, text}` (both
  straight from the event); the template animates the text into the box.
- A **navigation beat** shows its own frame, wide, with `url` (omnibox text)
  and `tab` (tab title) set — the template draws a realistic Chrome window.
- A **hold beat** (`hold: true`) freezes the previous camera on a result frame.
- Coordinates are page CSS px — use event `x`/`y`/`box` verbatim. Set
  `viewport: {w, h}` from the events once.
- **Telemetry is automatic**: click/type beats get `STEP k/N` + call chips and
  click crosshairs; set `label` to override (e.g. `'goto("site.com")'`). Set
  `t` (session wall-clock seconds, from event `ts` minus start) on beats to
  drive the fast-running session clock — it sells the time compression.

## Workflow

1. Read `events.jsonl`. Sketch the story: hook → beats → payoff.
2. Copy the template into the recording dir and write the composition:
   `cp interaction-skills/video-template.html <rec>/video.html`, then write
   `<rec>/composition.js`. (Template source:
   https://github.com/browser-use/browser-harness/blob/main/interaction-skills/video-template.html)
3. Serve the dir over HTTP — canvas capture fails on `file://` (tainted):
   `cd <rec> && python3 -m http.server 8123 &`
4. Open `http://127.0.0.1:8123/video.html` in a tab and **review your cut**:
   `js("seek(4.2)")` then `capture_screenshot()` — scrub every beat boundary.
   Check: caption overlapping the action? zoom too tight? cursor path silly?
   Fix composition.js, reload, re-check. At least one full pass.
5. Export: `js("exportVideo('my-video.webm')")` — it plays once in realtime
   (a 30s video takes 30s) and downloads to Chrome's download dir. Keep the
   tab focused and wait ~duration+2s, then confirm via
   `js("window.__exported")`. Move the file where the user wants it.
6. Kill the http server. Tell the user the path.

## Gotchas

- `file://` pages taint the canvas → export throws SecurityError. Always http.
- Background tabs throttle `requestAnimationFrame` → export stalls. Keep the
  compositor tab active until export resolves.
- Frames are captured at devicePixelRatio; the template maps CSS px itself —
  never pre-scale coordinates.
- MediaRecorder outputs webm (vp9). If the user wants mp4:
  `ffmpeg -i video.webm -c:v libx264 -crf 20 video.mp4` (needs ffmpeg).
- Missing frame file → that beat renders black; the HUD bottom-left shows
  playhead/beat for debugging.
