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

    def test_cli_help(self):
        r = subprocess.run([sys.executable, str(ROOT / "shorts.py"), "--help"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0); self.assertIn("compose", r.stdout)


if __name__ == "__main__":
    unittest.main()
