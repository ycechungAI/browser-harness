browser-harness is a thin layer that connects agents to browsers via an editable CDP harness.

# Code priorities
- Clarity
- Precision
- Low verbosity
- Versatility

# Overview
Core code lives in `src/browser_harness/`:
- `admin.py` — daemon lifecycle, diagnostics, updates, profile management
- `daemon.py` — the long-lived middleman process between the browser and the agent
- `helpers.py` — CDP wrapper and core browser primitives auto-imported into `-c` scripts
- `run.py` — the `browser-harness` CLI

`SKILL.md` tells agents how to use the harness and CLI.
`install.md` tells agents how to install it, attach a browser, and troubleshoot.
In this checkout, invoke the current source with `./browser-harness`; do not use
a globally installed `browser-harness` binary.

For any session-recording or video task, read
`skills/browser-harness-video/SKILL.md` fully and reuse the shared renderer.
Do not invent a separate editing workflow.

Recording and video creation require user intent. Treat any natural-language
nudge such as “show me what you did,” “record this,” “make a video,” “demo it,”
or “walk me through it” as opt-in; do not require exact wording. Significant
work alone is not consent. For a video requested before browser work, call
`start_recording()` before the first action and retain its exact returned path;
never substitute `./browser-harness recordings --latest`. Use `--latest` only
for a post-task request after verifying timestamps and pages. Never reenact a
task. When a video was requested and subagents are available, delegate only
post-production with the original task and exact recording path.

An agent operating the harness only edits inside `agent-workspace/`:
- `agent_helpers.py` — task-specific browser helpers the agent adds
- `domain-skills/` — skills the agent writes and reads

# Contributing
Consider what is really needed. Prefer the smallest diff that fixes the bug.
