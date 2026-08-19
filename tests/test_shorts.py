"""stdlib tests — no model, no browser. Break/control pairs on the lint gate, the
timing derivation, the compiler's contract invariants, and the ledger."""

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from eshorts import compose as C, pipeline as P, script as S  # noqa: E402
from eshorts.store import Short  # noqa: E402

EX = json.loads((ROOT / "examples" / "why-is-the-sky-blue.SCRIPT.json").read_text())


class LintTests(unittest.TestCase):
    def test_control_example_passes(self):
        self.assertEqual(S.lint_script(EX), [])

    def test_break_structure(self):
        d = json.loads(json.dumps(EX)); d["scenes"][0]["kind"] = "point"
        self.assertTrue(any("must be a hook" in f for f in S.lint_script(d)))
        d = json.loads(json.dumps(EX)); d["scenes"][1]["lines"] = ["one two three four five six seven eight nine ten eleven twelve thirteen"]
        self.assertTrue(any("words (max" in f for f in S.lint_script(d)))
        d = json.loads(json.dumps(EX)); d["scenes"][3]["visual"]["value"] = "lots"
        self.assertTrue(any("(number)" in f for f in S.lint_script(d)))
        d = json.loads(json.dumps(EX)); d["scenes"][2]["heading"] = "See www.example.com"
        self.assertTrue(any("blocked" in f for f in S.lint_script(d)))
        d = json.loads(json.dumps(EX)); d["scenes"] = d["scenes"][:3] + [dict(s, lines=["w " * 12] * 3) for s in d["scenes"][1:2]] * 9
        self.assertTrue(any("scene count" in f or "exceeds" in f for f in S.lint_script(d)))

    def test_timing_is_derived_and_bounded(self):
        times, total = S.timeline(EX)
        self.assertEqual(len(times), len(EX["scenes"]))
        for t in times:
            self.assertTrue(S.MIN_SCENE_S <= t["duration"] <= S.MAX_SCENE_S)
        self.assertLessEqual(total, S.MAX_TOTAL_S)
        # sequential, non-overlapping
        for a, b in zip(times, times[1:]):
            self.assertAlmostEqual(a["start"] + a["duration"], b["start"], places=2)


class ComposeTests(unittest.TestCase):
    def test_contract_invariants(self):
        out = C.compose(EX, "sky", theme="midnight")
        html = out["index.html"]
        self.assertEqual(html, C.compose(EX, "sky", theme="midnight")["index.html"])   # deterministic
        self.assertIn('data-composition-id="short" data-start="0" data-width="1080" data-height="1920"', html)
        self.assertIn('window.__timelines["short"] = tl;', html)
        self.assertIn("gsap.timeline({ paused: true })", html)
        self.assertNotIn("repeat: -1", html)
        self.assertNotIn("Math.random", html)
        self.assertNotIn("Date.now", html)
        self.assertNotIn("transition:", html)                       # no CSS transitions on animated elements
        self.assertNotIn("<br", html)
        ids = re.findall(r'\bid="([^"]+)"', html)
        self.assertEqual(len(ids), len(set(ids)), "duplicate ids")
        # every scene is a direct-child clip with sequential timing
        clips = re.findall(r'<section id="s(\d+)" class="clip scene kind-(\w+)" data-start="([\d.]+)" data-duration="([\d.]+)" data-track-index="(\d)"', html)
        self.assertEqual(len(clips), len(EX["scenes"]))
        for a, b in zip(clips, clips[1:]):
            self.assertAlmostEqual(float(a[2]) + float(a[3]), float(b[2]), places=2)
        # a full-bleed background CHILD, never the root's own background
        self.assertIn('id="bgfill"', html)
        self.assertNotIn('id="root" style=', html)

    def test_emphasis_wraps_whole_words_only(self):
        self.assertIn('<em class="hi">blue', C.emphasise("The blue sky is bluer", ["blue"]))
        self.assertNotIn("<em class=\"hi\">blue<span class=\"u\"></span></em>r", C.emphasise("bluer", ["blue"]))
        self.assertIn("&lt;", C.emphasise("<script>", []))          # escaped

    def test_all_kinds_render_something(self):
        for i, s in enumerate(EX["scenes"], 1):
            h = C.scene_html(i, s, len(EX["scenes"]))
            self.assertIn('id="s%d-h"' % i, h)


class PipelineTests(unittest.TestCase):
    def test_brief_script_compose_and_ledger(self):
        with tempfile.TemporaryDirectory() as d:
            sh = Short(d, "Sky Test!")
            self.assertEqual(sh.slug, "sky-test")
            P.brief(sh, "why the sky is blue", audience="kids")
            self.assertTrue(sh.brief.exists())
            sc, findings = P.script(sh, from_file=str(ROOT / "examples" / "why-is-the-sky-blue.SCRIPT.json"))
            self.assertEqual(findings, []); self.assertTrue(sh.script.exists())
            comp = P.compose_project(sh, theme="ocean")
            self.assertTrue((sh.project / "index.html").exists())
            self.assertTrue((sh.project / "package.json").exists())
            self.assertEqual(comp["theme"], "ocean")
            stages = [e["stage"] for e in sh.read_ledger()]
            self.assertEqual(stages, ["brief", "script", "compose"])
            self.assertTrue(sh.verify_ledger()[0])
            # tamper → detected
            lines = sh.ledger_path.read_text().splitlines()
            e = json.loads(lines[1]); e["payload"]["scenes"] = 99
            lines[1] = json.dumps(e, sort_keys=True); sh.ledger_path.write_text("\n".join(lines) + "\n")
            self.assertFalse(sh.verify_ledger()[0])

    def test_refused_script_is_recorded(self):
        with tempfile.TemporaryDirectory() as d:
            sh = Short(d, "bad")
            bad = json.loads(json.dumps(EX)); bad["scenes"][0]["kind"] = "point"
            Path(d, "bad.json").write_text(json.dumps(bad))
            sc, findings = P.script(sh, from_file=str(Path(d, "bad.json")))
            self.assertIsNone(sc); self.assertTrue(findings)
            self.assertEqual(sh.read_ledger()[-1]["stage"], "script.refused")

    def test_model_retry_with_feedback(self):
        calls = []
        def runner(prompt, model, timeout, workdir):
            calls.append(prompt)
            if len(calls) == 1:
                return "```json\n" + json.dumps({"schema": S.SCHEMA_SCRIPT, "title": "t", "topic": "x", "scenes": []}) + "\n```", None
            return json.dumps(EX), None
        sc, findings, log = S.write_script({"topic": "x"}, runner=runner, drafts_dir=tempfile.mkdtemp())
        self.assertIsNotNone(sc); self.assertEqual(len(log), 2)
        self.assertIn("PREVIOUS ATTEMPT WAS REFUSED", calls[1])
        self.assertIn("NO TOOLS", calls[0])

    def test_batch_is_resumable_and_never_stops(self):
        with tempfile.TemporaryDirectory() as d:
            ex = str(ROOT / "examples" / "why-is-the-sky-blue.SCRIPT.json")
            bad = Path(d, "bad.json"); bad.write_text("{not json")
            briefs = [{"slug": "one", "topic": "t", "script": ex}, {"slug": "two", "topic": "t", "script": str(bad)}]
            summary, results = P.batch(Path(d, "root"), briefs, skip_render=True, log=lambda m: None)
            self.assertEqual(results[0]["outcome"] in ("composed", "check_failed"), True)
            self.assertEqual(results[1]["outcome"], "error")
            self.assertTrue(Path(d, "root", "batch-ledger.jsonl").exists())
            self.assertEqual(sum(summary[k] for k in summary if k != "total"), 2)

    def test_cli_help(self):
        r = subprocess.run([sys.executable, str(ROOT / "shorts.py"), "--help"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0); self.assertIn("compose", r.stdout)


if __name__ == "__main__":
    unittest.main()


class LongFormTests(unittest.TestCase):
    def setUp(self):
        from eshorts import long as L, compose_long as CL
        self.L, self.CL = L, CL
        self.doc = json.loads((ROOT / "examples" / "account-intelligence.LONG.json").read_text())

    def test_control_example_passes_lint(self):
        self.assertEqual(self.L.lint_long(self.doc), [])

    def test_break_structure(self):
        d = json.loads(json.dumps(self.doc)); d["sections"][0]["kind"] = "explain"
        self.assertTrue(any("cold_open" in f for f in self.L.lint_long(d)))
        d = json.loads(json.dumps(self.doc)); d["sections"][1]["narration"] = "too short"
        self.assertTrue(any("narration has" in f for f in self.L.lint_long(d)))
        d = json.loads(json.dumps(self.doc)); d["sections"][1]["narration"] += " see http://x.com"
        self.assertTrue(any("blocked" in f for f in self.L.lint_long(d)))
        # the terminal card MAY carry a URL
        self.assertEqual(self.L.lint_long(self.doc), [])

    def test_timings_wrap_measured_audio_and_stay_contiguous(self):
        spans = [(0.0, 20.0), (20.45, 22.0), (42.9, 18.0), (61.35, 20.0), (81.8, 15.0), (97.25, 19.0), (116.7, 21.0), (138.15, 17.0)]
        times, total = self.CL.timings(self.doc, spans)
        self.assertEqual(len(times), len(self.doc["sections"]))
        for a, b in zip(times, times[1:]):
            self.assertAlmostEqual(a["start"] + a["dur"], b["start"], places=3)
        self.assertGreater(total, spans[-1][0] + spans[-1][1])
        # without audio, durations are derived and still contiguous
        times2, total2 = self.CL.timings(self.doc, None)
        for a, b in zip(times2, times2[1:]):
            self.assertAlmostEqual(a["start"] + a["dur"], b["start"], places=3)

    def test_compose_long_invariants(self):
        out = self.CL.compose_long(self.doc, "ai", spans=None)
        h = out["index.html"]
        self.assertIn('data-composition-id="long" data-start="0" data-width="1920" data-height="1080"', h)
        self.assertIn('window.__timelines["long"] = tl;', h)
        self.assertNotIn("repeat: -1", h); self.assertNotIn("Math.random", h); self.assertNotIn("transition:", h)
        ids = re.findall(r'\bid="([^"]+)"', h); self.assertEqual(len(ids), len(set(ids)))
        self.assertIn('id="capband" class="clip"', h)
        self.assertNotIn("<audio", h)
        out2 = self.CL.compose_long(self.doc, "ai", spans=[(i * 20.0, 18.0) for i in range(len(self.doc["sections"]))],
                                    audio_rel="assets/narration.wav")
        self.assertIn('<audio id="vo" src="assets/narration.wav"', out2["index.html"])
        self.assertGreater(out2["captions"], 20)

    def test_artifact_kinds_lint_and_render(self):
        d = json.loads(json.dumps(self.doc))
        d["mode"] = "solution"; d["brand"] = {"name": "Contoso", "primary": "#5b2d90", "secondary": "#8f5cff"}
        secs = [
            {"kind": "title", "heading": "X Copilot", "narration": "", "visual": {"type": "titlecard", "name": "X Copilot", "kicker": "Finance"}},
            {"kind": "problem", "heading": "Today", "narration": " ".join(["w"] * 40), "visual": {"type": "pain", "persona": "Analyst", "items": ["a", "b"]}},
            {"kind": "overview", "heading": "Now", "narration": " ".join(["w"] * 40), "visual": {"type": "triptych", "sources": ["A"], "flow": ["B"], "actions": ["C"]}},
            {"kind": "turn", "heading": "Ask", "narration": " ".join(["w"] * 40), "visual": {"type": "chat", "prompt": "p", "response": {"lead": "l", "table": {"headers": ["a", "b"], "rows": [["1", "2"], ["3", "4"]]}}, "benefit": "b", "agent_call": "VarianceAnalysis", "review_line": "analyst owns interpretation", "links": ["Open Excel review pack"]}},
            {"kind": "workbook", "heading": "Sheet", "narration": " ".join(["w"] * 30), "visual": {"type": "workbook", "title": "LIVE REVIEW", "progress": {"step": 2, "total": 6}, "sections": [{"name": "2 · Reconcile", "color": "blue", "headers": ["Item", "Value"], "rows": [["CE vs Budget", "+30.0"]]}]}},
            {"kind": "slide", "heading": "Slide", "narration": " ".join(["w"] * 30), "visual": {"type": "slide", "kicker": "BUDGET", "title": "T", "kpis": [{"label": "CE", "value": "$1,000.0"}], "chart": {"type": "waterfall", "items": [{"label": "Budget", "value": 970}, {"label": "Price", "value": 10}, {"label": "CE", "value": 1000}]}, "footer": "f"}},
            {"kind": "turn", "heading": "Fix", "narration": " ".join(["w"] * 40), "visual": {"type": "chat", "prompt": "p", "response": {"lead": "l"}, "benefit": "b"}},
            {"kind": "diff", "heading": "Closed loop", "narration": " ".join(["w"] * 30), "visual": {"type": "diff", "items": [{"label": "Residual", "before": 0.5, "after": 0.0, "unit": "USD millions"}]}},
            {"kind": "turn", "heading": "Deck", "narration": " ".join(["w"] * 40), "visual": {"type": "chat", "prompt": "p", "response": {"lead": "l"}, "benefit": "b"}},
            {"kind": "outcomes", "heading": "How", "narration": " ".join(["w"] * 40), "visual": {"type": "tiles", "items": ["a", "b", "c"]}},
            {"kind": "close", "heading": "Close", "narration": " ".join(["w"] * 30), "visual": {"type": "cta", "summary": "s", "cta": "c"}},
        ]
        d["sections"] = secs
        self.assertEqual(self.L.lint_long(d), [])
        html = self.CL.compose_long(d, "x")["index.html"]
        for needle in ("LIVE REVIEW", "Workflow progress: 2 of 6", "wsec c-blue", 'class="wf"', "Agent Calls: VarianceAnalysis",
                       "Open Excel review pack", "--brand:#5b2d90", 'data-before="0.5"', "areview"):
            self.assertIn(needle, html)
        bad = json.loads(json.dumps(d)); bad["sections"][5]["visual"]["chart"]["type"] = "pie"
        self.assertTrue(any("bars|waterfall" in f for f in self.L.lint_long(bad)))

    def test_caption_chunks_never_orphan(self):
        chunks = self.L.caption_chunks("One two three four five six seven eight nine ten eleven twelve thirteen. Short one.")
        self.assertTrue(all(1 <= len(c.split()) <= 11 for c in chunks))
