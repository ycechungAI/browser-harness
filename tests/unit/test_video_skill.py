import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills/browser-harness-video/scripts"
sys.path.insert(0, str(SCRIPTS))
STYLE = json.loads(
    (ROOT / "skills/browser-harness-video/assets/house-style.json").read_text()
)


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


policy = load("video_policy_test", "video_policy.py")
compose = load("compose_video_test", "compose_video.py")
initialize = load("init_video_test", "init_video.py")


def brief(action, frames):
    return {
        "task": "Complete the task",
        "plan": ["Act", "Verify"],
        "actions": [action],
        "outcomes": ["Result verified"],
        "privacy": {"reviewedFrames": frames, "redact": {}},
    }


def event(frame, helper, **extra):
    return {
        "frame": frame,
        "sourceLine": extra.pop("sourceLine", 1),
        "helper": helper,
        "ts": 100.0,
        "viewport": {"w": 1392, "h": 1170},
        "cursor": None,
        "box": None,
        "text": None,
        **extra,
    }


def test_compiler_owns_visuals_privacy_and_provenance(tmp_path):
    summary = {
        "events": [
            event("0001.jpg", "wait_for_load"),
            event("0002.jpg", "click_at_xy", cursor={"x": 60, "y": 1138}),
            event("0003.jpg", "wait_for_load"),
        ]
    }
    edit = brief(
        {
            "event": 2,
            "frameEvent": 1,
            "afterEvent": 3,
            "chapter": 0,
            "route": "App / Form",
        },
        ["0001.jpg", "0003.jpg"],
    )
    result = compose.compile_brief(summary, edit, STYLE)
    action = result["beats"][1]
    assert result["schemaVersion"] == 1
    assert result["motion"] == STYLE["motion"]
    assert action["click"] and action["after"] == "0003.jpg"
    assert action["endStateHold"] == STYLE["pacing"]["rawToCardHoldSeconds"]

    edit["actions"][0]["wide"] = True
    with pytest.raises(compose.BriefError, match="unsupported field"):
        compose.compile_brief(summary, edit, STYLE)
    edit["actions"][0].pop("wide")
    edit["actions"][0]["route"] = "https://internal.example/admin"
    with pytest.raises(compose.BriefError, match="semantic"):
        compose.compile_brief(summary, edit, STYLE)

    (tmp_path / "events.jsonl").write_text("{}\n")
    (tmp_path / "meta.json").write_text("{}")
    policy.write_source_manifest(tmp_path)
    (tmp_path / "events.jsonl").write_text('{"changed": true}\n')
    with pytest.raises(policy.VideoPolicyError, match="source changed"):
        policy.verify_source_manifest(tmp_path)


def test_typed_text_is_hidden_unless_a_safe_nonpassword_event_is_opted_in():
    assert initialize.safe_text({"helper": "type_text", "text": "sk-secret"}) == "<typed text hidden>"
    typed = event(
        "0001.jpg",
        "type_text",
        sourceLine=7,
        box={"x": 100, "y": 80, "w": 300, "h": 40},
        text="<typed text hidden>",
        password=False,
    )
    hidden = compose.compile_brief(
        {"events": [typed]},
        brief({"event": 1, "chapter": 0, "route": "App / Search"}, ["0001.jpg"]),
        STYLE,
        {7: "global administrator"},
    )["beats"][1]["type"]
    assert hidden["redact"] is True and "global administrator" not in hidden["text"]

    edit = brief(
        {"event": 1, "chapter": 0, "route": "App / Search", "showTyping": True},
        ["0001.jpg"],
    )
    shown = compose.compile_brief(
        {"events": [typed]}, edit, STYLE, {7: "global administrator"}
    )["beats"][1]["type"]
    assert shown == {
        "box": {"x": 100, "y": 80, "w": 300, "h": 40},
        "text": "global administrator",
    }

    typed["password"] = True
    with pytest.raises(compose.BriefError, match="cannot reveal a password"):
        compose.compile_brief({"events": [typed]}, edit, STYLE, {7: "secret"})


def test_renderer_keeps_edge_clicks_visible_and_rejects_raw_routes():
    composition = {
        "schemaVersion": 1,
        "viewport": {"w": 1392, "h": 1170},
        "cursorStart": {"x": 700, "y": 280},
        "frameStyle": "native",
        "readingWpm": 380,
        "pacing": STYLE["pacing"],
        "durationBudget": 22,
        "plan": ["Act", "Verify"],
        "bg": STYLE["background"],
        "motion": STYLE["motion"],
        "privacy": {"reviewedFrames": ["before.jpg", "after.jpg"]},
        "beats": [
            {"card": True, "kind": "intro", "title": "Task", "dur": 4.5},
            {
                "frame": "before.jpg",
                "after": "after.jpg",
                "route": "App / Review",
                "chapter": 0,
                "cursor": {"x": 60, "y": 1138},
                "click": True,
                "dur": 1.7,
            },
            {
                "card": True,
                "kind": "outcome",
                "title": "Done",
                "outcomes": ["Verified"],
                "dur": 4.5,
            },
        ],
    }
    node = r"""
const fs=require('fs'),vm=require('vm');
const html=fs.readFileSync(process.argv[1],'utf8');
const source=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].at(-1)[1];
const noop=()=>{}, gradient={addColorStop:noop};
const ctx=new Proxy({}, {get(_t,k){
  if(k==='measureText') return t=>({width:String(t).length*10});
  if(k==='createLinearGradient'||k==='createRadialGradient') return ()=>gradient;
  return noop;
},set(){return true;}});
const sandbox={window:{COMPOSITION:JSON.parse(process.argv[2])},document:{
  getElementById:id=>id==='stage'?{getContext:()=>ctx}:{textContent:''},
  createElement:()=>({click:noop}),addEventListener:noop},
  matchMedia:()=>({matches:false}),Path2D:class{},
  Image:class{set src(_v){queueMicrotask(()=>this.onload?.())}},
  requestAnimationFrame:noop,performance:{now:()=>0},
  MediaRecorder:{isTypeSupported:()=>true},Blob:class{},
  URL:{createObjectURL:()=>''},console,Promise,queueMicrotask,setTimeout,clearTimeout};
vm.createContext(sandbox);vm.runInContext(source,sandbox);
process.stdout.write(JSON.stringify({
  clicks:sandbox.window.clickVisibility(),preflight:sandbox.window.videoPreflight()}));
"""

    def run(value):
        proc = subprocess.run(
            [
                "node",
                "-e",
                node,
                str(ROOT / "interaction-skills/video-template.html"),
                json.dumps(value),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        assert proc.returncode == 0, proc.stderr
        return json.loads(proc.stdout)

    result = run(composition)
    click = result["clicks"][0]
    assert result["preflight"]["errors"] == [] and click["visible"]
    assert 0 < click["resultTime"] - click["time"] <= 0.08

    composition["beats"][1]["route"] = "https://internal.example/admin"
    assert any("raw URL" in error for error in run(composition)["preflight"]["errors"])
