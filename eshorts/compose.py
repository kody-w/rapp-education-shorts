"""compose.py — SCRIPT.json → a HyperFrames project.

What the generated composition obeys (hyperframes-core / hyperframes-animation):
  * standalone root `#root` with data-composition-id/start/width/height/duration/fps
  * every timed visual is a `class="clip"` DIRECT child of the root, on a track;
    scene clips are sequential, round-robin over tracks 1–4 (never overlapping); background on
    track 0; chrome (progress, counter, title chip) on track 5; optional audio bed on 6
  * ONE paused GSAP timeline registered on window.__timelines["short"], built
    synchronously; every tween is fromTo with explicit from-state, absolute
    values, finite repeats; no CSS transitions on animated elements; no CSS
    transform on tweened elements (the from-state lives in the tween)
  * transforms + paint-only properties; width/height are never tweened
    (progress bar = scaleX proxy; underline = scaleX; connector = dashoffset with
    pathLength=1 so nothing is measured at build time)
  * no clocks, no Math.random, no network beyond the pinned GSAP CDN the CLI
    scaffold itself uses; the same SCRIPT.json produces the same bytes
  * content stays inside a Shorts-safe box (clear of the top bar, the right-hand
    action rail and the bottom title/caption zone)
"""

import html
import json
import re
from pathlib import Path

from . import __version__
from .script import timeline as script_timeline, word_count
from .themes import pick

W, H = 1080, 1920
SAFE_TOP, SAFE_BOTTOM, SAFE_X = 300, 460, 72
COMP_ID = "short"
GSAP_CDN = "https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"

_e = html.escape


def emphasise(text, words):
    """Wrap emphasised words in <em class="hi"> (accent + underline reveal)."""
    out = _e(text)
    for w in sorted({w for w in (words or []) if w and w.strip()}, key=len, reverse=True):
        out = re.sub(r"(?<![\w-])(%s)(?![\w-])" % re.escape(_e(w)),
                     r'<em class="hi">\1<span class="u"></span></em>', out, flags=re.I)
    return out


def _lines_html(sid, lines, emph):
    return "".join('<p class="line" id="%s-l%d">%s</p>' % (sid, j, emphasise(l, emph))
                   for j, l in enumerate(lines, 1))


def scene_html(i, s, n_scenes):
    sid = "s%d" % i
    track = 1 + ((i - 1) % 4)   # sequential scenes never overlap; spreading them over 4 tracks keeps each track readable
    kind = s.get("kind", "point")
    emph = s.get("emphasis") or []
    v = s.get("visual") or {}
    heading = emphasise(s.get("heading", ""), emph)
    lines = s.get("lines") or []
    body = ""
    if kind == "hook":
        body = ('<h1 class="hook" id="%s-h">%s</h1>%s' % (sid, heading, _lines_html(sid, lines[:1], emph)))
    elif kind == "steps":
        items = v.get("items") or []
        chips = "".join(
            '<li class="step" id="%s-st%d"><span class="num">%d</span><span class="txt">%s</span></li>'
            % (sid, k, k, emphasise(t, emph)) for k, t in enumerate(items, 1))
        body = ('<h2 class="head" id="%s-h">%s</h2>%s<div class="steps-wrap"><svg class="conn" viewBox="0 0 10 100" preserveAspectRatio="none" aria-hidden="true">'
                '<path id="%s-conn" d="M5 0 V100" pathLength="1"/></svg><ol class="steps">%s</ol></div>'
                % (sid, heading, _lines_html(sid, lines[:1], emph), sid, chips))
    elif kind == "compare":
        body = ('<h2 class="head" id="%s-h">%s</h2>%s<div class="cmp"><div class="card left" id="%s-cl">%s</div>'
                '<div class="vs" id="%s-vs">vs</div><div class="card right" id="%s-cr">%s</div></div>'
                % (sid, heading, _lines_html(sid, lines[:1], emph), sid, emphasise(v.get("left", ""), emph),
                   sid, sid, emphasise(v.get("right", ""), emph)))
    elif kind == "number":
        val = str(v.get("value", "0"))
        m = re.match(r"^([\d.,]+)(.*)$", val)
        num, suffix = (m.group(1), m.group(2)) if m else ("0", "")
        body = ('<h2 class="head" id="%s-h">%s</h2><div class="bignum" id="%s-num" data-target="%s" data-suffix="%s">%s%s</div>'
                '<p class="cap" id="%s-cap">%s</p>%s'
                % (sid, heading, sid, _e(num), _e(suffix), "0", _e(suffix), sid, emphasise(v.get("caption", ""), emph),
                   _lines_html(sid, lines[:1], emph)))
    elif kind == "quote":
        body = ('<div class="qmark" id="%s-q">“</div><h2 class="head" id="%s-h">%s</h2>%s'
                % (sid, sid, heading, _lines_html(sid, lines[:2], emph)))
    elif kind in ("recap",):
        body = ('<h2 class="head" id="%s-h">%s</h2><ul class="bullets">%s</ul>'
                % (sid, heading, "".join('<li class="bullet" id="%s-b%d"><span class="dot"></span><span>%s</span></li>'
                                          % (sid, j, emphasise(l, emph)) for j, l in enumerate(lines, 1))))
    elif kind == "cta":
        pill = (v.get("text") if v.get("type") == "pill" else None) or "Follow for more"
        body = ('<h2 class="head" id="%s-h">%s</h2>%s<div class="pill" id="%s-pill">%s</div>'
                % (sid, heading, _lines_html(sid, lines[:2], emph), sid, _e(pill)))
    else:  # point
        body = '<h2 class="head" id="%s-h">%s</h2>%s' % (sid, heading, _lines_html(sid, lines[:3], emph))
    return ('<section id="%s" class="clip scene kind-%s" data-start="{start}" data-duration="{dur}" data-track-index="%d">'
            '<div class="stage" id="%s-stage">%s</div></section>' % (sid, kind, track, sid, body))


CSS = """
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:%(W)dpx;height:%(H)dpx;overflow:hidden;background:%(bg1)s}
body{font-family:"Inter",system-ui,sans-serif;color:%(ink)s}
#root{position:relative;width:%(W)dpx;height:%(H)dpx;overflow:hidden}
.clip{position:absolute;inset:0}
/* background — full-bleed CHILD, never the root's own background */
#bgfill{position:absolute;inset:0;background:linear-gradient(160deg,%(bg1)s 0%%,%(bg2)s 100%%)}
.blob{position:absolute;border-radius:50%%;filter:blur(90px);opacity:.55;will-change:transform}
#blob1{width:820px;height:820px;left:-260px;top:120px;background:%(blob1)s}
#blob2{width:700px;height:700px;right:-220px;top:900px;background:%(blob2)s}
#blob3{width:520px;height:520px;left:180px;bottom:-200px;background:%(accent2)s;opacity:.28}
#grid{position:absolute;inset:0;background-image:linear-gradient(rgba(255,255,255,.04) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.04) 1px,transparent 1px);background-size:120px 120px}
/* chrome */
#chip{position:absolute;top:150px;left:%(SAFE_X)dpx;font-size:30px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:%(muted)s;display:flex;align-items:center;gap:16px}
#chip .dotc{width:14px;height:14px;border-radius:50%%;background:%(accent)s;display:inline-block}
#counter{position:absolute;top:150px;right:180px;font-size:30px;font-weight:600;color:%(muted)s;font-variant-numeric:tabular-nums}
#ptrack{position:absolute;top:212px;left:%(SAFE_X)dpx;right:%(SAFE_X)dpx;height:8px;border-radius:8px;background:rgba(127,127,127,.25);overflow:hidden}
#pbar{position:absolute;inset:0;background:%(accent)s;transform-origin:left center}
/* scenes */
.stage{position:absolute;left:%(SAFE_X)dpx;right:%(SAFE_X)dpx;top:%(SAFE_TOP)dpx;bottom:%(SAFE_BOTTOM)dpx;display:flex;flex-direction:column;justify-content:center;gap:34px}
.head{font-size:88px;line-height:1.04;font-weight:800;letter-spacing:-.02em;text-wrap:balance}
.hook{font-size:118px;line-height:1.0;font-weight:900;letter-spacing:-.03em;text-wrap:balance}
.line{font-size:52px;line-height:1.3;font-weight:500;color:%(muted)s;text-wrap:pretty}
.kind-hook .line{font-size:56px;color:%(ink)s;font-weight:500}
em.hi{font-style:normal;color:%(accent)s;position:relative;display:inline-block;padding:0 .04em}
em.hi .u{position:absolute;left:0;right:0;bottom:-.06em;height:.12em;background:%(accent)s;opacity:.55;transform-origin:left center;border-radius:4px}
.steps-wrap{position:relative;padding-left:12px}
.steps{list-style:none;display:flex;flex-direction:column;gap:26px;position:relative}
.step{display:flex;align-items:center;gap:26px;background:%(card)s;border:2px solid rgba(255,255,255,.08);border-radius:26px;padding:26px 30px;font-size:46px;line-height:1.25;font-weight:600;will-change:transform}
.step .num{flex:0 0 78px;height:78px;border-radius:50%%;background:%(accent)s;color:%(bg1)s;display:grid;place-items:center;font-weight:900;font-size:40px}
.conn{position:absolute;left:49px;top:40px;bottom:40px;width:10px;height:calc(100%% - 80px)}
.conn path{fill:none;stroke:%(accent)s;stroke-width:6;stroke-dasharray:1;stroke-dashoffset:1;opacity:.6}
.cmp{display:grid;grid-template-columns:1fr auto 1fr;align-items:stretch;gap:22px;perspective:1400px}
.card{background:%(card)s;border:2px solid rgba(255,255,255,.1);border-radius:30px;padding:40px 34px;font-size:46px;line-height:1.25;font-weight:600;display:flex;align-items:center;justify-content:center;text-align:center;min-height:320px;will-change:transform}
.card.left{border-color:%(accent)s}.card.right{border-color:%(accent2)s}
.vs{align-self:center;font-size:40px;font-weight:900;color:%(muted)s;padding:0 4px}
.bignum{font-size:230px;line-height:1;font-weight:900;letter-spacing:-.04em;color:%(accent)s;font-variant-numeric:tabular-nums;will-change:transform}
.cap{font-size:54px;line-height:1.25;font-weight:600;color:%(ink)s}
.qmark{font-size:260px;line-height:.6;font-weight:900;color:%(accent)s;opacity:.9;height:150px;will-change:transform}
.kind-quote .head{font-size:78px;font-weight:700;font-style:italic}
.bullets{list-style:none;display:flex;flex-direction:column;gap:28px}
.bullet{display:flex;gap:26px;align-items:flex-start;font-size:52px;line-height:1.3;font-weight:600;will-change:transform}
.bullet .dot{flex:0 0 26px;width:26px;height:26px;border-radius:50%%;background:%(accent)s;margin-top:22px}
.pill{align-self:flex-start;background:%(accent)s;color:%(bg1)s;font-weight:800;font-size:46px;padding:26px 46px;border-radius:999px;will-change:transform;margin-top:14px}
"""

JS = r"""
window.__timelines = window.__timelines || {};
const S = %(scenes_json)s;         // [{id, kind, start, dur, exit}]
const TOTAL = %(total)s;
const tl = gsap.timeline({ paused: true });

// ── ambient background: finite yoyo drifts, transform-only, deterministic ──
const drift = (sel, dx, dy, period) => {
  const reps = Math.max(1, Math.ceil(TOTAL / period));
  tl.fromTo(sel, { x: 0, y: 0 }, { x: dx, y: dy, duration: period, ease: "sine.inOut",
    yoyo: true, repeat: reps, immediateRender: false }, 0);
};
drift("#blob1", 140, 90, 9); drift("#blob2", -120, -80, 11); drift("#blob3", 60, -140, 13);

// ── chrome: progress is a scaleX proxy over the whole short ──
tl.fromTo("#pbar", { scaleX: 0 }, { scaleX: 1, duration: TOTAL, ease: "none" }, 0);
tl.fromTo("#chip", { y: -30, opacity: 0 }, { y: 0, opacity: 1, duration: 0.6, ease: "power3.out" }, 0.1);
tl.fromTo("#counter", { y: -30, opacity: 0 }, { y: 0, opacity: 1, duration: 0.6, ease: "power3.out" }, 0.15);
S.forEach((sc, i) => {
  // counter text is a discrete state: swap at each scene start (zero-duration set on a non-clip element)
  tl.set("#counter", { textContent: (i + 1) + " / " + S.length }, sc.start);
});

// ── per-scene entrances (distinct per kind), staggers capped ≤ 0.5s, exits before the cut ──
const stag = (n, cap = 0.5) => Math.min(0.14, cap / Math.max(1, n));
S.forEach((sc) => {
  const t = sc.start, id = "#" + sc.id, stage = id + "-stage";
  const lines = gsap.utils.toArray(id + " .line");
  const under = gsap.utils.toArray(id + " em.hi .u");
  switch (sc.kind) {
    case "hook":
      tl.fromTo(id + "-h", { scale: 1.45, filter: "blur(18px)", opacity: 0 },
        { scale: 1, filter: "blur(0px)", opacity: 1, duration: 0.55, ease: "power4.out" }, t + 0.1);
      break;
    case "number":
      tl.fromTo(id + "-h", { y: -40, opacity: 0 }, { y: 0, opacity: 1, duration: 0.5, ease: "power3.out" }, t + 0.05);
      break;
    case "quote":
      tl.fromTo(id + "-q", { scale: 0.4, rotation: -12, opacity: 0 }, { scale: 1, rotation: 0, opacity: 1, duration: 0.6, ease: "back.out(1.6)" }, t + 0.05);
      tl.fromTo(id + "-h", { y: 40, opacity: 0 }, { y: 0, opacity: 1, duration: 0.55, ease: "power3.out" }, t + 0.35);
      break;
    default:
      tl.fromTo(id + "-h", { x: -70, opacity: 0 }, { x: 0, opacity: 1, duration: 0.5, ease: "expo.out" }, t + 0.05);
  }
  lines.forEach((el, k) => {
    tl.fromTo(el, { y: 44, opacity: 0 }, { y: 0, opacity: 1, duration: 0.5, ease: "power3.out" },
      t + 0.45 + k * stag(lines.length));
  });
  under.forEach((el, k) => {
    tl.fromTo(el, { scaleX: 0 }, { scaleX: 1, duration: 0.4, ease: "power2.out" }, t + 0.9 + k * 0.12);
  });
  // kind-specific visuals
  const steps = gsap.utils.toArray(id + " .step");
  steps.forEach((el, k) => {
    tl.fromTo(el, { x: 90, opacity: 0 }, { x: 0, opacity: 1, duration: 0.5, ease: "back.out(1.4)" },
      t + 0.7 + k * stag(steps.length, 0.6));
  });
  if (steps.length) {
    tl.fromTo(id + "-conn", { strokeDashoffset: 1 }, { strokeDashoffset: 0, duration: 0.9, ease: "power2.inOut" }, t + 0.8);
  }
  if (sc.kind === "compare") {
    tl.fromTo(id + "-cl", { x: -240, rotationY: 28, opacity: 0 }, { x: 0, rotationY: 0, opacity: 1, duration: 0.6, ease: "expo.out" }, t + 0.6);
    tl.fromTo(id + "-cr", { x: 240, rotationY: -28, opacity: 0 }, { x: 0, rotationY: 0, opacity: 1, duration: 0.6, ease: "expo.out" }, t + 0.7);
    tl.fromTo(id + "-vs", { scale: 0, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.4, ease: "back.out(2)" }, t + 1.0);
  }
  if (sc.kind === "number") {
    const el = document.querySelector(id + "-num");
    const target = parseFloat((el.getAttribute("data-target") || "0").replace(/,/g, "")) || 0;
    const suffix = el.getAttribute("data-suffix") || "";
    const decimals = ((el.getAttribute("data-target") || "").split(".")[1] || "").length;
    const proxy = { v: 0 };
    tl.fromTo(el, { scale: 0.6, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.6, ease: "back.out(1.5)" }, t + 0.5);
    tl.fromTo(proxy, { v: 0 }, { v: target, duration: 1.4, ease: "power2.out", onUpdate: () => {
      el.textContent = proxy.v.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals }) + suffix;
    } }, t + 0.5);
    tl.fromTo(id + "-cap", { y: 40, opacity: 0 }, { y: 0, opacity: 1, duration: 0.5, ease: "power3.out" }, t + 1.2);
  }
  const bullets = gsap.utils.toArray(id + " .bullet");
  bullets.forEach((el, k) => {
    tl.fromTo(el, { x: -60, opacity: 0 }, { x: 0, opacity: 1, duration: 0.45, ease: "power3.out" }, t + 0.6 + k * stag(bullets.length));
  });
  if (sc.kind === "cta") {
    tl.fromTo(id + "-pill", { scale: 0.7, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.5, ease: "back.out(1.8)" }, t + 0.9);
    tl.fromTo(id + "-pill", { scale: 1 }, { scale: 1.06, duration: 0.5, ease: "sine.inOut", yoyo: true, repeat: 3, immediateRender: false }, t + 1.5);
  }
  // exit: the whole stage lifts and fades before the cut (autoAlpha on a wrapper inside the clip)
  if (sc.exit) {
    tl.fromTo(stage, { y: 0, autoAlpha: 1 }, { y: -60, autoAlpha: 0, duration: 0.35, ease: "power2.in", immediateRender: false }, sc.start + sc.dur - 0.38);
  }
});
window.__timelines["%(comp)s"] = tl;
"""


def compose(script, slug, theme=None, fps=30, audio=None, chip=None):
    """Return {"index.html": ..., "meta.json": ..., "package.json": ..., "hyperframes.json": ...}."""
    theme_name, T = pick(theme or script.get("theme"), slug)
    scenes = script["scenes"]
    times, total = script_timeline(script)
    total = round(total + 0.4, 2)   # a short tail so the last scene's end state holds
    parts, plan = [], []
    for i, (s, tm) in enumerate(zip(scenes, times), 1):
        parts.append(scene_html(i, s, len(scenes)).format(start=tm["start"], dur=tm["duration"]))
        plan.append({"id": "s%d" % i, "kind": s.get("kind", "point"), "start": tm["start"],
                     "dur": tm["duration"], "exit": i < len(scenes)})
    css = CSS % dict(T, W=W, H=H, SAFE_TOP=SAFE_TOP, SAFE_BOTTOM=SAFE_BOTTOM, SAFE_X=SAFE_X)
    js = JS % {"scenes_json": json.dumps(plan), "total": total, "comp": COMP_ID}
    audio_tag = ""
    if audio:
        audio_tag = ('<audio id="bed" src="%s" data-start="0" data-duration="%s" data-track-index="6" data-volume="0.25"></audio>'
                     % (_e(audio), total))
    doc = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="UTF-8" />\n'
           '<meta name="viewport" content="width=%d, height=%d" />\n<title>%s</title>\n'
           '<meta name="generator" content="rapp-education-shorts/%s" />\n'
           '<script src="%s"></script>\n<style>%s</style>\n</head>\n<body>\n'
           '<div id="root" data-composition-id="%s" data-start="0" data-width="%d" data-height="%d" data-duration="%s" data-fps="%d">\n'
           '<div id="bg" class="clip" data-start="0" data-duration="%s" data-track-index="0">'
           '<div id="bgfill"></div><div id="grid"></div><div class="blob" id="blob1" data-layout-allow-overflow></div><div class="blob" id="blob2" data-layout-allow-overflow></div><div class="blob" id="blob3" data-layout-allow-overflow></div></div>\n'
           '%s\n'
           '<div id="chrome" class="clip" data-start="0" data-duration="%s" data-track-index="5">'
           '<div id="chip"><span class="dotc"></span><span>%s</span></div><div id="counter">1 / %d</div>'
           '<div id="ptrack"><div id="pbar"></div></div></div>\n%s</div>\n'
           '<script>%s</script>\n</body>\n</html>\n') % (
        W, H, _e(script.get("title", slug)), __version__, GSAP_CDN, css, COMP_ID, W, H, total, fps,
        total, "\n".join(parts), total, _e(chip or script.get("chip") or " ".join(str(script.get("title", "")).split()[:3])), len(scenes),
        audio_tag, js)
    return {
        "index.html": doc,
        "meta.json": json.dumps({"id": slug, "name": script.get("title", slug),
                                 "theme": theme_name, "duration": total, "fps": fps,
                                 "generator": "rapp-education-shorts/%s" % __version__}, indent=2) + "\n",
        "hyperframes.json": json.dumps({
            "$schema": "https://hyperframes.heygen.com/schema/hyperframes.json",
            "registry": "https://raw.githubusercontent.com/heygen-com/hyperframes/main/registry",
            "paths": {"blocks": "compositions", "components": "compositions/components", "assets": "assets"},
            "media": {"autoProxy": True}}, indent=2) + "\n",
        "duration": total, "theme": theme_name,
    }


def package_json(slug, cli_version):
    v = "@%s" % cli_version if cli_version else ""
    return json.dumps({"name": slug, "private": True, "type": "module", "scripts": {
        "dev": "npx --yes hyperframes%s preview" % v,
        "check": "npx --yes hyperframes%s check" % v,
        "render": "npx --yes hyperframes%s render" % v,
    }}, indent=2) + "\n"
