"""compose_long.py — long-form script (+ measured narration) → 1920×1080 HyperFrames project.

Visual language borrowed from the RAPP films (eight-ais-bar): near-black stage,
monospace type, amber + green accents, faint scanlines, a VO-synced caption band
at the bottom, and the narration WAV as its own <audio> clip on a high track.

Contract (hyperframes-core): standalone root, sized; every section a class="clip"
direct child on its own track slot; the caption band and audio are clips too; ONE
paused GSAP timeline on window.__timelines["long"], fromTo everywhere, finite
repeats, transforms/paint only, no CSS transitions on animated elements; the
stage fill is a full-bleed CHILD; captions are discrete tl.set() text states on a
non-clip span (the eight-ais-bar pattern).
"""

import html
import json
import re

from . import __version__
from .long import caption_chunks, section_seconds
from .script import word_count

W, H = 1920, 1080
COMP_ID = "long"
GSAP_CDN = "https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"
_e = html.escape


def timings(doc, spans=None, gap=0.45, lead=0.6, tail=1.2):
    """[{start, dur, vo_start, vo_dur}] per section. With spans (from the real WAV
    concat) each section wraps its audio; otherwise words/2.6 + hold."""
    out, t = [], lead
    for i, s in enumerate(doc["sections"]):
        if spans:
            vo_start, vo_dur = spans[i]
            start = round(lead + vo_start - 0.15, 3) if i else 0.0
            dur = round(vo_dur + gap + 0.15, 3)
        else:
            start, dur = round(t, 3), section_seconds(s)
            vo_start, vo_dur = None, None
        out.append({"start": start, "dur": dur, "vo_start": vo_start, "vo_dur": vo_dur})
        t = start + dur
    total = round(out[-1]["start"] + out[-1]["dur"] + tail, 2)
    # make sections contiguous: each ends where the next begins
    for a, b in zip(out, out[1:]):
        a["dur"] = round(b["start"] - a["start"], 3)
    out[-1]["dur"] = round(total - out[-1]["start"], 3)
    return out, total


def _lines(sid, items, cls, tag="div"):
    return "".join('<%s class="%s" id="%s-i%d">%s</%s>' % (tag, cls, sid, k, _e(x), tag) for k, x in enumerate(items, 1))


def section_html(i, s, n):
    sid = "s%d" % i
    k = s.get("kind")
    v = s.get("visual") or {}
    head = _e(s.get("heading", ""))
    if k in ("cold_open", "outro"):
        lines = v.get("lines") or []
        body = ('<div class="titlewrap"><div class="kicker" id="%s-k">%s</div><h1 class="big" id="%s-h">%s</h1>%s</div>'
                % (sid, "chapter %d of %d" % (i, n) if k == "outro" else "a RAPP agent, explained", sid, head,
                   "".join('<p class="tag" id="%s-t%d">%s</p>' % (sid, j, _e(x)) for j, x in enumerate(lines, 1))))
    elif k == "explain":
        body = ('<div class="panel"><h2 class="h" id="%s-h">%s</h2><ul class="bul">%s</ul></div>'
                % (sid, head, "".join('<li class="b" id="%s-i%d"><span class="dot"></span><span>%s</span></li>'
                                      % (sid, j, _e(x)) for j, x in enumerate(v.get("items") or [], 1))))
    elif k == "steps":
        body = ('<div class="panel"><h2 class="h" id="%s-h">%s</h2><div class="flow"><svg class="conn" viewBox="0 0 100 10" preserveAspectRatio="none" aria-hidden="true">'
                '<path id="%s-conn" d="M0 5 H100" pathLength="1"/></svg><ol class="steps">%s</ol></div></div>'
                % (sid, head, sid, "".join('<li class="step" id="%s-i%d"><span class="num">%d</span><span class="txt">%s</span></li>'
                                           % (sid, j, j, _e(x)) for j, x in enumerate(v.get("items") or [], 1))))
    elif k == "example":
        turns = v.get("turns") or []
        body = ('<div class="panel"><h2 class="h" id="%s-h">%s</h2><div class="chat">%s</div></div>'
                % (sid, head, "".join('<div class="turn %s" id="%s-i%d"><span class="who">%s</span><span class="msg">%s</span></div>'
                                      % (t.get("who"), sid, j, "you" if t.get("who") == "user" else "agent", _e(t.get("text", "")))
                                      for j, t in enumerate(turns, 1))))
    elif k == "stat":
        val = str(v.get("value", "0"))
        m = re.match(r"^([\d.,]+)(.*)$", val)
        num, suf = (m.group(1), m.group(2)) if m else ("0", "")
        body = ('<div class="panel center"><h2 class="h" id="%s-h">%s</h2><div class="stat" id="%s-num" data-target="%s" data-suffix="%s">0%s</div>'
                '<p class="cap" id="%s-cap">%s</p></div>' % (sid, head, sid, _e(num), _e(suf), _e(suf), sid, _e(v.get("caption", ""))))
    elif k == "fit":
        cards = v.get("items") or []
        body = ('<div class="panel"><h2 class="h" id="%s-h">%s</h2><div class="cards n%d">%s</div></div>'
                % (sid, head, len(cards), "".join('<div class="card" id="%s-i%d"><div class="ct">%s</div><div class="cx">%s</div></div>'
                                                  % (sid, j, _e(c.get("title", "")), _e(c.get("text", ""))) for j, c in enumerate(cards, 1))))
    elif k == "install":
        lines = v.get("lines") or []
        body = ('<div class="panel"><h2 class="h" id="%s-h">%s</h2><div class="term" id="%s-term"><div class="tbar"><i></i><i></i><i></i><span>terminal</span></div>'
                '<pre class="tbody">%s</pre></div></div>' % (sid, head, sid, "".join('<div class="tl" id="%s-i%d">%s</div>' % (sid, j, _e(x)) for j, x in enumerate(lines, 1))))
    else:
        body = '<div class="panel"><h2 class="h" id="%s-h">%s</h2></div>' % (sid, head)
    return ('<section id="%s" class="clip scene kind-%s" data-start="{start}" data-duration="{dur}" data-track-index="%d">'
            '<div class="stage-in" id="%s-in">%s</div></section>' % (sid, k, 1 + ((i - 1) % 4), sid, body))


CSS = """
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#07080d;--panel:#0d0f18;--amber:#f0b429;--amber-dim:#7a5a1a;--green:#3ddc84;--ink:#e8e9f0;--muted:#8f95ad;--line:rgba(255,255,255,.07);--mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace}
html,body{width:%(W)dpx;height:%(H)dpx;overflow:hidden;background:var(--bg);color:var(--ink);font-family:var(--mono)}
#root{position:relative;width:%(W)dpx;height:%(H)dpx;overflow:hidden}
.clip{position:absolute;inset:0}
#fill{position:absolute;inset:0;background:radial-gradient(1200px 700px at 50%% -8%%,rgba(240,180,41,.10),transparent 60%%),radial-gradient(900px 600px at 50%% 120%%,rgba(61,220,132,.06),transparent 60%%),var(--bg)}
#scan{position:absolute;inset:0;background:repeating-linear-gradient(0deg,rgba(255,255,255,.015) 0 1px,transparent 1px 4px);opacity:.5}
#glow{position:absolute;width:900px;height:900px;left:510px;top:90px;border-radius:50%%;background:radial-gradient(circle,rgba(240,180,41,.10),transparent 60%%);will-change:transform}
/* chrome */
#chip{position:absolute;top:44px;left:72px;font-size:22px;letter-spacing:5px;text-transform:uppercase;color:var(--muted)}
#chip b{color:var(--amber);font-weight:700}
#counter{position:absolute;top:44px;right:72px;font-size:22px;letter-spacing:3px;color:var(--muted);font-variant-numeric:tabular-nums}
#ptrack{position:absolute;top:84px;left:72px;right:72px;height:3px;background:rgba(255,255,255,.08)}
#pbar{position:absolute;inset:0;background:var(--amber);transform-origin:left center}
/* scenes */
.stage-in{position:absolute;left:120px;right:120px;top:130px;bottom:170px;display:flex;flex-direction:column;justify-content:center}
.titlewrap{display:flex;flex-direction:column;align-items:center;text-align:center;gap:26px}
.kicker{color:var(--muted);font-size:26px;letter-spacing:6px;text-transform:uppercase}
.big{font-size:104px;line-height:1.02;font-weight:800;letter-spacing:1px;color:var(--amber);text-shadow:0 0 24px rgba(240,180,41,.45),0 0 60px rgba(240,180,41,.2);max-width:1500px;text-wrap:balance}
.kind-outro .big{color:var(--ink);text-shadow:none}
.tag{font-size:38px;color:var(--ink);opacity:.9;max-width:1400px;text-wrap:balance}
.panel{display:flex;flex-direction:column;gap:34px}
.panel.center{align-items:center;text-align:center}
.h{font-size:56px;font-weight:700;color:var(--amber);letter-spacing:1px}
.bul{list-style:none;display:flex;flex-direction:column;gap:22px}
.b{display:flex;gap:22px;align-items:flex-start;font-size:40px;line-height:1.3;color:var(--ink);will-change:transform;max-width:1500px}
.b .dot{flex:0 0 14px;width:14px;height:14px;border-radius:50%%;background:var(--green);margin-top:18px;box-shadow:0 0 12px rgba(61,220,132,.6)}
.flow{position:relative;padding-top:6px}
.steps{list-style:none;display:grid;grid-template-columns:repeat(auto-fit,minmax(0,1fr));gap:22px;position:relative}
.step{display:flex;flex-direction:column;gap:16px;border:1px solid var(--line);border-radius:14px;padding:26px 24px;background:rgba(255,255,255,.012);font-size:30px;line-height:1.3;will-change:transform;min-height:220px}
.step .num{width:54px;height:54px;border-radius:50%%;background:var(--amber);color:var(--bg);display:grid;place-items:center;font-weight:800;font-size:26px}
.conn{position:absolute;left:0;right:0;top:32px;height:10px;width:100%%}
.conn path{fill:none;stroke:var(--amber);stroke-width:3;stroke-dasharray:1;stroke-dashoffset:1;opacity:.55}
.chat{display:flex;flex-direction:column;gap:18px;max-width:1500px}
.turn{display:flex;gap:22px;align-items:flex-start;border:1px solid var(--line);border-radius:14px;padding:22px 26px;background:rgba(255,255,255,.012);font-size:32px;line-height:1.35;will-change:transform}
.turn .who{flex:0 0 110px;font-size:20px;letter-spacing:3px;text-transform:uppercase;color:var(--muted);padding-top:8px}
.turn.agent{border-color:rgba(61,220,132,.35)}.turn.agent .who{color:var(--green)}
.turn.user .who{color:var(--amber)}
.stat{font-size:220px;line-height:1;font-weight:800;color:var(--green);text-shadow:0 0 30px rgba(61,220,132,.35);font-variant-numeric:tabular-nums;will-change:transform}
.cap{font-size:40px;color:var(--ink);max-width:1200px;text-wrap:balance}
.cards{display:grid;gap:22px}.cards.n3{grid-template-columns:repeat(3,1fr)}.cards.n4{grid-template-columns:repeat(4,1fr)}
.card{border:1px solid var(--line);border-radius:14px;padding:28px 26px;background:rgba(255,255,255,.012);display:flex;flex-direction:column;gap:14px;min-height:240px;will-change:transform}
.card .ct{font-size:32px;font-weight:700;color:var(--amber)}.card .cx{font-size:27px;line-height:1.35;color:var(--ink);opacity:.9}
.term{border:1px solid var(--line);border-radius:14px;background:var(--panel);max-width:1500px;overflow:hidden;will-change:transform}
.tbar{display:flex;align-items:center;gap:10px;padding:14px 18px;border-bottom:1px solid var(--line);color:var(--muted);font-size:20px}
.tbar i{width:12px;height:12px;border-radius:50%%;background:#3a3f55;display:inline-block}.tbar span{margin-left:8px;letter-spacing:3px}
.tbody{padding:26px 28px;font-size:30px;line-height:1.5;color:var(--green);white-space:pre-wrap;word-break:break-word;font-family:var(--mono)}
.tl{will-change:transform}
/* caption band */
#cap{position:absolute;left:0;right:0;bottom:56px;text-align:center;color:var(--muted);font-size:31px;letter-spacing:1px;padding:0 160px;line-height:1.35}
#cap b{color:var(--ink)}
"""

JS = r"""
window.__timelines = window.__timelines || {};
const S = %(sections_json)s;      // [{id, kind, start, dur, vo_start, vo_dur, items}]
const CAPS = %(caps_json)s;       // [[start, dur, html]]
const TOTAL = %(total)s;
const tl = gsap.timeline({ paused: true });

// ambient: one slow finite drift on the glow
tl.fromTo("#glow", { x: 0, y: 0 }, { x: 60, y: 40, duration: 12, ease: "sine.inOut", yoyo: true,
  repeat: Math.max(1, Math.ceil(TOTAL / 12)), immediateRender: false }, 0);
// chrome
tl.fromTo("#pbar", { scaleX: 0 }, { scaleX: 1, duration: TOTAL, ease: "none" }, 0);
tl.fromTo("#chip", { y: -16, opacity: 0 }, { y: 0, opacity: 1, duration: 0.5, ease: "power2.out" }, 0.2);
tl.fromTo("#counter", { y: -16, opacity: 0 }, { y: 0, opacity: 1, duration: 0.5, ease: "power2.out" }, 0.3);
S.forEach((sc, i) => tl.set("#counter", { textContent: String(i + 1).padStart(2, "0") + " / " + String(S.length).padStart(2, "0") }, sc.start));

const spread = (n, span) => Math.min(0.9, span * 0.55) / Math.max(1, n);   // items land while the voice is still talking

S.forEach((sc) => {
  const t = sc.start, id = "#" + sc.id, span = sc.vo_dur || sc.dur;
  const items = gsap.utils.toArray(id + " [id$='-i1'], " + id + " [id$='-i2'], " + id + " [id$='-i3'], " + id + " [id$='-i4'], " + id + " [id$='-i5'], " + id + " [id$='-i6']");
  switch (sc.kind) {
    case "cold_open":
      tl.fromTo(id + "-k", { opacity: 0, y: -10 }, { opacity: 1, y: 0, duration: 0.45 }, t + 0.1);
      tl.fromTo(id + "-h", { autoAlpha: 0, y: 26 }, { autoAlpha: 1, y: 0, duration: 0.55, ease: "power2.out" }, t + 0.25);
      tl.fromTo(id + "-h", { opacity: 1 }, { opacity: 0.55, duration: 0.06, yoyo: true, repeat: 3, ease: "none", immediateRender: false }, t + 0.85);
      gsap.utils.toArray(id + " .tag").forEach((el, k) => tl.fromTo(el, { autoAlpha: 0, y: 14 }, { autoAlpha: 1, y: 0, duration: 0.45 }, t + 1.1 + k * 0.3));
      break;
    case "outro":
      tl.fromTo(id + "-k", { opacity: 0 }, { opacity: 1, duration: 0.4 }, t + 0.1);
      tl.fromTo(id + "-h", { autoAlpha: 0, y: 18 }, { autoAlpha: 1, y: 0, duration: 0.5 }, t + 0.3);
      gsap.utils.toArray(id + " .tag").forEach((el, k) => tl.fromTo(el, { autoAlpha: 0, y: 18 }, { autoAlpha: 1, y: 0, duration: 0.45 }, t + 0.9 + k * 0.35));
      break;
    default:
      tl.fromTo(id + "-h", { autoAlpha: 0, x: -40 }, { autoAlpha: 1, x: 0, duration: 0.5, ease: "power3.out" }, t + 0.1);
  }
  // per-kind items
  if (sc.kind === "explain") items.forEach((el, k) => tl.fromTo(el, { autoAlpha: 0, x: -50 }, { autoAlpha: 1, x: 0, duration: 0.45, ease: "power3.out" }, t + 0.7 + k * spread(items.length, span) * 2.2));
  if (sc.kind === "steps") {
    items.forEach((el, k) => tl.fromTo(el, { autoAlpha: 0, y: 40 }, { autoAlpha: 1, y: 0, duration: 0.5, ease: "back.out(1.4)" }, t + 0.7 + k * spread(items.length, span) * 2.0));
    tl.fromTo(id + "-conn", { strokeDashoffset: 1 }, { strokeDashoffset: 0, duration: Math.min(2.4, span * 0.5), ease: "power2.inOut" }, t + 0.8);
  }
  if (sc.kind === "example") items.forEach((el, k) => tl.fromTo(el, { autoAlpha: 0, y: 30, scale: 0.98 }, { autoAlpha: 1, y: 0, scale: 1, duration: 0.5, ease: "power3.out" }, t + 0.7 + k * spread(items.length, span) * 2.6));
  if (sc.kind === "fit") items.forEach((el, k) => tl.fromTo(el, { autoAlpha: 0, y: 40, rotationX: 12 }, { autoAlpha: 1, y: 0, rotationX: 0, duration: 0.55, ease: "power3.out" }, t + 0.7 + k * spread(items.length, span) * 1.6));
  if (sc.kind === "install") {
    tl.fromTo(id + "-term", { autoAlpha: 0, y: 30 }, { autoAlpha: 1, y: 0, duration: 0.5, ease: "power3.out" }, t + 0.6);
    items.forEach((el, k) => tl.fromTo(el, { autoAlpha: 0, x: -10 }, { autoAlpha: 1, x: 0, duration: 0.3 }, t + 1.2 + k * spread(items.length, span) * 2.0));
  }
  if (sc.kind === "stat") {
    const el = document.querySelector(id + "-num");
    const target = parseFloat((el.getAttribute("data-target") || "0").replace(/,/g, "")) || 0;
    const suffix = el.getAttribute("data-suffix") || "";
    const decimals = ((el.getAttribute("data-target") || "").split(".")[1] || "").length;
    const proxy = { v: 0 };
    tl.fromTo(el, { scale: 0.7, autoAlpha: 0 }, { scale: 1, autoAlpha: 1, duration: 0.6, ease: "back.out(1.5)" }, t + 0.6);
    tl.fromTo(proxy, { v: 0 }, { v: target, duration: 1.6, ease: "power2.out", onUpdate: () => {
      el.textContent = proxy.v.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals }) + suffix; } }, t + 0.6);
    tl.fromTo(id + "-cap", { autoAlpha: 0, y: 20 }, { autoAlpha: 1, y: 0, duration: 0.5 }, t + 1.4);
  }
  // exit: lift the inner stage before the cut (wrapper inside the clip)
  if (sc.exit) tl.fromTo(id + "-in", { y: 0, autoAlpha: 1 }, { y: -30, autoAlpha: 0, duration: 0.4, ease: "power2.in", immediateRender: false }, t + sc.dur - 0.42);
});

// captions: discrete text states + a fade per chunk (eight-ais-bar pattern)
const captext = document.getElementById("captext");
CAPS.forEach(([start, dur, htmlText]) => {
  tl.set(captext, { innerHTML: htmlText }, start);
  tl.fromTo("#capband", { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.25, immediateRender: false }, start);
  tl.to("#capband", { autoAlpha: 0, duration: 0.25 }, start + Math.max(0.5, dur) - 0.25);
});
window.__timelines["%(comp)s"] = tl;
"""


def build_captions(doc, times, gap=0.12):
    """Chunks per section, timed proportionally by word count inside the section's
    voice span (or the whole section when there is no voice)."""
    caps = []
    for s, tm in zip(doc["sections"], times):
        chunks = caption_chunks(s.get("narration", ""))
        if not chunks:
            continue
        span_start = tm["start"] + (0.15 if tm["vo_start"] is not None else 0.4)
        span = (tm["vo_dur"] if tm["vo_dur"] else tm["dur"] - 0.8)
        total_w = sum(word_count(c) for c in chunks) or 1
        t = span_start
        for c in chunks:
            d = span * (word_count(c) / total_w)
            caps.append([round(t, 3), round(max(0.6, d - gap), 3), _e(c)])
            t += d
    return caps


def compose_long(doc, slug, spans=None, audio_rel=None, fps=30, chip=None):
    times, total = timings(doc, spans)
    plan, parts = [], []
    n = len(doc["sections"])
    for i, (s, tm) in enumerate(zip(doc["sections"], times), 1):
        parts.append(section_html(i, s, n).format(start=tm["start"], dur=tm["dur"]))
        plan.append({"id": "s%d" % i, "kind": s.get("kind"), "start": tm["start"], "dur": tm["dur"],
                     "vo_start": tm["vo_start"], "vo_dur": tm["vo_dur"], "exit": i < n})
    caps = build_captions(doc, times)
    css = CSS % {"W": W, "H": H}
    js = JS % {"sections_json": json.dumps(plan), "caps_json": json.dumps(caps), "total": total, "comp": COMP_ID}
    audio = ""
    if audio_rel and spans:
        vo_total = spans[-1][0] + spans[-1][1]
        audio = ('<audio id="vo" src="%s" data-start="%s" data-duration="%s" data-track-index="10" data-volume="1"></audio>\n'
                 % (_e(audio_rel), 0.6, round(vo_total + 0.05, 3)))
    doc_html = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="UTF-8" />\n'
                '<meta name="viewport" content="width=%d, height=%d" />\n<title>%s</title>\n'
                '<meta name="generator" content="rapp-education-shorts/%s long" />\n'
                '<script src="%s"></script>\n<style>%s</style>\n</head>\n<body>\n'
                '<div id="root" data-composition-id="%s" data-start="0" data-width="%d" data-height="%d" data-duration="%s" data-fps="%d">\n'
                '<div id="bg" class="clip" data-start="0" data-duration="%s" data-track-index="0"><div id="fill"></div><div id="scan"></div><div id="glow" data-layout-allow-overflow></div></div>\n'
                '%s\n'
                '<div id="chrome" class="clip" data-start="0" data-duration="%s" data-track-index="5"><div id="chip"><b>%s</b>&nbsp;&nbsp;%s</div>'
                '<div id="counter">01 / %02d</div><div id="ptrack"><div id="pbar"></div></div></div>\n'
                '<div id="capband" class="clip" data-start="0" data-duration="%s" data-track-index="6" data-layout-allow-caption-zone><div id="cap"><span id="captext"></span></div></div>\n'
                '%s</div>\n<script>%s</script>\n</body>\n</html>\n') % (
        W, H, _e(doc.get("title", slug)), __version__, GSAP_CDN, css, COMP_ID, W, H, total, fps,
        total, "\n".join(parts), total, _e(chip or doc.get("chip") or "explainer"), _e(doc.get("title", ""))[:60], n,
        total, audio, js)
    return {"index.html": doc_html, "duration": total, "captions": len(caps), "times": times}
