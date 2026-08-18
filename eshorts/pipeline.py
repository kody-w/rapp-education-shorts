"""pipeline.py — the stages, each a file on disk and a ledger entry.

  brief   → BRIEF.md
  script  → SCRIPT.json (model, or --script file), linted
  compose → project/index.html (+ package.json, hyperframes.json, meta.json)
  check   → `hyperframes check` (lint + runtime + layout + motion + contrast), report kept
  render  → out/<slug>.mp4 (+ poster.png when ffmpeg is present), sha256 on the ledger
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from . import SCHEMA_SCRIPT, __version__
from .compose import compose, package_json
from .script import lint_script, timeline, write_script
from .store import Short, read_json, sha256_file, sha256_text, utc_now, write_json, write_text


def cli_version():
    exe = shutil.which("hyperframes")
    if not exe:
        return None
    try:
        return subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=60).stdout.strip() or None
    except Exception:
        return None


def hf_argv(*args):
    exe = shutil.which("hyperframes")
    return [exe] + list(args) if exe else ["npx", "--yes", "hyperframes"] + list(args)


def brief(short, topic, audience=None, tone=None, notes=None, length=None, theme=None):
    doc = {"topic": topic, "audience": audience or "", "tone": tone or "", "notes": notes or "",
           "length": length or "30-55s", "theme": theme or ""}
    md = ("# %s\n\n- **topic:** %s\n- **audience:** %s\n- **tone:** %s\n- **length:** %s\n- **theme:** %s\n\n%s\n"
          % (short.slug, doc["topic"], doc["audience"] or "general", doc["tone"] or "clear, warm, playful",
             doc["length"], doc["theme"] or "auto", ("## notes\n\n" + doc["notes"]) if doc["notes"] else ""))
    write_text(short.brief, md)
    write_json(short.dir / "brief.json", doc)
    short.record("brief", {"topic": topic, "brief_sha256": sha256_text(md)})
    return doc


def script(short, model="claude-opus-5", timeout=600, attempts=3, runner=None, from_file=None):
    if from_file:
        sc = read_json(from_file)
        if not isinstance(sc, dict):
            raise ValueError("--script file is not JSON: %s" % from_file)
        sc.setdefault("schema", SCHEMA_SCRIPT)
        findings = lint_script(sc)
        if findings:
            short.record("script.refused", {"source": str(from_file), "findings": findings})
            return None, findings
        write_json(short.script, sc)
        short.record("script", {"source": str(from_file), "script_sha256": sha256_file(short.script),
                                "scenes": len(sc["scenes"]), "seconds": timeline(sc)[1]})
        return sc, []
    b = read_json(short.dir / "brief.json") or {"topic": short.slug}
    sc, findings, log = write_script(b, model=model, timeout=timeout, attempts=attempts, runner=runner,
                                     drafts_dir=short.dir / "drafts")
    if sc is None:
        short.record("script.failed", {"model": model, "attempts": len(log), "findings": findings})
        return None, findings
    write_json(short.script, sc)
    short.record("script", {"model": model, "attempts": len(log), "script_sha256": sha256_file(short.script),
                            "scenes": len(sc["scenes"]), "seconds": timeline(sc)[1]})
    return sc, []


def compose_project(short, theme=None, fps=30, audio=None):
    sc = read_json(short.script)
    if not sc:
        raise ValueError("no SCRIPT.json for %s — run `script` first" % short.slug)
    findings = lint_script(sc)
    if findings:
        raise ValueError("SCRIPT.json does not pass lint: " + "; ".join(findings[:5]))
    files = compose(sc, short.slug, theme=theme, fps=fps, audio=audio)
    for name in ("index.html", "meta.json", "hyperframes.json"):
        write_text(short.project / name, files[name])
    write_text(short.project / "package.json", package_json(short.slug, cli_version()))
    (short.project / "assets").mkdir(exist_ok=True)
    (short.project / "compositions").mkdir(exist_ok=True)
    sha = sha256_file(short.project / "index.html")
    short.record("compose", {"index_sha256": sha, "duration": files["duration"], "theme": files["theme"], "fps": fps})
    return {"index": str(short.project / "index.html"), "duration": files["duration"], "theme": files["theme"],
            "index_sha256": sha}


def _run(argv, cwd, timeout):
    try:
        p = subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True, timeout=timeout,
                           stdin=subprocess.DEVNULL, env=dict(os.environ, CI="1", NO_COLOR="1"))
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "timed out after %ss" % timeout
    except FileNotFoundError as e:
        return 127, str(e)


def check(short, timeout=900):
    """`hyperframes check` in the project. Returns (ok, summary, report_path)."""
    rc, out = _run(hf_argv("check"), short.project, timeout)
    report = short.dir / "state" / "check.txt"
    write_text(report, out)
    findings = len(re.findall(r"^\s*(?:✖|✗|ERROR|error:)|\bfinding", out, flags=re.M))
    ok = rc == 0
    short.record("check", {"ok": ok, "exit": rc, "report_sha256": sha256_file(report),
                           "index_sha256": sha256_file(short.project / "index.html")})
    return ok, out[-1200:], str(report)


def render(short, quality="high", timeout=1800):
    """`hyperframes render` → out/<slug>.mp4. Returns dict with ok, mp4, sha256."""
    out_mp4 = short.out / (short.slug + ".mp4")
    rc, out = _run(hf_argv("render", "--quality", quality, "--output", str(out_mp4)), short.project, timeout)
    write_text(short.dir / "state" / "render.txt", out)
    ok = rc == 0 and out_mp4.exists() and out_mp4.stat().st_size > 0
    rec = {"ok": ok, "exit": rc, "quality": quality,
           "index_sha256": sha256_file(short.project / "index.html")}
    if ok:
        rec["mp4_sha256"] = sha256_file(out_mp4)
        rec["mp4_bytes"] = out_mp4.stat().st_size
        poster = short.out / "poster.png"
        if shutil.which("ffmpeg"):
            _run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "1.2", "-i", str(out_mp4), "-frames:v", "1", str(poster)],
                 short.out, 120)
            if poster.exists():
                rec["poster_sha256"] = sha256_file(poster)
        if shutil.which("ffprobe"):
            rc2, o2 = _run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=width,height,duration,nb_frames", "-of", "json", str(out_mp4)], short.out, 60)
            try:
                st = json.loads(o2)["streams"][0]
                rec["probe"] = {k: st.get(k) for k in ("width", "height", "duration", "nb_frames")}
            except Exception:
                pass
    short.record("render" if ok else "render.failed", rec)
    rec.update({"mp4": str(out_mp4) if ok else None, "log_tail": out[-800:]})
    return rec


def once(short, topic=None, model="claude-opus-5", from_script=None, theme=None, quality="high",
         skip_render=False, runner=None, **brief_kw):
    """The whole chain. Returns a dict describing where it stopped."""
    if topic:
        brief(short, topic, theme=theme, **brief_kw)
    sc, findings = script(short, model=model, runner=runner, from_file=from_script)
    if sc is None:
        return {"outcome": "script_failed", "findings": findings}
    comp = compose_project(short, theme=theme)
    ok, summary, report = check(short)
    if not ok:
        return {"outcome": "check_failed", "report": report, "summary": summary, **comp}
    if skip_render:
        return {"outcome": "composed", "check": "ok", **comp}
    r = render(short, quality=quality)
    if not r["ok"]:
        return {"outcome": "render_failed", "log_tail": r["log_tail"], **comp}
    return {"outcome": "rendered", "mp4": r["mp4"], "mp4_sha256": r["mp4_sha256"], "probe": r.get("probe"), **comp}
