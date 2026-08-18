"""long.py — the long-form (16:9, narrated, faceless) script contract, prompt and lint.

A long-form script is a list of SECTIONS. Each carries the narration the voice
reads (40–95 words), a heading, and a visual the compiler knows how to animate:

  cold_open  title card — the hook                       visual: {type:"title", lines:[tagline]}
  explain    heading + 3–4 bullets revealed as it talks  visual: {type:"bullets", items:[...]}
  steps      a numbered flow, 3–5 items                  visual: {type:"steps", items:[...]}
  example    a worked exchange, 2–4 turns                visual: {type:"dialogue", turns:[{who:"user"|"agent", text}]}
  stat       one big figure                              visual: {type:"stat", value:"70%", caption:"..."}
  fit        where it fits — 3–4 cards                   visual: {type:"cards", items:[{title, text}]}
  install    how to get it — a terminal card             visual: {type:"terminal", lines:[...]}
  outro      close + call to action                      visual: {type:"title", lines:[...]}

Timing is never authored. When narration is synthesized, every section is as long
as its audio really is (ffprobe), plus a beat; without a voice, words/2.6 + a hold.
"""

import json
import re

from . import SCHEMA_SCRIPT  # noqa: F401  (kept for parity)
from .script import BLOCKED, extract_json, run_copilot, word_count

SCHEMA_LONG = "rapp-education-long/1.0"
KINDS = ("cold_open", "explain", "steps", "example", "stat", "fit", "install", "outro")
MIN_SECTIONS, MAX_SECTIONS = 6, 10
MIN_NARR_WORDS, MAX_NARR_WORDS = 30, 95
MIN_TOTAL_WORDS, MAX_TOTAL_WORDS = 300, 700
SPEECH_WPS = 2.6
HOLD_S = 1.4


def lint_long(doc):
    f = []
    if not isinstance(doc, dict):
        return ["script is not an object"]
    if doc.get("schema") != SCHEMA_LONG:
        f.append("schema must be %s" % SCHEMA_LONG)
    if not isinstance(doc.get("title"), str) or not doc["title"].strip():
        f.append("title missing")
    secs = doc.get("sections")
    if not isinstance(secs, list):
        return f + ["sections must be a list"]
    if not (MIN_SECTIONS <= len(secs) <= MAX_SECTIONS):
        f.append("section count %d outside %d-%d" % (len(secs), MIN_SECTIONS, MAX_SECTIONS))
    if secs and (secs[0].get("kind") != "cold_open"):
        f.append("section 1 must be cold_open")
    if secs and (secs[-1].get("kind") != "outro"):
        f.append("last section must be outro")
    total = 0
    corpus = [str(doc.get("title", "")), str(doc.get("tagline", ""))]
    for i, s in enumerate(secs, 1):
        if not isinstance(s, dict):
            f.append("section %d is not an object" % i)
            continue
        k = s.get("kind")
        if k not in KINDS:
            f.append("section %d kind %r not in %s" % (i, k, KINDS))
        h = s.get("heading")
        if not isinstance(h, str) or not h.strip():
            f.append("section %d heading missing" % i)
        elif len(h) > 48:
            f.append("section %d heading over 48 chars: \"%s\"" % (i, h[:60]))
        n = s.get("narration")
        wc = word_count(n) if isinstance(n, str) else 0
        total += wc
        if not isinstance(n, str) or not n.strip():
            f.append("section %d narration missing" % i)
        elif not (MIN_NARR_WORDS <= wc <= MAX_NARR_WORDS):
            f.append("section %d narration has %d words (need %d-%d)" % (i, wc, MIN_NARR_WORDS, MAX_NARR_WORDS))
        v = s.get("visual") or {}
        if not isinstance(v, dict):
            f.append("section %d visual must be an object" % i)
            v = {}
        vt = v.get("type")
        need = {"cold_open": "title", "explain": "bullets", "steps": "steps", "example": "dialogue",
                "stat": "stat", "fit": "cards", "install": "terminal", "outro": "title"}.get(k)
        if need and vt != need:
            f.append("section %d (%s) needs visual.type=%s" % (i, k, need))
        if vt in ("bullets", "steps", "terminal"):
            items = v.get("items") if vt != "terminal" else v.get("lines")
            lo, hi = (3, 4) if vt == "bullets" else (3, 5) if vt == "steps" else (1, 6)
            if not isinstance(items, list) or not (lo <= len(items) <= hi) or not all(isinstance(x, str) and x.strip() for x in items):
                f.append("section %d visual %s needs %d-%d text items" % (i, vt, lo, hi))
            elif vt != "terminal" and any(word_count(x) > 12 for x in items):
                f.append("section %d has an item over 12 words" % i)
        if vt == "title":
            lines = v.get("lines")
            if not isinstance(lines, list) or not (1 <= len(lines) <= 2):
                f.append("section %d title visual needs 1-2 lines" % i)
        if vt == "dialogue":
            turns = v.get("turns")
            if not isinstance(turns, list) or not (2 <= len(turns) <= 4) or not all(
                    isinstance(t, dict) and t.get("who") in ("user", "agent") and isinstance(t.get("text"), str) for t in turns):
                f.append("section %d dialogue needs 2-4 turns of {who:user|agent,text}" % i)
            elif any(word_count(t["text"]) > 40 for t in turns):
                f.append("section %d has a dialogue turn over 40 words" % i)
        if vt == "stat":
            if not re.match(r"^[\d.,]+[%xKMB+]?$", str(v.get("value", ""))) or not v.get("caption"):
                f.append("section %d stat needs a numeric value and caption" % i)
        if vt == "cards":
            items = v.get("items")
            if not isinstance(items, list) or not (3 <= len(items) <= 4) or not all(
                    isinstance(c, dict) and c.get("title") and c.get("text") for c in items):
                f.append("section %d cards need 3-4 {title,text}" % i)
        # the terminal card is the one visual allowed to carry a URL/handle (how to get it)
        corpus += [str(h), str(n), "" if vt == "terminal" else json.dumps(v)]
    if secs and not (MIN_TOTAL_WORDS <= total <= MAX_TOTAL_WORDS):
        f.append("total narration %d words (need %d-%d)" % (total, MIN_TOTAL_WORDS, MAX_TOTAL_WORDS))
    low = " ".join(corpus).lower()
    hits = sorted({b for b in BLOCKED if b in low})
    if hits:
        f.append("blocked tokens present: %s" % ", ".join(hits))
    return f


def section_seconds(sec):
    return round(max(6.0, word_count(sec.get("narration", "")) / SPEECH_WPS + HOLD_S), 2)


PROMPT = """You write faceless, narrated explainer videos for YouTube (3–4 minutes, 16:9). A calm,
knowledgeable narrator reads your narration while clean animated text and cards appear on screen.

TOPIC: {topic}
AUDIENCE: {audience}
TONE: {tone}
{extra}
YOU HAVE NO TOOLS. Do not run commands or create files. Reply with ONLY a JSON object.

Write {lo}–{hi} sections. Section 1 is a "cold_open" (a hook the viewer cannot skip past);
the last is an "outro" (a warm close and one clear next step). In between, teach: what it is,
the problem it solves, how it works (steps), a concrete worked example (dialogue), where it
fits (cards), and how to get it (install). Narration per section: 40–95 words, spoken English —
short sentences, no bullet-speak, no URLs read aloud, no exaggerated claims. The on-screen
visual for each section is what a viewer reads while listening: keep items short.
Do not invent capabilities, numbers, customers or names beyond the notes. Total narration
{tlo}–{thi} words. Headings ≤ 48 chars.

Return exactly this shape (only the kinds you need, in a sensible order):
{{"schema": "{schema}", "title": "...", "tagline": "...", "chip": "1-3 word series label",
 "sections": [
  {{"kind": "cold_open", "heading": "...", "narration": "...", "visual": {{"type": "title", "lines": ["one-line tagline"]}}}},
  {{"kind": "explain", "heading": "What it is", "narration": "...", "visual": {{"type": "bullets", "items": ["...", "...", "..."]}}}},
  {{"kind": "steps", "heading": "How it works", "narration": "...", "visual": {{"type": "steps", "items": ["...", "...", "..."]}}}},
  {{"kind": "example", "heading": "A worked example", "narration": "...", "visual": {{"type": "dialogue", "turns": [{{"who": "user", "text": "..."}}, {{"who": "agent", "text": "..."}}]}}}},
  {{"kind": "stat", "heading": "...", "narration": "...", "visual": {{"type": "stat", "value": "3x", "caption": "..."}}}},
  {{"kind": "fit", "heading": "Where it fits", "narration": "...", "visual": {{"type": "cards", "items": [{{"title": "...", "text": "..."}}, {{"title": "...", "text": "..."}}, {{"title": "...", "text": "..."}}]}}}},
  {{"kind": "install", "heading": "How to get it", "narration": "...", "visual": {{"type": "terminal", "lines": ["$ ...", "..."]}}}},
  {{"kind": "outro", "heading": "...", "narration": "...", "visual": {{"type": "title", "lines": ["...", "..."]}}}}
 ]}}{feedback}"""


def build_prompt(brief, feedback=None):
    fb = ""
    if feedback:
        fb = ("\n\nYOUR PREVIOUS ATTEMPT WAS REFUSED — fix every one of these:\n- " + "\n- ".join(feedback[:12])
              + "\nReply with ONLY the JSON object.")
    return PROMPT.format(topic=brief["topic"], audience=brief.get("audience") or "curious general viewers",
                         tone=brief.get("tone") or "calm, clear, concrete, a little warm",
                         extra=("NOTES: " + brief["notes"] + "\n") if brief.get("notes") else "",
                         lo=7, hi=9, tlo=MIN_TOTAL_WORDS + 60, thi=MAX_TOTAL_WORDS - 60, schema=SCHEMA_LONG, feedback=fb)


def write_long_script(brief, model="claude-opus-5", timeout=900, attempts=3, runner=None, drafts_dir=None):
    from pathlib import Path
    runner = runner or run_copilot
    drafts_dir = Path(drafts_dir or ".")
    feedback, log = None, []
    for n in range(1, attempts + 1):
        text, err = runner(build_prompt(brief, feedback), model, timeout, drafts_dir)
        try:
            (drafts_dir / ("long-attempt-%d.txt" % n)).write_text(text or ("ERROR: %s\n" % err), encoding="utf-8")
        except Exception:
            pass
        if err:
            log.append({"n": n, "error": err}); feedback = ["the model call failed: %s" % err]; continue
        doc = extract_json(text)
        if not isinstance(doc, dict):
            log.append({"n": n, "error": "no JSON object in output"}); feedback = ["return only the JSON object"]; continue
        doc.setdefault("schema", SCHEMA_LONG)
        findings = lint_long(doc)
        log.append({"n": n, "findings": findings})
        if not findings:
            return doc, [], log
        feedback = findings
    last = log[-1] if log else {}
    return None, last.get("findings") or [last.get("error", "unknown")], log


def caption_chunks(text, max_words=11):
    """Sentence-aware caption chunks for the band; each ≤ max_words."""
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if s.strip()]
    out = []
    for s in sents:
        words = s.split()
        while words:
            take = words[:max_words]
            if len(words) > max_words and len(words) - max_words < 4:   # avoid a 1–3 word orphan
                take = words[:len(words) // 2]
            out.append(" ".join(take))
            words = words[len(take):]
    return out
