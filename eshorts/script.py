"""script.py — the SCRIPT.json contract, the model prompt, and the lint gate.

A script is a list of SCENES. Each scene has a kind, a heading, up to three short
lines, an optional visual, and the words to emphasise. The compiler turns kinds
into motion; the writer only decides what to say. Timing is derived, not
authored: on-screen reading pace × words + a hold, clamped per scene, capped to
a Short. If the model authored the timing it would lie about it.

Kinds and what the compiler does with them:
  hook     — big kinetic slam of the hook line, then a subtitle
  point    — heading + 1–3 lines, staggered in
  steps    — numbered chips with a drawn connector (a process)
  compare  — two cards, this vs that
  number   — one big count-up figure with a caption (a stat)
  quote    — a pull-quote with big marks
  recap    — 2–4 bullets stacking up
  cta      — closing line + a pill (follow / next video / question)
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

from . import SCENE_KINDS, SCHEMA_SCRIPT

READ_WPS = 2.4            # words per second a viewer reads on-screen text comfortably
HOLD_S = 1.2              # per-scene settle/hold beyond reading time
MIN_SCENE_S = 2.5
MAX_SCENE_S = 9.0
MAX_TOTAL_S = 59.0        # a Short
MIN_SCENES = 4
MAX_SCENES = 12
MAX_LINES = 3
MAX_LINE_WORDS = 12
MAX_TOTAL_WORDS = 110     # ≈ 45–55 s at READ_WPS with per-scene holds — the budget the model is told
MAX_HEADING_CHARS = 42
BLOCKED = ("http", "www.", ".com", "@", "kill", "suicide", "porn", "fuck", "shit")

_WORD = re.compile(r"[A-Za-z0-9''’%$-]+")


def word_count(text):
    return len(_WORD.findall(text or ""))


def scene_seconds(scene):
    words = word_count(scene.get("heading", "")) + sum(word_count(l) for l in scene.get("lines", []))
    v = scene.get("visual") or {}
    if v.get("type") == "steps":
        words += sum(word_count(s) for s in v.get("items", []))
    if v.get("type") == "compare":
        words += word_count(v.get("left", "")) + word_count(v.get("right", ""))
    if v.get("type") == "number":
        words += word_count(v.get("caption", "")) + 1
    sec = words / READ_WPS + HOLD_S
    if scene.get("kind") == "hook":
        sec = max(sec, 3.0)
    return round(max(MIN_SCENE_S, min(MAX_SCENE_S, sec)), 2)


def total_words(script):
    n = 0
    for s in script.get("scenes", []) or []:
        if not isinstance(s, dict):
            continue
        n += word_count(s.get("heading", "")) + sum(word_count(l) for l in (s.get("lines") or []) if isinstance(l, str))
        v = s.get("visual") or {}
        if isinstance(v, dict):
            n += sum(word_count(x) for x in (v.get("items") or []) if isinstance(x, str))
            n += sum(word_count(str(v.get(k, ""))) for k in ("left", "right", "caption", "text"))
    return n


def timeline(script):
    """Absolute start/duration per scene, and the total."""
    t, out = 0.0, []
    for s in script.get("scenes", []):
        d = scene_seconds(s)
        out.append({"start": round(t, 2), "duration": d})
        t += d
    return out, round(t, 2)


def lint_script(script):
    f = []
    if not isinstance(script, dict):
        return ["script is not an object"]
    if script.get("schema") != SCHEMA_SCRIPT:
        f.append("schema must be %s" % SCHEMA_SCRIPT)
    for key in ("title", "topic"):
        if not isinstance(script.get(key), str) or not script[key].strip():
            f.append("%s missing" % key)
    if isinstance(script.get("title"), str) and len(script["title"]) > 70:
        f.append("title over 70 chars")
    scenes = script.get("scenes")
    if not isinstance(scenes, list):
        return f + ["scenes must be a list"]
    if not (MIN_SCENES <= len(scenes) <= MAX_SCENES):
        f.append("scene count %d outside %d-%d" % (len(scenes), MIN_SCENES, MAX_SCENES))
    if scenes and scenes[0].get("kind") != "hook":
        f.append("scene 1 must be a hook")
    if scenes and scenes[-1].get("kind") not in ("cta", "recap"):
        f.append("last scene must be recap or cta")
    corpus = [str(script.get("title", "")), str(script.get("topic", ""))]
    for i, s in enumerate(scenes, 1):
        if not isinstance(s, dict):
            f.append("scene %d is not an object" % i)
            continue
        kind = s.get("kind")
        if kind not in SCENE_KINDS:
            f.append("scene %d kind %r not in %s" % (i, kind, SCENE_KINDS))
        h = s.get("heading")
        if not isinstance(h, str) or not h.strip():
            f.append("scene %d heading missing" % i)
        elif len(h) > MAX_HEADING_CHARS:
            f.append("scene %d heading over %d chars: \"%s\"" % (i, MAX_HEADING_CHARS, h[:60]))
        lines = s.get("lines", [])
        if not isinstance(lines, list) or len(lines) > MAX_LINES:
            f.append("scene %d must have 0-%d lines" % (i, MAX_LINES))
            lines = lines if isinstance(lines, list) else []
        for j, l in enumerate(lines, 1):
            if not isinstance(l, str) or not l.strip():
                f.append("scene %d line %d empty" % (i, j))
            elif word_count(l) > MAX_LINE_WORDS:
                f.append("scene %d line %d has %d words (max %d): \"%s\"" % (i, j, word_count(l), MAX_LINE_WORDS, l[:60]))
        v = s.get("visual") or {}
        if v and not isinstance(v, dict):
            f.append("scene %d visual must be an object" % i)
            v = {}
        vt = v.get("type")
        if kind == "steps":
            items = v.get("items")
            if vt != "steps" or not isinstance(items, list) or not (2 <= len(items) <= 5):
                f.append("scene %d (steps) needs visual.type=steps with 2-5 items" % i)
        if kind == "compare":
            if vt != "compare" or not v.get("left") or not v.get("right"):
                f.append("scene %d (compare) needs visual.type=compare with left/right" % i)
        if kind == "number":
            if vt != "number" or not re.match(r"^[\d.,]+[%xKMB+]?$", str(v.get("value", ""))) or not v.get("caption"):
                f.append("scene %d (number) needs visual.type=number with numeric value and caption" % i)
        emph = s.get("emphasis", [])
        if emph and (not isinstance(emph, list) or not all(isinstance(e, str) for e in emph)):
            f.append("scene %d emphasis must be a list of words" % i)
        corpus += [str(h), " ".join(str(l) for l in lines), json.dumps(v)]
    _, total = timeline(script) if isinstance(scenes, list) else ([], 0)
    if total > MAX_TOTAL_S:
        f.append("derived length %.1fs exceeds %.0fs: %d on-screen words in %d scenes — cut to under %d words total (fewer scenes or shorter lines)"
                 % (total, MAX_TOTAL_S, total_words(script), len(scenes), MAX_TOTAL_WORDS))
    low = " ".join(corpus).lower()
    hits = sorted({b for b in BLOCKED if b in low})
    if hits:
        f.append("blocked tokens present: %s" % ", ".join(hits))
    return f


# ── the model ────────────────────────────────────────────────────────────────

PROMPT = """You write scripts for 30–55 second educational YouTube Shorts: text-forward, animated,
watched with the sound OFF. Every word appears on screen, so fewer words win.

TOPIC: {topic}
AUDIENCE: {audience}
TONE: {tone}
{extra}
YOU HAVE NO TOOLS. Do not run commands or create files. Reply with ONLY a JSON object.

WORD BUDGET: at most {budget} words TOTAL across every heading, line, step, card, caption and pill —
a Short is under 60 seconds and every word is read on screen. Aim for 6 scenes and ~90 words.

Structure: 5–8 scenes. Scene 1 is a "hook" (one punchy line ≤ 9 words that creates a
question or a surprise; a subtitle line ≤ 10 words). Then 3–5 teaching scenes mixing kinds
("point", "steps", "compare", "number", "quote"). End with a "recap" (2–4 bullets) or a "cta"
(closing line + a short pill like "Follow for more" or a question to comment on).
Rules (machine-checked): headings ≤ 42 chars; each line ≤ 12 words; ≤ 3 lines per scene;
plain, concrete, correct; no URLs, handles or hashtags in text; no medical/legal advice.
Add 1–3 "emphasis" words per scene (exact words that appear in that scene's lines/heading).

Return exactly this shape:
{{"schema": "{schema}", "title": "...", "topic": "...", "audience": "...",
 "chip": "a 1-3 word series label shown top-left, e.g. Money basics",
 "hashtags": ["#..", "#..", "#.."],
 "scenes": [
   {{"kind": "hook", "heading": "...", "lines": ["subtitle"], "emphasis": ["word"]}},
   {{"kind": "point", "heading": "...", "lines": ["...", "..."], "emphasis": ["word"]}},
   {{"kind": "steps", "heading": "...", "lines": [], "visual": {{"type": "steps", "items": ["...", "...", "..."]}}, "emphasis": []}},
   {{"kind": "compare", "heading": "...", "lines": ["one line"], "visual": {{"type": "compare", "left": "...", "right": "..."}}, "emphasis": []}},
   {{"kind": "number", "heading": "...", "lines": [], "visual": {{"type": "number", "value": "70%", "caption": "..."}}, "emphasis": []}},
   {{"kind": "quote", "heading": "...", "lines": ["the quote", "— who"], "emphasis": []}},
   {{"kind": "recap", "heading": "...", "lines": ["...", "...", "..."], "emphasis": []}},
   {{"kind": "cta", "heading": "...", "lines": ["..."], "visual": {{"type": "pill", "text": "Follow for more"}}, "emphasis": []}}
 ]}}
Use only the kinds you need (5–8 scenes total).{feedback}"""


def build_prompt(brief, feedback=None):
    fb = ""
    if feedback:
        fb = ("\n\nYOUR PREVIOUS ATTEMPT WAS REFUSED — fix every one of these:\n- " + "\n- ".join(feedback[:12])
              + "\nReply with ONLY the JSON object.")
    return PROMPT.format(topic=brief["topic"], audience=brief.get("audience") or "curious general viewers",
                         tone=brief.get("tone") or "clear, warm, a little playful",
                         extra=("NOTES: " + brief["notes"] + "\n") if brief.get("notes") else "",
                         schema=SCHEMA_SCRIPT, feedback=fb, budget=MAX_TOTAL_WORDS)


def copilot_argv(prompt, model, workdir):
    return ["copilot", "-p", prompt, "--model", model, "--available-tools=",
            "--excluded-tools=create,edit,web_fetch",
            "--log-level", "none", "--log-dir", str(Path(workdir) / "copilot-logs")]


def run_copilot(prompt, model, timeout, workdir):
    """Default model runner: GitHub Copilot CLI with NO tools. Returns (text, error)."""
    if not shutil.which("copilot"):
        return "", "copilot CLI not on PATH (install GitHub Copilot CLI, or pass --script <file>)"
    Path(workdir).mkdir(parents=True, exist_ok=True)
    try:
        p = subprocess.run(copilot_argv(prompt, model, workdir), capture_output=True, text=True,
                           timeout=timeout, cwd=str(workdir), stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return "", "model timed out after %ss" % timeout
    if p.returncode != 0 and not p.stdout.strip():
        return "", "copilot exit %d: %s" % (p.returncode, (p.stderr or "")[-300:].strip())
    return p.stdout, None


def extract_json(text):
    if not text:
        return None
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.M)
    start = text.find("{")
    if start < 0:
        return None
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except Exception:
                    return None
    return None


def write_script(brief, model="claude-opus-5", timeout=600, attempts=3, runner=None, drafts_dir=None):
    """Ask the model for a script until lint accepts it. Returns (script|None, findings, attempt_log)."""
    runner = runner or run_copilot
    drafts_dir = Path(drafts_dir or ".")
    feedback, log = None, []
    for n in range(1, attempts + 1):
        text, err = runner(build_prompt(brief, feedback), model, timeout, drafts_dir)
        try:
            (drafts_dir / ("attempt-%d.txt" % n)).write_text(text or ("ERROR: %s\n" % err), encoding="utf-8")
        except Exception:
            pass
        if err:
            log.append({"n": n, "error": err})
            feedback = ["the model call failed: %s" % err]
            continue
        script = extract_json(text)
        if not isinstance(script, dict):
            log.append({"n": n, "error": "no JSON object in output"})
            feedback = ["you returned no valid JSON object; return only the JSON"]
            continue
        script.setdefault("schema", SCHEMA_SCRIPT)
        findings = lint_script(script)
        log.append({"n": n, "findings": findings})
        if not findings:
            return script, [], log
        feedback = findings
    last = log[-1] if log else {}
    return None, last.get("findings") or [last.get("error", "unknown")], log
