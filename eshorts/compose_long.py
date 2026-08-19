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


def _fmt(v, unit=""):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return _e(str(v))
    txt = ("%+.1f" % f) if abs(f) < 1000 else format(f, "+,.1f")
    return _e(txt)


def bars_svg(sid, items, unit=""):
    """Horizontal driver bars around zero: positive green, negative red. 1000x{h} viewBox."""
    n = len(items)
    rowh = 54
    h = 30 + n * rowh
    mx = max(abs(float(x.get("value", 0))) for x in items) or 1.0
    zero = 520
    scale = 380 / mx
    out = ['<svg class="bars" viewBox="0 0 1000 %d" preserveAspectRatio="xMidYMid meet" aria-hidden="true">' % h,
           '<line x1="%d" y1="10" x2="%d" y2="%d" stroke="rgba(255,255,255,.18)" stroke-width="2"/>' % (zero, zero, h - 10)]
    for k, x in enumerate(items, 1):
        v = float(x.get("value", 0)); y = 20 + (k - 1) * rowh
        w = abs(v) * scale
        x0 = zero if v >= 0 else zero - w
        col = "#3ddc84" if v >= 0 else "#f85149"
        out.append('<text x="20" y="%d" font-size="26" fill="currentColor" font-weight="600">%s</text>' % (y + 30, _e(str(x.get("label", "")))))
        out.append('<rect id="%s-bar%d" x="%d" y="%d" width="%d" height="30" rx="4" fill="%s"/>' % (sid, k, x0, y + 8, max(2, w), col))
        tx = (zero + w + 12) if v >= 0 else (zero - w - 12)
        out.append('<text x="%d" y="%d" font-size="24" fill="%s" font-weight="700" text-anchor="%s">%s</text>' % (
            tx, y + 30, col, "start" if v >= 0 else "end", _fmt(v)))
    out.append('</svg>')
    return "".join(out)


def waterfall_svg(sid, items, unit=""):
    """Cumulative waterfall left→right; the last item is drawn as a total bar. 1000x420."""
    n = len(items)
    vals = [float(x.get("value", 0)) for x in items]
    starts, cum = [], 0.0
    for k, v in enumerate(vals):
        if k == n - 1:
            starts.append(0.0)
        else:
            starts.append(cum); cum += v
    tops = [max(st, st + v) if k < n - 1 else max(0.0, v) for k, (st, v) in enumerate(zip(starts, vals))]
    bots = [min(st, st + v) if k < n - 1 else min(0.0, v) for k, (st, v) in enumerate(zip(starts, vals))]
    lo, hi = min(bots + [0.0]), max(tops + [0.0])
    span = (hi - lo) or 1.0
    W, H, top, bottom = 1000, 420, 30, 80
    ph = H - top - bottom
    def Y(v): return top + (hi - v) / span * ph
    bw = (W - 60) / n * 0.62
    step = (W - 60) / n
    out = ['<svg class="wf" viewBox="0 0 %d %d" preserveAspectRatio="xMidYMid meet" aria-hidden="true">' % (W, H),
           '<line x1="30" y1="%.1f" x2="%d" y2="%.1f" stroke="rgba(255,255,255,.18)" stroke-width="2"/>' % (Y(0), W - 30, Y(0))]
    for k, (st, v) in enumerate(zip(starts, vals)):
        x = 30 + k * step + (step - bw) / 2
        y0, y1 = Y(max(st, st + v)) if k < n - 1 else Y(max(0.0, v)), Y(min(st, st + v)) if k < n - 1 else Y(min(0.0, v))
        col = "#8f5cff" if k == n - 1 else ("#3ddc84" if v >= 0 else "#f85149")
        out.append('<rect id="%s-wf%d" x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="4" fill="%s"/>' % (sid, k + 1, x, y0, bw, max(2, y1 - y0), col))
        out.append('<text x="%.1f" y="%.1f" font-size="22" fill="%s" font-weight="700" text-anchor="middle">%s</text>' % (
            x + bw / 2, y0 - 8, col, _fmt(v)))
        out.append('<text x="%.1f" y="%d" font-size="21" fill="currentColor" text-anchor="middle">%s</text>' % (
            x + bw / 2, H - 40, _e(str(items[k].get("label", ""))[:16])))
        if k < n - 2:
            out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="rgba(255,255,255,.35)" stroke-dasharray="4 4"/>' % (
                x + bw, Y(st + v), x + step, Y(st + v)))
    out.append('</svg>')
    return "".join(out)


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
    elif k == "title":
        body = ('<div class="titlecard" id="%s-card"><div class="kicker" id="%s-k">%s</div><h1 class="tname" id="%s-h">%s</h1></div>'
                % (sid, sid, _e(v.get("kicker", "")), sid, _e(v.get("name") or s.get("heading", ""))))
    elif k == "problem":
        body = ('<div class="panel"><div class="persona" id="%s-p">%s</div><h2 class="h" id="%s-h">%s</h2><ul class="pain">%s</ul></div>'
                % (sid, _e(v.get("persona", "")), sid, head,
                   "".join('<li class="painitem" id="%s-i%d"><span class="x">×</span><span>%s</span></li>' % (sid, j, _e(x))
                           for j, x in enumerate(v.get("items") or [], 1))))
    elif k == "overview":
        def col(j, title, items):
            return ('<div class="ocol" id="%s-i%d"><div class="otitle">%s</div><div class="ocard">%s</div></div>'
                    % (sid, j, title, "".join('<div class="oi">%s</div>' % _e(x) for x in (items or []))))
        body = ('<div class="panel"><h2 class="h" id="%s-h">%s</h2><div class="triptych">%s<div class="arrow" id="%s-a1">›</div>%s<div class="arrow" id="%s-a2">›</div>%s</div></div>'
                % (sid, head, col(1, "Sources", v.get("sources")), sid, col(2, "Flow of work", v.get("flow")), sid, col(3, "Actions", v.get("actions"))))
    elif k == "turn":
        r = v.get("response") or {}
        tbl = r.get("table") or {}
        table_html = ""
        if tbl.get("headers"):
            table_html = ('<table class="ctab"><thead><tr>%s</tr></thead><tbody>%s</tbody></table>' % (
                "".join("<th>%s</th>" % _e(x) for x in tbl["headers"]),
                "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % _e(c) for c in row) for row in tbl.get("rows") or [])))
        bullets_html = ""
        if r.get("bullets"):
            bullets_html = "<ul class=\"cbul\">%s</ul>" % "".join("<li>%s</li>" % _e(x) for x in r["bullets"])
        links_html = ""
        if v.get("links"):
            links_html = '<div class="alinks">%s</div>' % "".join('<span class="alink">%s</span>' % _e(x) for x in v["links"])
        review_html = ('<div class="areview">%s</div>' % _e(v["review_line"])) if v.get("review_line") else ""
        call_html = ('<div class="acall">Agent Calls: %s</div>' % _e(v["agent_call"])) if v.get("agent_call") else ""
        agent_label = _e(v.get("agent_name") or s.get("agent_name") or "Agent")
        hist = "".join('<div class="ritem hist">%s</div>' % _e(x) for x in (v.get("history") or ["Reset workflow", "Get the package ready", "New chat"])[:4])
        body = ('<div class="panel"><h2 class="h" id="%s-h">%s</h2><div class="chatwin" id="%s-win">'
                '<div class="rail"><div class="rlogo"></div><div class="ritem">New chat</div><div class="ritem">Search</div><div class="ritem">Library</div><div class="rsub">Chats</div>%s</div>'
                '<div class="convo"><div class="ubub" id="%s-i1">%s</div>'
                '<div class="acard" id="%s-i2"><div class="aname"><span class="adot"></span>%s</div><div class="alead">%s</div>%s%s%s%s%s</div>'
                '<div class="benefit" id="%s-i3">%s</div></div></div></div>'
                % (sid, head, sid, hist, sid, _e(v.get("prompt", "")), sid, agent_label, _e(r.get("lead", "")),
                   table_html, bullets_html, links_html, review_html, call_html, sid, _e(v.get("benefit", ""))))
    elif k == "workbook":
        pr = v.get("progress") or {}
        secs = v.get("sections") or []
        html_secs = []
        for j, sec in enumerate(secs, 1):
            hdr = sec.get("headers") or []
            html_secs.append('<tbody class="wsec c-%s" id="%s-i%d"><tr class="whead"><td colspan="%d">%s</td></tr>%s%s</tbody>' % (
                _e(sec.get("color") or "gray"), sid, j, max(2, len(hdr) or max(len(r) for r in sec["rows"])), _e(sec.get("name", "")),
                ("<tr class=\"wcols\">%s</tr>" % "".join("<th>%s</th>" % _e(x) for x in hdr)) if hdr else "",
                "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % _e(c) for c in row) for row in sec.get("rows") or [])))
        body = ('<div class="panel"><h2 class="h" id="%s-h">%s</h2><div class="sheet" id="%s-win"><div class="sbar"><span class="sname">%s</span>'
                '<span class="sprog">%s</span></div><table class="wtab">%s</table><div class="stabs"><span class="on">Live Review</span><span>Executive Summary</span><span>Exception Queue</span><span>Slide Bindings</span><span>Evidence Index</span></div></div></div>'
                % (sid, head, sid, _e(v.get("title", "")), _e("Workflow progress: %s of %s" % (pr.get("step"), pr.get("total"))) if pr else "",
                   "".join(html_secs)))
    elif k == "slide":
        kp = v.get("kpis") or []
        ch = v.get("chart") or {}
        chart = ""
        if ch.get("items"):
            chart = (waterfall_svg if ch.get("type") == "waterfall" else bars_svg)(sid, ch["items"], ch.get("unit", ""))
        body = ('<div class="panel"><h2 class="h" id="%s-h">%s</h2><div class="slide" id="%s-win"><div class="skick">%s<span class="sbrand">%s</span></div>'
                '<div class="stitle">%s</div><div class="sbody"><div class="kpis">%s</div><div class="schart" id="%s-chart">%s%s</div></div>'
                '<div class="sfoot">%s</div></div></div>'
                % (sid, head, sid, _e(v.get("kicker", "")), _e(s.get("brand") or ""), _e(v.get("title", "")),
                   "".join('<div class="kpi" id="%s-i%d"><div class="kl">%s</div><div class="kv">%s</div>%s</div>' % (
                       sid, j, _e(x.get("label", "")), _e(str(x.get("value", ""))),
                       ('<div class="kt">%s</div>' % _e(x["tag"])) if x.get("tag") else "") for j, x in enumerate(kp, 1)),
                   sid, ('<div class="ctitle">%s</div>' % _e(ch.get("title") or ("Values in %s" % ch.get("unit") if ch.get("unit") else ""))) if ch else "", chart,
                   _e(v.get("footer", ""))))
    elif k == "diff":
        items = v.get("items") or []
        body = ('<div class="panel"><h2 class="h" id="%s-h">%s</h2><div class="diffs">%s</div></div>'
                % (sid, head, "".join(
                    '<div class="dcard" id="%s-i%d" data-before="%s" data-after="%s"><div class="dl">%s</div>'
                    '<div class="dv"><span class="db">%s</span><span class="darr">→</span><span class="da" id="%s-da%d">%s</span></div><div class="du">%s</div></div>'
                    % (sid, j, _e(str(x.get("before"))), _e(str(x.get("after"))), _e(x.get("label", "")), _e(str(x.get("before"))), sid, j,
                       _e(str(x.get("before"))), _e(x.get("unit", ""))) for j, x in enumerate(items, 1))))
    elif k == "media":
        src = v.get("src", "")
        if v.get("kind") == "video":
            inner = '<video id="%s-media" src="%s" muted data-start="{start}" data-duration="{dur}" data-track-index="7"></video>' % (sid, _e(src))
        else:
            inner = '<img id="%s-media" src="%s" alt="">' % (sid, _e(src))
        body = ('<div class="panel"><h2 class="h" id="%s-h">%s</h2><div class="mediaframe" id="%s-win">%s</div>%s</div>'
                % (sid, head, sid, inner, ('<p class="cap" id="%s-cap">%s</p>' % (sid, _e(v["caption"]))) if v.get("caption") else ""))
    elif k == "outcomes":
        body = ('<div class="panel"><h2 class="h" id="%s-h">%s</h2><div class="tiles">%s</div></div>'
                % (sid, head, "".join('<div class="tile" id="%s-i%d"><div class="tico">%s</div><div class="ttxt">%s</div></div>'
                                      % (sid, j, ["◆", "▲", "●", "■"][(j - 1) % 4], _e(x)) for j, x in enumerate(v.get("items") or [], 1))))
    elif k == "close":
        body = ('<div class="titlewrap"><p class="tag" id="%s-t1">%s</p><div class="ctabtn" id="%s-i1">%s</div><div class="brand" id="%s-b">%s</div></div>'
                % (sid, _e(v.get("summary", "")), sid, _e(v.get("cta", "")), sid, _e(s.get("brand") or "AIBAST Agents Library")))
    else:
        body = '<div class="panel"><h2 class="h" id="%s-h">%s</h2></div>' % (sid, head)
    return ('<section id="%s" class="clip scene kind-%s" data-start="{start}" data-duration="{dur}" data-track-index="%d">'
            '<div class="stage-in" id="%s-in">%s</div></section>' % (sid, k, 1 + ((i - 1) % 4), sid, body))


STYLES = {
    "mono": ':root{--bg:#07080d;--panel:#0d0f18;--amber:#f0b429;--amber-dim:#7a5a1a;--green:#3ddc84;--ink:#e8e9f0;--muted:#8f95ad;--accent:#f0b429;--grad:linear-gradient(135deg,#f0b429,#c98a12);--line:rgba(255,255,255,.07);--mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;--body:var(--mono)}',
    "solution": ':root{--bg:#0b1230;--panel:#111a3d;--amber:#f77fbe;--amber-dim:#7a3f66;--green:#8f7cff;--ink:#ffffff;--muted:#a9b0d6;--accent:#f77fbe;--grad:linear-gradient(135deg,#f77fbe 0%,#8f5cff 100%);--line:rgba(255,255,255,.08);--mono:"Inter",system-ui,sans-serif;--body:"Inter",system-ui,sans-serif}',
}

CSS = """
*{margin:0;padding:0;box-sizing:border-box}
%(vars)s
html,body{width:%(W)dpx;height:%(H)dpx;overflow:hidden;background:var(--bg);color:var(--ink);font-family:var(--body)}
#root{position:relative;width:%(W)dpx;height:%(H)dpx;overflow:hidden}
.clip{position:absolute;inset:0}
#fill{position:absolute;inset:0;background:radial-gradient(1200px 700px at 50%% -8%%,rgba(247,127,190,.10),transparent 60%%),radial-gradient(900px 600px at 50%% 120%%,rgba(143,92,255,.10),transparent 60%%),var(--bg)}
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
/* solution-mode kinds */
.titlecard{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:22px;text-align:center}
.tname{font-size:96px;line-height:1.05;font-weight:800;color:var(--ink);padding:26px 54px;border-radius:22px;background:var(--grad);box-shadow:0 20px 60px rgba(0,0,0,.35);max-width:1500px;text-wrap:balance}
.persona{font-size:24px;letter-spacing:5px;text-transform:uppercase;color:var(--accent)}
.pain{list-style:none;display:flex;flex-direction:column;gap:22px}
.painitem{display:flex;gap:22px;align-items:flex-start;font-size:40px;line-height:1.3;color:var(--ink);will-change:transform;max-width:1500px}
.painitem .x{color:var(--muted);font-weight:800;font-size:40px}
.triptych{display:grid;grid-template-columns:1fr auto 1fr auto 1fr;gap:18px;align-items:stretch}
.ocol{display:flex;flex-direction:column;gap:14px;will-change:transform}
.otitle{font-size:22px;letter-spacing:4px;text-transform:uppercase;color:var(--muted);text-align:center}
.ocard{background:var(--grad);border-radius:20px;padding:30px 26px;min-height:300px;display:flex;flex-direction:column;justify-content:center;gap:16px;box-shadow:0 14px 40px rgba(0,0,0,.3)}
.oi{font-size:32px;line-height:1.3;font-weight:600;color:#fff;text-align:center}
.arrow{align-self:center;font-size:80px;color:var(--muted);line-height:1;padding-bottom:20px}
.kind-turn .stage-in{top:112px;bottom:150px;justify-content:flex-start;gap:18px}
.kind-turn .h{font-size:44px}
.chatwin{display:grid;grid-template-columns:200px 1fr;background:#f6f7fb;color:#1c1f2a;border-radius:18px;overflow:hidden;box-shadow:0 24px 70px rgba(0,0,0,.45);min-height:520px;max-height:730px;font-family:"Inter",system-ui,sans-serif;will-change:transform}
.rail{background:#eceef6;padding:22px 18px;display:flex;flex-direction:column;gap:14px;font-size:20px;color:#3a3f55}
.rlogo{width:34px;height:34px;border-radius:9px;background:var(--grad);margin-bottom:8px}
.convo{padding:22px 30px;display:flex;flex-direction:column;gap:14px}
.ubub{align-self:flex-end;background:#e6e9f4;border-radius:16px 16px 4px 16px;padding:14px 22px;font-size:26px;line-height:1.3;max-width:1000px;will-change:transform}
.acard{background:#fff;border:1px solid #e3e6f0;border-radius:16px;padding:16px 24px;display:flex;flex-direction:column;gap:10px;will-change:transform}
.aname{display:flex;align-items:center;gap:10px;font-size:20px;color:#3f4a99;font-weight:700}
.adot{width:12px;height:12px;border-radius:50%%;background:var(--grad)}
.alead{font-size:28px;line-height:1.35;font-weight:600;color:#1c1f2a}
.ctab{border-collapse:collapse;font-size:22px;width:100%%}
.ctab th{background:var(--grad);color:#fff;text-align:left;padding:10px 14px;font-weight:700}
.ctab td{padding:7px 14px;border-bottom:1px solid #eceef6;color:#2a2e3d}
.cbul{margin:0;padding-left:28px;font-size:25px;line-height:1.4;color:#2a2e3d}
.benefit{align-self:flex-start;color:var(--accent);font-size:26px;font-weight:700;padding:8px 0;font-family:var(--mono)}
.tiles{display:grid;grid-template-columns:repeat(3,1fr);gap:26px}
.tile{background:var(--grad);border-radius:20px;padding:44px 30px;min-height:300px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:22px;text-align:center;box-shadow:0 14px 40px rgba(0,0,0,.3);will-change:transform}
.tico{font-size:60px;color:#fff;opacity:.9}.ttxt{font-size:36px;font-weight:700;color:#fff;line-height:1.25}
.ctabtn{background:var(--grad);color:#fff;font-weight:800;font-size:40px;padding:26px 54px;border-radius:999px;box-shadow:0 14px 40px rgba(0,0,0,.35);will-change:transform;margin-top:10px}
.brand{font-size:26px;letter-spacing:6px;text-transform:uppercase;color:var(--muted);margin-top:26px}
.rsub{margin-top:14px;font-size:14px;letter-spacing:3px;text-transform:uppercase;color:#4b516a}
.ritem.hist{font-size:15px;line-height:1.25;color:#3a3f55;max-width:164px;overflow-wrap:anywhere}
.alinks{display:flex;flex-wrap:wrap;gap:10px}.alink{font-size:22px;color:#3446b8;text-decoration:underline;text-underline-offset:3px}
.areview{font-size:22px;color:#3a3f55;border-top:1px solid #eceef6;padding-top:10px}.areview::before{content:"Human review required: ";font-weight:700;color:#1c1f2a}
.acall{font-size:19px;color:#3f4a99;font-family:var(--mono)}.acall::before{content:"⚒ ";}
/* workbook */
.sheet{background:#fff;color:#1c1f2a;border-radius:14px;overflow:hidden;box-shadow:0 24px 70px rgba(0,0,0,.45);font-family:"Inter",system-ui,sans-serif;will-change:transform}
.sbar{display:flex;justify-content:space-between;align-items:center;padding:14px 22px;background:#217346;color:#fff;font-size:22px;font-weight:700}
.sprog{font-weight:600;opacity:.9;font-size:20px}
.wtab{border-collapse:collapse;width:100%%;font-size:20px}
.wtab td,.wtab th{padding:8px 14px;border-bottom:1px solid #eef0f6;text-align:left;vertical-align:top}
.wtab th{font-weight:700;color:#3a3f55;background:#f7f8fc}
.whead td{font-weight:800;letter-spacing:.5px;text-transform:uppercase;font-size:18px}
.wsec.c-blue .whead td{background:#dbe7ff;color:#1e3a8a}.wsec.c-blue td{background:#f0f5ff}
.wsec.c-amber .whead td{background:#ffe8b3;color:#7a4b00}.wsec.c-amber td{background:#fff7e0}
.wsec.c-red .whead td{background:#ffd6d6;color:#8a1c1c}.wsec.c-red td{background:#fff0f0}
.wsec.c-purple .whead td{background:#e6dcff;color:#4b2ea8}.wsec.c-purple td{background:#f4efff}
.wsec.c-green .whead td{background:#d3f5df;color:#0f5c2e}.wsec.c-green td{background:#eefbf2}
.wsec.c-gray .whead td{background:#e6e8f0;color:#2a2e3d}
.stabs{display:flex;gap:2px;background:#eceef6;padding:6px 10px 0;font-size:16px}.stabs span{padding:6px 14px;background:#e0e3ee;border-radius:6px 6px 0 0;color:#3a3f55}.stabs span.on{background:#fff;color:#217346;font-weight:700}
/* slide */
.slide{background:#fff;color:#1c1f2a;border-radius:14px;padding:30px 36px;box-shadow:0 24px 70px rgba(0,0,0,.45);font-family:"Inter",system-ui,sans-serif;display:flex;flex-direction:column;gap:14px;will-change:transform;min-height:560px}
.skick{display:flex;justify-content:space-between;font-size:18px;letter-spacing:3px;text-transform:uppercase;color:var(--brand,#5b2d90);font-weight:700}
.sbrand{color:var(--brand,#5b2d90);letter-spacing:1px;text-transform:none;font-size:22px}
.stitle{font-size:38px;line-height:1.2;font-weight:800;color:#1c1f2a;max-width:1500px}
.sbody{display:grid;grid-template-columns:300px 1fr;gap:26px;align-items:start}
.kpis{display:flex;flex-direction:column;gap:14px}
.kpi{border-left:6px solid var(--brand,#5b2d90);padding:6px 14px}.kl{font-size:16px;letter-spacing:2px;text-transform:uppercase;color:#5b6070}.kv{font-size:40px;font-weight:800;line-height:1.1}.kt{font-size:14px;letter-spacing:2px;text-transform:uppercase;color:#92400e;font-weight:700}
.schart{color:#1c1f2a}.ctitle{font-size:18px;color:#5b6070;margin-bottom:6px;font-weight:600}
.schart svg{width:100%%;height:auto;display:block;color:#1c1f2a}
.sfoot{border-top:1px solid #eceef6;padding-top:10px;font-size:18px;color:#5b6070}
/* diff */
.diffs{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:24px}
.dcard{background:var(--panel);border:1px solid var(--line);border-radius:18px;padding:30px 28px;display:flex;flex-direction:column;gap:12px;will-change:transform}
.dl{font-size:22px;letter-spacing:3px;text-transform:uppercase;color:var(--muted)}
.dv{display:flex;align-items:baseline;gap:18px;font-size:70px;font-weight:800;font-variant-numeric:tabular-nums}
.db{color:var(--muted);text-decoration:line-through;font-size:44px}.darr{color:var(--muted);font-size:44px}.da{color:var(--green)}
.du{font-size:20px;color:var(--muted)}
/* media (option 2: real captures) */
.mediaframe{border-radius:14px;overflow:hidden;box-shadow:0 24px 70px rgba(0,0,0,.45);background:#000;max-height:760px}
.mediaframe img,.mediaframe video{display:block;width:100%%;height:auto}
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
    case "title":
      tl.fromTo(id + "-k", { autoAlpha: 0, y: -10 }, { autoAlpha: 1, y: 0, duration: 0.5 }, t + 0.3);
      tl.fromTo(id + "-h", { autoAlpha: 0, scale: 0.94, y: 20 }, { autoAlpha: 1, scale: 1, y: 0, duration: 0.7, ease: "power3.out" }, t + 0.5);
      break;
    case "problem":
      tl.fromTo(id + "-p", { autoAlpha: 0, y: -10 }, { autoAlpha: 1, y: 0, duration: 0.4 }, t + 0.1);
      tl.fromTo(id + "-h", { autoAlpha: 0, x: -40 }, { autoAlpha: 1, x: 0, duration: 0.5, ease: "power3.out" }, t + 0.25);
      break;
    case "close":
      gsap.utils.toArray(id + " .tag").forEach((el, k) => tl.fromTo(el, { autoAlpha: 0, y: 18 }, { autoAlpha: 1, y: 0, duration: 0.5 }, t + 0.2 + k * 0.3));
      tl.fromTo(id + "-i1", { autoAlpha: 0, scale: 0.8 }, { autoAlpha: 1, scale: 1, duration: 0.55, ease: "back.out(1.6)" }, t + 1.0);
      tl.fromTo(id + "-b", { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.5 }, t + 1.5);
      break;
    default:
      tl.fromTo(id + "-h", { autoAlpha: 0, x: -40 }, { autoAlpha: 1, x: 0, duration: 0.5, ease: "power3.out" }, t + 0.1);
  }
  if (sc.kind === "problem") items.forEach((el, k) => tl.fromTo(el, { autoAlpha: 0, x: -40 }, { autoAlpha: 1, x: 0, duration: 0.45, ease: "power3.out" }, t + 0.8 + k * spread(items.length, span) * 2.4));
  if (sc.kind === "overview") {
    items.forEach((el, k) => tl.fromTo(el, { autoAlpha: 0, y: 40 }, { autoAlpha: 1, y: 0, duration: 0.55, ease: "power3.out" }, t + 0.7 + k * 0.5));
    ["-a1", "-a2"].forEach((a, k) => tl.fromTo(id + a, { autoAlpha: 0, x: -20 }, { autoAlpha: 1, x: 0, duration: 0.4 }, t + 1.15 + k * 0.5));
  }
  if (sc.kind === "turn") {
    tl.fromTo(id + "-win", { autoAlpha: 0, y: 30, scale: 0.98 }, { autoAlpha: 1, y: 0, scale: 1, duration: 0.55, ease: "power3.out" }, t + 0.35);
    tl.fromTo(id + "-i1", { autoAlpha: 0, x: 40 }, { autoAlpha: 1, x: 0, duration: 0.45, ease: "power3.out" }, t + 0.9);
    tl.fromTo(id + "-i2", { autoAlpha: 0, y: 30 }, { autoAlpha: 1, y: 0, duration: 0.55, ease: "power3.out" }, t + Math.min(2.2, 0.9 + span * 0.18));
    tl.fromTo(id + "-i3", { autoAlpha: 0, y: 14 }, { autoAlpha: 1, y: 0, duration: 0.45 }, t + Math.min(span - 1.2, 0.9 + span * 0.55));
  }
  if (sc.kind === "workbook") {
    tl.fromTo(id + "-win", { autoAlpha: 0, y: 30 }, { autoAlpha: 1, y: 0, duration: 0.55, ease: "power3.out" }, t + 0.35);
    items.forEach((el, k) => tl.fromTo(el, { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.5 }, t + 0.9 + k * Math.min(1.4, span * 0.18)));
  }
  if (sc.kind === "slide") {
    tl.fromTo(id + "-win", { autoAlpha: 0, y: 30, scale: 0.98 }, { autoAlpha: 1, y: 0, scale: 1, duration: 0.55, ease: "power3.out" }, t + 0.35);
    items.forEach((el, k) => tl.fromTo(el, { autoAlpha: 0, x: -20 }, { autoAlpha: 1, x: 0, duration: 0.45 }, t + 0.9 + k * 0.25));
    const bars = gsap.utils.toArray(id + " rect[id*='-bar'], " + id + " rect[id*='-wf']");
    bars.forEach((el, k) => tl.fromTo(el, { scaleY: 0, transformOrigin: "50%% 100%%" }, { scaleY: 1, duration: 0.5, ease: "power2.out" }, t + 1.3 + k * 0.18));
  }
  if (sc.kind === "diff") {
    items.forEach((el, k) => tl.fromTo(el, { autoAlpha: 0, y: 30 }, { autoAlpha: 1, y: 0, duration: 0.5, ease: "power3.out" }, t + 0.5 + k * 0.3));
    (sc.diff || []).forEach((d, k) => {
      const el = document.getElementById(d.id); if (!el) return;
      const b = parseFloat(d.before), a = parseFloat(d.after);
      if (isNaN(b) || isNaN(a)) { tl.set(el, { textContent: String(d.after) }, t + 1.4 + k * 0.3); return; }
      const dec = Math.max((String(d.before).split(".")[1] || "").length, (String(d.after).split(".")[1] || "").length);
      const proxy = { v: b };
      tl.fromTo(proxy, { v: b }, { v: a, duration: 1.2, ease: "power2.out", onUpdate: () => { el.textContent = proxy.v.toFixed(dec); } }, t + 1.4 + k * 0.3);
    });
  }
  if (sc.kind === "media") tl.fromTo(id + "-win", { autoAlpha: 0, scale: 0.98 }, { autoAlpha: 1, scale: 1, duration: 0.6, ease: "power3.out" }, t + 0.3);
  if (sc.kind === "outcomes") items.forEach((el, k) => tl.fromTo(el, { autoAlpha: 0, y: 50, scale: 0.94 }, { autoAlpha: 1, y: 0, scale: 1, duration: 0.55, ease: "back.out(1.3)" }, t + 0.7 + k * 0.45));
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


def compose_long(doc, slug, spans=None, audio_rel=None, fps=30, chip=None, style=None):
    style = style or ("solution" if doc.get("mode") == "solution" else "mono")
    times, total = timings(doc, spans)
    plan, parts = [], []
    n = len(doc["sections"])
    for i, (s, tm) in enumerate(zip(doc["sections"], times), 1):
        parts.append(section_html(i, s, n).format(start=tm["start"], dur=tm["dur"]))
        plan.append({"id": "s%d" % i, "kind": s.get("kind"), "start": tm["start"], "dur": tm["dur"],
                     "vo_start": tm["vo_start"], "vo_dur": tm["vo_dur"], "exit": i < n,
                     "diff": [{"id": "s%d-da%d" % (i, j), "before": x.get("before"), "after": x.get("after")}
                              for j, x in enumerate((s.get("visual") or {}).get("items") or [], 1)] if s.get("kind") == "diff" else []})
    caps = build_captions(doc, times)
    brand = doc.get("brand") or {}
    vars_css = STYLES.get(style, STYLES["mono"])
    if brand.get("primary"):
        prim = brand["primary"]; sec = brand.get("secondary") or prim
        # on the dark stage the lighter secondary carries accents (contrast); the primary lives on light artifacts
        vars_css += ":root{--brand:%s;--accent:%s;--amber:%s;--grad:linear-gradient(135deg,%s 0%%,%s 100%%)}" % (prim, sec, sec, prim, sec)
    css = CSS % {"W": W, "H": H, "vars": vars_css}
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
