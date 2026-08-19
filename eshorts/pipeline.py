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


def brief(short, topic, audience=None, tone=None, notes=None, length=None, theme=None, mode=None, **extra):
    doc = {"topic": topic, "audience": audience or "", "tone": tone or "", "notes": notes or "",
           "length": length or "30-55s", "theme": theme or "", "mode": mode or ""}
    for k in ("brand", "chip", "agent_name"):     # presentation hints
        if extra.get(k):
            doc[k] = extra[k]
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


# ── batch ─────────────────────────────────────────────────────────────────────

def batch(root, briefs, model="claude-opus-5", quality="high", skip_render=False, resume=True,
          log=None, limit=None, formats=("short",), tts_engine="vibevoice"):
    """Run many shorts one by one. `briefs` is a list of dicts:
    {slug, topic, audience?, tone?, notes?, theme?, script? (path)}.

    Resumable: a slug whose MP4 already exists is skipped (resume=True). Every
    item's outcome lands in <root>/batch-ledger.jsonl and the summary is returned.
    Failures never stop the batch — they are named and the next item runs.
    """
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    ledger = root / "batch-ledger.jsonl"
    log = log or (lambda m: print(m, flush=True))
    results = []
    todo = briefs[:limit] if limit else briefs
    for i, b in enumerate(todo, 1):
        sh = Short(root, b["slug"])
        wrote_brief = False
        for fmt in formats:
            mp4 = sh.out / (sh.slug + (".mp4" if fmt == "short" else "-long.mp4"))
            if resume and mp4.exists():
                log("[%d/%d] %s/%s — already rendered, skipping" % (i, len(todo), sh.slug, fmt))
                results.append({"slug": sh.slug, "format": fmt, "outcome": "skipped", "mp4": str(mp4)})
                continue
            log("[%d/%d] %s/%s — %s" % (i, len(todo), sh.slug, fmt, b.get("topic", "")[:80]))
            try:
                topic = None if wrote_brief else b.get("topic")
                if fmt == "short":
                    out = once(sh, topic=topic, model=model, from_script=b.get("script"),
                               theme=b.get("theme"), quality=quality, skip_render=skip_render,
                               audience=b.get("audience"), tone=b.get("tone"), notes=b.get("notes"), mode=b.get("mode"))
                else:
                    out = long(sh, topic=topic, model=model, from_script=b.get("long_script"), tts_engine=tts_engine,
                               quality=quality, skip_render=skip_render,
                               audience=b.get("audience"), tone=b.get("tone"), notes=b.get("notes"), mode=b.get("mode"))
                wrote_brief = True
            except Exception as e:  # keep the batch alive; the ledger names it
                out = {"outcome": "error", "error": "%s: %s" % (type(e).__name__, e)}
            rec = {"utc": utc_now(), "slug": sh.slug, "format": fmt, "outcome": out.get("outcome"),
                   "mp4": out.get("mp4"), "duration": out.get("duration"), "findings": out.get("findings"),
                   "error": out.get("error")}
            with open(ledger, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            log("    → %s%s" % (rec["outcome"], (" (%ss)" % rec["duration"]) if rec.get("duration") else ""))
            results.append(rec)
    summary = {"total": len(todo)}
    for r in results:
        summary[r["outcome"]] = summary.get(r["outcome"], 0) + 1
    write_json(root / "batch-summary.json", {"utc": utc_now(), "summary": summary, "results": results})
    return summary, results


# ── long-form (16:9, narrated) ────────────────────────────────────────────────

def long_script(short, model="claude-opus-5", timeout=900, attempts=3, runner=None, from_file=None):
    from .long import lint_long, write_long_script
    path = short.dir / "LONG.json"
    if from_file:
        doc = read_json(from_file)
        if not isinstance(doc, dict):
            raise ValueError("--long-script file is not JSON")
        findings = lint_long(doc)
        if findings:
            short.record("long.script.refused", {"source": str(from_file), "findings": findings})
            return None, findings
        write_json(path, doc)
        short.record("long.script", {"source": str(from_file), "sha256": sha256_file(path), "sections": len(doc["sections"])})
        return doc, []
    b = read_json(short.dir / "brief.json") or {"topic": short.slug}
    if b.get("mode") == "solution":
        from .long import write_solution_script
        doc, findings, log = write_solution_script(b, model=model, timeout=timeout, attempts=attempts, runner=runner,
                                                   drafts_dir=short.dir / "drafts")
    else:
        doc, findings, log = write_long_script(b, model=model, timeout=timeout, attempts=attempts, runner=runner,
                                               drafts_dir=short.dir / "drafts")
    if doc is None:
        short.record("long.script.failed", {"model": model, "attempts": len(log), "findings": findings})
        return None, findings
    # brief-level presentation hints ride into the script (never into the model's facts)
    for key in ("brand", "chip", "agent_name"):
        if b.get(key):
            doc[key] = b[key]
    if b.get("agent_name"):
        for sec in doc.get("sections") or []:
            if isinstance(sec, dict) and sec.get("kind") in ("turn", "slide", "close") and not sec.get("agent_name"):
                sec["agent_name"] = b["agent_name"]
                if sec.get("kind") == "slide" and (doc.get("brand") or {}).get("name"):
                    sec["brand"] = doc["brand"]["name"]
    write_json(path, doc)
    short.record("long.script", {"model": model, "attempts": len(log), "sha256": sha256_file(path),
                                 "sections": len(doc["sections"]), "narration_words": sum(
                                     len((s.get("narration") or "").split()) for s in doc["sections"])})
    return doc, []


def narrate(short, engine="vibevoice", timeout=900):
    """Per-section TTS → one narration.wav in project/assets + measured spans.
    Returns (spans|None, detail). engine='none' skips (durations derived)."""
    from . import tts
    doc = read_json(short.dir / "LONG.json")
    if not doc:
        raise ValueError("no LONG.json — run `long-script` first")
    if engine == "none":
        short.record("narrate", {"engine": "none"})
        return None, "no narration (durations derived from words)"
    if not tts.vibevoice_available():
        short.record("narrate.failed", {"engine": engine, "error": "VibeVoice not available"})
        return None, "VibeVoice not available; composing without voice"
    work = short.dir / "drafts" / "tts"
    work.mkdir(parents=True, exist_ok=True)
    parts = []
    for i, s in enumerate(doc["sections"], 1):
        wav = work / ("section-%02d.wav" % i)
        cache_key = work / ("section-%02d.txt" % i)
        text = (s.get("narration") or "").strip()
        if wav.exists() and cache_key.exists() and cache_key.read_text(encoding="utf-8").strip() == text:
            parts.append(wav); continue                      # resume: same text, same wav
        if not text:                                          # a silent beat (title card): 3.5 s of silence
            _run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", "3.5", str(wav)], work, 60)
            cache_key.write_text("\n", encoding="utf-8"); parts.append(wav); continue
        ok, detail = tts.synthesize(text, wav, work / ("w%02d" % i), timeout=timeout)
        if not ok:
            short.record("narrate.failed", {"engine": engine, "section": i, "error": detail})
            return None, "section %d: %s" % (i, detail)
        cache_key.write_text(text + "\n", encoding="utf-8")
        parts.append(wav)
    (short.project / "assets").mkdir(parents=True, exist_ok=True)
    out = short.project / "assets" / "narration.wav"
    spans = tts.concat_wavs(parts, out)
    if not spans:
        short.record("narrate.failed", {"engine": engine, "error": "concat failed (ffmpeg?)"})
        return None, "concat failed"
    write_json(short.dir / "state" / "narration-spans.json", {"engine": engine, "voice": tts.vibevoice_config()["voice"],
                                                              "spans": spans, "wav_sha256": sha256_file(out)})
    short.record("narrate", {"engine": engine, "voice": tts.vibevoice_config()["voice"], "sections": len(parts),
                             "seconds": round(spans[-1][0] + spans[-1][1], 2), "wav_sha256": sha256_file(out)})
    return spans, str(out)


def compose_long_project(short, fps=30):
    from .compose_long import compose_long
    from .long import lint_long
    doc = read_json(short.dir / "LONG.json")
    if not doc:
        raise ValueError("no LONG.json for %s" % short.slug)
    findings = lint_long(doc)
    if findings:
        raise ValueError("LONG.json does not pass lint: " + "; ".join(findings[:5]))
    spans_doc = read_json(short.dir / "state" / "narration-spans.json") or {}
    spans = [tuple(x) for x in spans_doc.get("spans", [])] or None
    audio_rel = "assets/narration.wav" if spans and (short.project / "assets" / "narration.wav").exists() else None
    files = compose_long(doc, short.slug, spans=spans, audio_rel=audio_rel, fps=fps)
    proj = short.dir / "project-long"
    proj.mkdir(exist_ok=True)
    (proj / "assets").mkdir(exist_ok=True)
    if audio_rel:
        import shutil as _sh
        _sh.copy2(short.project / "assets" / "narration.wav", proj / "assets" / "narration.wav")
    write_text(proj / "index.html", files["index.html"])
    write_text(proj / "package.json", package_json(short.slug + "-long", cli_version()))
    write_text(proj / "hyperframes.json", json.dumps({
        "$schema": "https://hyperframes.heygen.com/schema/hyperframes.json",
        "registry": "https://raw.githubusercontent.com/heygen-com/hyperframes/main/registry",
        "paths": {"blocks": "compositions", "components": "compositions/components", "assets": "assets"},
        "media": {"autoProxy": True}}, indent=2) + "\n")
    write_text(proj / "meta.json", json.dumps({"id": short.slug + "-long", "name": doc.get("title", short.slug),
                                               "duration": files["duration"], "fps": fps,
                                               "narrated": bool(audio_rel)}, indent=2) + "\n")
    sha = sha256_file(proj / "index.html")
    short.record("long.compose", {"index_sha256": sha, "duration": files["duration"], "captions": files["captions"],
                                  "narrated": bool(audio_rel)})
    return {"index": str(proj / "index.html"), "duration": files["duration"], "narrated": bool(audio_rel), "index_sha256": sha}


def check_long(short, timeout=1200):
    proj = short.dir / "project-long"
    rc, out = _run(hf_argv("check"), proj, timeout)
    report = short.dir / "state" / "check-long.txt"
    write_text(report, out)
    ok = rc == 0
    short.record("long.check", {"ok": ok, "exit": rc, "report_sha256": sha256_file(report)})
    return ok, out[-1200:], str(report)


def render_long(short, quality="high", timeout=3600):
    proj = short.dir / "project-long"
    out_mp4 = short.out / (short.slug + "-long.mp4")
    rc, out = _run(hf_argv("render", "--quality", quality, "--output", str(out_mp4)), proj, timeout)
    write_text(short.dir / "state" / "render-long.txt", out)
    ok = rc == 0 and out_mp4.exists() and out_mp4.stat().st_size > 0
    rec = {"ok": ok, "exit": rc, "quality": quality}
    if ok:
        rec["mp4_sha256"] = sha256_file(out_mp4); rec["mp4_bytes"] = out_mp4.stat().st_size
        if shutil.which("ffprobe"):
            rc2, o2 = _run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height,duration",
                            "-of", "json", str(out_mp4)], short.out, 60)
            try:
                st = json.loads(o2)["streams"]
                rec["probe"] = {"streams": [x.get("codec_type") for x in st],
                                "video": next(({k: x.get(k) for k in ("width", "height", "duration")} for x in st if x.get("codec_type") == "video"), None)}
            except Exception:
                pass
        if shutil.which("ffmpeg"):
            poster = short.out / "poster-long.png"
            _run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "2.0", "-i", str(out_mp4), "-frames:v", "1", str(poster)], short.out, 120)
    short.record("long.render" if ok else "long.render.failed", rec)
    rec.update({"mp4": str(out_mp4) if ok else None, "log_tail": out[-800:]})
    return rec


def long(short, topic=None, model="claude-opus-5", from_script=None, tts_engine="vibevoice", quality="high",
         skip_render=False, runner=None, **brief_kw):
    """The long-form chain: (brief) → LONG.json → narration → compose → check → render."""
    if topic:
        brief(short, topic, **brief_kw)
    doc, findings = long_script(short, model=model, runner=runner, from_file=from_script)
    if doc is None:
        return {"outcome": "long_script_failed", "findings": findings}
    spans, detail = narrate(short, engine=tts_engine)
    comp = compose_long_project(short)
    ok, summary, report = check_long(short)
    if not ok:
        return {"outcome": "long_check_failed", "report": report, "summary": summary, **comp}
    if skip_render:
        return {"outcome": "long_composed", "check": "ok", "narration": detail, **comp}
    r = render_long(short, quality=quality)
    if not r["ok"]:
        return {"outcome": "long_render_failed", "log_tail": r["log_tail"], **comp}
    return {"outcome": "long_rendered", "mp4": r["mp4"], "mp4_sha256": r["mp4_sha256"], "probe": r.get("probe"),
            "narration": detail, **comp}
