#!/usr/bin/env python3
"""shorts.py — rapp-education-shorts CLI.

  python3 shorts.py new <slug> --topic "..." [--audience ..] [--tone ..] [--notes ..] [--theme ..]
  python3 shorts.py script <slug> [--model claude-opus-5 | --script path.json]
  python3 shorts.py compose <slug> [--theme midnight|ember|forest|paper|ocean] [--fps 30] [--audio bed.mp3]
  python3 shorts.py check <slug>                 hyperframes check on the project
  python3 shorts.py preview <slug>               hyperframes preview (Studio) — interactive
  python3 shorts.py render <slug> [--quality draft|high]
  python3 shorts.py once <slug> --topic "..." [--script path.json] [--theme ..] [--skip-render]
  python3 shorts.py status <slug> | list | verify <slug>
  python3 shorts.py long <slug> --topic "..." [--long-script LONG.json] [--tts vibevoice|none] [--quality ..] [--skip-render]
      16:9 narrated faceless explainer (3–4 min): LONG.json → VibeVoice narration → project-long/ → out/<slug>-long.mp4
  python3 shorts.py both <slug> --topic "..."   the Short and the long-form, one after the other
  python3 shorts.py briefs --source aibast [--limit N] > briefs.json
      grounded briefs from the official AIBAST Agents Library (52 advertised solutions; curated copy + captured
      demo transcripts); solution mode — the video is about the solution, never how it is built
  python3 shorts.py batch briefs.json [--formats short,long] [--quality draft|high] [--limit N] [--no-resume]
      briefs.json = [{"slug","topic","audience?","tone?","notes?","theme?","script?"}] — one by one,
      resumable (rendered slugs skip), failures logged to <root>/batch-ledger.jsonl and the batch continues

Shorts live under ./shorts/<slug>/ (override with --root or SHORTS_ROOT).
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eshorts import pipeline as P  # noqa: E402
from eshorts.store import Short  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=os.environ.get("SHORTS_ROOT") or "shorts")
    sub = ap.add_subparsers(dest="cmd")

    def add(name, slug=True):
        p = sub.add_parser(name)
        if slug:
            p.add_argument("slug")
        return p
    n = add("new"); n.add_argument("--topic", required=True); n.add_argument("--audience"); n.add_argument("--tone")
    n.add_argument("--notes"); n.add_argument("--theme")
    s = add("script"); s.add_argument("--model", default="claude-opus-5"); s.add_argument("--script", dest="from_file")
    s.add_argument("--timeout", type=int, default=600)
    c = add("compose"); c.add_argument("--theme"); c.add_argument("--fps", type=int, default=30); c.add_argument("--audio")
    add("check"); add("preview")
    r = add("render"); r.add_argument("--quality", default="high", choices=["draft", "high"])
    o = add("once"); o.add_argument("--topic"); o.add_argument("--audience"); o.add_argument("--tone"); o.add_argument("--notes")
    o.add_argument("--script", dest="from_file"); o.add_argument("--theme"); o.add_argument("--model", default="claude-opus-5")
    o.add_argument("--quality", default="high", choices=["draft", "high"]); o.add_argument("--skip-render", action="store_true")
    add("status"); add("verify"); add("list", slug=False)
    br = sub.add_parser("briefs"); br.add_argument("--source", default="aibast", choices=["aibast"]); br.add_argument("--limit", type=int)
    for name in ("long", "both"):
        l = add(name); l.add_argument("--topic"); l.add_argument("--audience"); l.add_argument("--tone"); l.add_argument("--notes")
        l.add_argument("--long-script", dest="long_file"); l.add_argument("--script", dest="from_file"); l.add_argument("--theme")
        l.add_argument("--model", default="claude-opus-5"); l.add_argument("--tts", default="vibevoice", choices=["vibevoice", "none"])
        l.add_argument("--quality", default="high", choices=["draft", "high"]); l.add_argument("--skip-render", action="store_true")
    b = sub.add_parser("batch"); b.add_argument("briefs"); b.add_argument("--model", default="claude-opus-5")
    b.add_argument("--quality", default="high", choices=["draft", "high"]); b.add_argument("--limit", type=int)
    b.add_argument("--no-resume", action="store_true"); b.add_argument("--skip-render", action="store_true")
    b.add_argument("--formats", default="short", help="comma list: short,long"); b.add_argument("--tts", default="vibevoice", choices=["vibevoice", "none"])
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help(); return 1
    root = Path(a.root)
    if a.cmd == "briefs":
        from eshorts import aibast
        out = aibast.briefs(limit=a.limit)
        for b in out:
            b["mode"] = "solution"
        print(json.dumps(out, indent=1, ensure_ascii=False)); return 0
    if a.cmd == "batch":
        briefs = json.loads(Path(a.briefs).read_text(encoding="utf-8"))
        summary, _ = P.batch(root, briefs, model=a.model, quality=a.quality, skip_render=a.skip_render,
                             resume=not a.no_resume, limit=a.limit,
                             formats=[f.strip() for f in a.formats.split(",") if f.strip()], tts_engine=a.tts)
        print(json.dumps(summary, indent=2)); return 0
    if a.cmd == "list":
        root.mkdir(parents=True, exist_ok=True)
        print(json.dumps([Short(root, d.name).status() for d in sorted(root.iterdir()) if d.is_dir()], indent=2))
        return 0
    sh = Short(root, a.slug)
    if a.cmd == "new":
        print(json.dumps(P.brief(sh, a.topic, a.audience, a.tone, a.notes, theme=a.theme), indent=2)); return 0
    if a.cmd == "script":
        sc, findings = P.script(sh, model=a.model, timeout=a.timeout, from_file=a.from_file)
        print(json.dumps({"ok": sc is not None, "findings": findings, "script": str(sh.script) if sc else None}, indent=2))
        return 0 if sc else 2
    if a.cmd == "compose":
        print(json.dumps(P.compose_project(sh, theme=a.theme, fps=a.fps, audio=a.audio), indent=2)); return 0
    if a.cmd == "check":
        ok, summary, report = P.check(sh); print(summary); print(json.dumps({"ok": ok, "report": report})); return 0 if ok else 2
    if a.cmd == "preview":
        return subprocess.call(P.hf_argv("preview"), cwd=str(sh.project))
    if a.cmd == "render":
        r = P.render(sh, quality=a.quality); print(json.dumps({k: v for k, v in r.items() if k != "log_tail"}, indent=2))
        if not r["ok"]:
            print(r["log_tail"], file=sys.stderr)
        return 0 if r["ok"] else 2
    if a.cmd == "once":
        out = P.once(sh, topic=a.topic, model=a.model, from_script=a.from_file, theme=a.theme, quality=a.quality,
                     skip_render=a.skip_render, audience=a.audience, tone=a.tone, notes=a.notes)
        print(json.dumps(out, indent=2)); return 0 if out["outcome"] in ("rendered", "composed") else 2
    if a.cmd in ("long", "both"):
        outs = {}
        if a.cmd == "both":
            outs["short"] = P.once(sh, topic=a.topic, model=a.model, from_script=a.from_file, theme=a.theme, quality=a.quality,
                                   skip_render=a.skip_render, audience=a.audience, tone=a.tone, notes=a.notes)
            a.topic = None   # brief already written
        outs["long"] = P.long(sh, topic=a.topic, model=a.model, from_script=a.long_file, tts_engine=a.tts, quality=a.quality,
                              skip_render=a.skip_render, audience=a.audience, tone=a.tone, notes=a.notes)
        print(json.dumps(outs, indent=2))
        good = all(o["outcome"] in ("rendered", "composed", "long_rendered", "long_composed") for o in outs.values())
        return 0 if good else 2
    if a.cmd == "status":
        print(json.dumps(sh.status(), indent=2)); return 0
    if a.cmd == "verify":
        ok, d = sh.verify_ledger(); print(json.dumps({"ok": ok, "detail": d})); return 0 if ok else 2
    return 1


if __name__ == "__main__":
    sys.exit(main())
