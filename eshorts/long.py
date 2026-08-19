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
KINDS = ("cold_open", "explain", "steps", "example", "stat", "fit", "install", "outro", "workbook", "slide", "diff", "media",
         # solution-mode spine (the industry-video template): what the viewer gets, never how it is built
         "title", "problem", "overview", "turn", "outcomes", "close")
SOLUTION_KINDS = ("title", "problem", "overview", "turn", "outcomes", "close",
                  # artifact and closed-loop kinds (what the hand-made films show, rendered from the agent's own numbers)
                  "workbook", "slide", "diff", "media")
MIN_SECTIONS, MAX_SECTIONS = 6, 16
MIN_NARR_WORDS, MAX_NARR_WORDS = 20, 95
MIN_TOTAL_WORDS, MAX_TOTAL_WORDS = 300, 800
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
    solution = bool(secs) and any(isinstance(x, dict) and x.get("kind") in SOLUTION_KINDS for x in secs)
    if secs and not solution and (secs[0].get("kind") != "cold_open"):
        f.append("section 1 must be cold_open")
    if secs and not solution and (secs[-1].get("kind") != "outro"):
        f.append("last section must be outro")
    if solution:
        kinds = [x.get("kind") for x in secs if isinstance(x, dict)]
        if kinds[:1] != ["title"]:
            f.append("solution mode: section 1 must be a silent 'title'")
        if kinds[-1:] != ["close"]:
            f.append("solution mode: last section must be 'close'")
        if kinds.count("turn") < 3:
            f.append("solution mode: need at least 3 'turn' sections (the walkthrough)")
        for must in ("problem", "overview", "outcomes"):
            if must not in kinds:
                f.append("solution mode: missing a '%s' section" % must)
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
        if k == "title":
            if wc:
                f.append("section %d (title) must be silent — no narration" % i)
        elif not isinstance(n, str) or not n.strip():
            f.append("section %d narration missing" % i)
        elif not (MIN_NARR_WORDS <= wc <= MAX_NARR_WORDS):
            f.append("section %d narration has %d words (need %d-%d)" % (i, wc, MIN_NARR_WORDS, MAX_NARR_WORDS))
        v = s.get("visual") or {}
        if not isinstance(v, dict):
            f.append("section %d visual must be an object" % i)
            v = {}
        vt = v.get("type")
        need = {"cold_open": "title", "explain": "bullets", "steps": "steps", "example": "dialogue",
                "stat": "stat", "fit": "cards", "install": "terminal", "outro": "title",
                "title": "titlecard", "problem": "pain", "overview": "triptych", "turn": "chat",
                "outcomes": "tiles", "close": "cta", "workbook": "workbook", "slide": "slide", "diff": "diff",
                "media": "media"}.get(k)
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
        if vt == "titlecard":
            if not v.get("name") or not v.get("kicker"):
                f.append("section %d titlecard needs name and kicker" % i)
        if vt == "pain":
            items = v.get("items")
            if not v.get("persona") or not isinstance(items, list) or not (2 <= len(items) <= 3) or any(word_count(x) > 12 for x in items):
                f.append("section %d pain needs persona and 2-3 items (≤12 words)" % i)
        if vt == "triptych":
            for col in ("sources", "flow", "actions"):
                col_items = v.get(col)
                if not isinstance(col_items, list) or not (1 <= len(col_items) <= 4) or any(word_count(x) > 8 for x in col_items):
                    f.append("section %d triptych.%s needs 1-4 items (≤8 words)" % (i, col))
        if vt == "chat":
            if not v.get("prompt") or word_count(v.get("prompt", "")) > 22:
                f.append("section %d chat needs a prompt (≤22 words)" % i)
            r = v.get("response") or {}
            if not isinstance(r, dict) or not r.get("lead"):
                f.append("section %d chat.response needs a lead line" % i)
            tbl = r.get("table") if isinstance(r, dict) else None
            if tbl is not None:
                if not (isinstance(tbl, dict) and isinstance(tbl.get("headers"), list) and 2 <= len(tbl["headers"]) <= 5
                        and isinstance(tbl.get("rows"), list) and 2 <= len(tbl["rows"]) <= 5
                        and all(isinstance(rw, list) and len(rw) == len(tbl["headers"]) for rw in tbl["rows"])):
                    f.append("section %d chat.response.table needs 2-5 headers and 2-5 rows of equal width" % i)
            bl = r.get("bullets") if isinstance(r, dict) else None
            if bl is not None and (not isinstance(bl, list) or not (1 <= len(bl) <= 4) or any(word_count(x) > 14 for x in bl)):
                f.append("section %d chat.response.bullets needs 1-4 items (≤14 words)" % i)
            if not v.get("benefit") or word_count(v.get("benefit", "")) > 18:
                f.append("section %d chat needs a benefit line (≤18 words)" % i)
            lk = v.get("links")
            if lk is not None and (not isinstance(lk, list) or len(lk) > 5 or not all(isinstance(x, str) for x in lk)):
                f.append("section %d chat.links must be up to 5 strings" % i)
        if vt == "workbook":
            secs_ = v.get("sections")
            if not v.get("title") or not isinstance(secs_, list) or not (1 <= len(secs_) <= 5):
                f.append("section %d workbook needs title and 1-5 sections" % i)
            else:
                for sec_ in secs_:
                    if not (isinstance(sec_, dict) and sec_.get("name") and isinstance(sec_.get("rows"), list) and 1 <= len(sec_["rows"]) <= 6
                            and all(isinstance(rw, list) and 2 <= len(rw) <= 5 for rw in sec_["rows"])):
                        f.append("section %d workbook sections need name and 1-6 rows of 2-5 cells" % i); break
            pr = v.get("progress")
            if pr is not None and not (isinstance(pr, dict) and isinstance(pr.get("step"), int) and isinstance(pr.get("total"), int)):
                f.append("section %d workbook.progress needs {step,total} ints" % i)
        if vt == "slide":
            kp = v.get("kpis") or []
            ch = v.get("chart") or {}
            if not v.get("title") or not (1 <= len(kp) <= 4) or not all(isinstance(x, dict) and x.get("label") and x.get("value") is not None for x in kp):
                f.append("section %d slide needs title and 1-4 kpis {label,value}" % i)
            if ch:
                items_ = ch.get("items")
                if ch.get("type") not in ("bars", "waterfall") or not isinstance(items_, list) or not (2 <= len(items_) <= 9) \
                        or not all(isinstance(x, dict) and x.get("label") and isinstance(x.get("value"), (int, float)) for x in items_):
                    f.append("section %d slide.chart needs type bars|waterfall and 2-9 numeric items" % i)
        if vt == "diff":
            items_ = v.get("items")
            if not isinstance(items_, list) or not (1 <= len(items_) <= 4) or not all(
                    isinstance(x, dict) and x.get("label") and x.get("before") is not None and x.get("after") is not None for x in items_):
                f.append("section %d diff needs 1-4 items {label,before,after}" % i)
        if vt == "media":
            if not v.get("src") or v.get("kind") not in ("image", "video"):
                f.append("section %d media needs src and kind image|video" % i)
        if vt == "tiles":
            items = v.get("items")
            if not isinstance(items, list) or len(items) != 3 or any(word_count(x) > 5 for x in items):
                f.append("section %d tiles need exactly 3 items (≤5 words)" % i)
        if vt == "cta":
            if not v.get("summary") or not v.get("cta"):
                f.append("section %d cta needs summary and cta" % i)
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


# ── solution mode: the industry-video template ───────────────────────────────

SOLUTION_PROMPT = """You write narrated, faceless solution videos (2:30–3:20, 16:9) in the style of enterprise product
explainers: a calm narrator, clean animated cards, and a worked walkthrough of real prompts and answers.
The video is about THE SOLUTION and what the persona gets. It NEVER discusses how the agent is built,
packaged, installed, downloaded or where its code lives. Never say: RAPP, agent.py, brainstem, RAR,
registry, single file, install, GitHub, curl, python, repo, open source.

TOPIC: {topic}
AUDIENCE: {audience}
TONE: {tone}
GROUNDING (use ONLY facts, names, numbers, prompts and answers from here):
{notes}

YOU HAVE NO TOOLS. Reply with ONLY a JSON object.

Structure — exactly this order (every section object has "kind", "heading", "narration", "visual"):
 1. kind "title"    silent title card (no narration): visual {{"type":"titlecard","name":"<advertised name>","kicker":"<industry or 'Cross-industry'> · Copilot agent"}}
 2. kind "problem"  15–20 s: the persona and the pain (narration 40–65 words, e.g. "Sellers face … Yet account research often means …");
               visual {{"type":"pain","persona":"<role>","items":["<pain 1>","<pain 2>","<pain 3>"]}}
 3. kind "overview" "Now an agent can …" (narration 45–70 words naming the Microsoft products);
               visual {{"type":"triptych","sources":["Dynamics 365","SharePoint"],"flow":["Microsoft Teams","Copilot experience"],"actions":["<verb phrase>","<verb phrase>","<verb phrase>"]}}
 4–9. three to six kind "turn" sections (artifact sections may sit between them) — the walkthrough. Each turn: heading = what the persona asks for (≤48 chars);
       narration 35–70 words: "Imagine a <persona> who … The agent …" then one benefit sentence
       ("Insights that once required hours are available in seconds."). Visual:
       {{"type":"chat","prompt":"<the real prompt as the persona would type it, ≤22 words — drop qualifiers like 'synthetic'>",
         "response":{{"lead":"<one-line summary of the real answer>",
                      "table":{{"headers":["..",".."],"rows":[["..",".."],["..",".."]]}}  (optional, from the AGENT TABLES, 2–5 rows),
                      "bullets":["..",".."]}} (optional, 1–4, from the real answer),
         "benefit":"<≤18 words>"}}
       Use "Going further, …" / "Next, …" / "When the <persona> is ready, …" transitions like a guided workflow;
       include a Teams or Outlook hand-off beat if the grounding has one.
 Between turns you MAY add artifact sections that SHOW what the turn produced, built only from numbers in the grounding:
   kind "workbook" — a color-coded live review sheet: visual {{"type":"workbook","title":"...","progress":{{"step":2,"total":6}},
        "sections":[{{"name":"2 · Reconcile comparisons","color":"blue","headers":["Item","Value","Owner","Action"],"rows":[["..","..","..",".."]]}}]}}
        (colors: blue, amber, red, purple, green, gray — one section per step the conversation has reached)
   kind "slide"    — an executive slide: visual {{"type":"slide","kicker":"BUDGET COMPARISON","title":"<the slide headline>",
        "kpis":[{{"label":"Current Estimate","value":"$1,000.0","tag":"provisional"}}],
        "chart":{{"type":"bars"|"waterfall","items":[{{"label":"Price","value":10.0}}],"unit":"USD millions"}},"footer":"<review gate / caveat>"}}
   kind "diff"     — the closed loop after a correction: visual {{"type":"diff","items":[{{"label":"Budget residual","before":0.5,"after":0.0,"unit":"USD millions"}}]}}
   Each artifact section has its own heading and 25–55 words of narration. Use 2–4 artifact sections in total.
   Chat turns may also carry: "agent_call":"<specialist name if the answer names one>", "review_line":"<the answer's human-review sentence>",
   "links":["Open Excel review pack","Open editable PowerPoint"] (only if the answer offered them).
 8. kind "outcomes" "How the agent helps": narration 35–60 words summarising value; visual {{"type":"tiles","items":["<≤5 words>","<≤5 words>","<≤5 words>"]}}
 9. kind "close"    narration 25–45 words: one-sentence summary + "Get started on your agentic journey today."
               visual {{"type":"cta","summary":"<one line>","cta":"Explore the AIBAST Agents Library"}}
Narration is spoken English: short sentences, product names spoken naturally, no bullet-speak, no URLs.
Total narration {tlo}–{thi} words. Headings ≤ 48 chars.

Return exactly: {{"schema":"{schema}","title":"<advertised name>","tagline":"<one line>","chip":"<series or customer label>",
 "sections":[{{"kind":"title","heading":"...","narration":"","visual":{{...}}}}, {{"kind":"problem", ...}}, …]}}{feedback}"""


def build_solution_prompt(brief, feedback=None):
    fb = ""
    if feedback:
        fb = ("\n\nYOUR PREVIOUS ATTEMPT WAS REFUSED — fix every one of these:\n- " + "\n- ".join(feedback[:12])
              + "\nReply with ONLY the JSON object.")
    return SOLUTION_PROMPT.format(topic=brief["topic"], audience=brief.get("audience") or "business decision makers",
                                  tone=brief.get("tone") or "calm, confident, concrete", notes=brief.get("notes") or "",
                                  tlo=330, thi=600, schema=SCHEMA_LONG, feedback=fb)


def lint_solution(doc):
    """lint_long plus the solution-mode vocabulary gate."""
    f = lint_long(doc)
    try:
        from .aibast import forbidden_hits
    except Exception:  # pragma: no cover
        return f
    spoken = " ".join([str(doc.get("title", "")), str(doc.get("tagline", ""))] +
                      [str(s.get("heading", "")) + " " + str(s.get("narration", "")) + " " + json.dumps(s.get("visual") or {})
                       for s in (doc.get("sections") or []) if isinstance(s, dict)])
    hits = [h for h in forbidden_hits(spoken) if h not in ("registry",) or "Registry" in spoken]
    if hits:
        f.append("the video must not mention how the agent is built/installed — remove: %s" % ", ".join(hits))
    return f


def write_solution_script(brief, model="claude-opus-5", timeout=900, attempts=3, runner=None, drafts_dir=None):
    from pathlib import Path
    runner = runner or run_copilot
    drafts_dir = Path(drafts_dir or ".")
    feedback, log = None, []
    for n in range(1, attempts + 1):
        text, err = runner(build_solution_prompt(brief, feedback), model, timeout, drafts_dir)
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
        doc["mode"] = "solution"
        for sec in doc.get("sections") or []:            # tolerate "id"/"type" as the kind alias
            if isinstance(sec, dict) and not sec.get("kind"):
                sec["kind"] = sec.get("id") or sec.get("type")
        findings = lint_solution(doc)
        log.append({"n": n, "findings": findings})
        if not findings:
            return doc, [], log
        feedback = findings
    last = log[-1] if log else {}
    return None, last.get("findings") or [last.get("error", "unknown")], log
