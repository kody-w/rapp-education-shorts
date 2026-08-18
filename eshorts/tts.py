"""tts.py — local narration for long-form videos.

Default engine: Microsoft VibeVoice (VibeVoice-Realtime-0.5B), run locally through
its own demo script with a monkeypatch that lets torch>=2.6 load the voice presets
(they carry a BaseModelOutputWithPast, so torch.load(weights_only=True) refuses
them). No network at synthesis time once the weights are cached.

Configure via env or config:
    VIBEVOICE_PYTHON   python of a venv where `pip install -e <VibeVoice checkout>` ran
    VIBEVOICE_REPO     the checkout (needs demo/realtime_model_inference_from_file.py)
    VIBEVOICE_VOICE    e.g. en-davis_man (default), en-emma_woman, en-carter_man ...
    VIBEVOICE_DEVICE   mps | cuda | cpu

Fallback: engine "none" — no audio; durations are derived from words like a Short.
Every synthesized WAV is measured with ffprobe: the composition is timed from what
the narration actually is, never from what the script guessed.
"""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

DRIVER = r'''
import runpy, sys, torch
_orig = torch.load
def _load(*a, **k):
    k["weights_only"] = False   # trusted Microsoft voice presets
    return _orig(*a, **k)
torch.load = _load
sys.argv = [sys.argv[1]] + sys.argv[2:]
runpy.run_path(sys.argv[0], run_name="__main__")
'''


def vibevoice_config():
    home = Path.home()
    py = os.environ.get("VIBEVOICE_PYTHON") or ""
    repo = os.environ.get("VIBEVOICE_REPO") or ""
    if not py:
        for cand in (home / ".rapp-mirror" / "venv" / "bin" / "python", home / "VibeVoice" / ".venv" / "bin" / "python",
                     home / "VibeVoice" / "venv" / "bin" / "python"):
            if cand.exists():
                py = str(cand)
                break
    if not repo:
        for cand in (home / "VibeVoice", home / ".rapp-mirror" / "VibeVoice"):
            if (cand / "demo" / "realtime_model_inference_from_file.py").exists():
                repo = str(cand)
                break
    return {"python": py, "repo": repo,
            "voice": os.environ.get("VIBEVOICE_VOICE") or "en-davis_man",
            "device": os.environ.get("VIBEVOICE_DEVICE") or "mps",
            "model": os.environ.get("VIBEVOICE_MODEL") or "microsoft/VibeVoice-Realtime-0.5B"}


def vibevoice_available():
    c = vibevoice_config()
    return bool(c["python"] and c["repo"] and Path(c["python"]).exists()
                and Path(c["repo"], "demo", "realtime_model_inference_from_file.py").exists())


def wav_duration(path):
    if not shutil.which("ffprobe"):
        return None
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return None


def synthesize(text, out_wav, workdir, timeout=900):
    """One text → one WAV at out_wav. Returns (ok, detail)."""
    c = vibevoice_config()
    if not vibevoice_available():
        return False, "VibeVoice not available (set VIBEVOICE_PYTHON / VIBEVOICE_REPO)"
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    txt = workdir / "narration.txt"
    txt.write_text(text.strip() + "\n", encoding="utf-8")
    outdir = workdir / "vv-out"
    if outdir.exists():
        shutil.rmtree(outdir)
    outdir.mkdir()
    driver = workdir / "vv_run.py"
    driver.write_text(DRIVER, encoding="utf-8")
    demo = str(Path(c["repo"]) / "demo" / "realtime_model_inference_from_file.py")
    argv = [c["python"], str(driver), demo, "--model_path", c["model"], "--txt_path", str(txt),
            "--speaker_name", c["voice"], "--output_dir", str(outdir), "--device", c["device"]]
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, cwd=c["repo"],
                           stdin=subprocess.DEVNULL, env=dict(os.environ, PYTHONUNBUFFERED="1"))
    except subprocess.TimeoutExpired:
        return False, "vibevoice timed out after %ss" % timeout
    wavs = sorted(outdir.glob("*.wav"))
    if r.returncode != 0 or not wavs:
        return False, "vibevoice exit %d: %s" % (r.returncode, (r.stderr or r.stdout or "")[-400:].strip())
    shutil.move(str(wavs[0]), str(out_wav))
    return True, str(out_wav)


def concat_wavs(parts, out_wav, gap_s=0.45):
    """Join WAVs with silence gaps. Returns [(start, duration)] per part, or None."""
    if not shutil.which("ffmpeg"):
        return None
    durs = [wav_duration(p) for p in parts]
    if any(d is None for d in durs):
        return None
    # measure sample rate from the first part
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=sample_rate,channels",
                        "-of", "json", str(parts[0])], capture_output=True, text=True)
    try:
        st = json.loads(r.stdout)["streams"][0]
        sr, ch = int(st["sample_rate"]), int(st.get("channels") or 1)
    except Exception:
        sr, ch = 24000, 1
    with tempfile.TemporaryDirectory() as td:
        sil = Path(td) / "sil.wav"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                        "anullsrc=r=%d:cl=%s" % (sr, "mono" if ch == 1 else "stereo"), "-t", str(gap_s), str(sil)],
                       check=False)
        lst = Path(td) / "list.txt"
        lines, spans, t = [], [], 0.0
        for p, d in zip(parts, durs):
            lines.append("file '%s'" % str(Path(p).resolve()).replace("'", r"'\''"))
            spans.append((round(t, 3), round(d, 3)))
            t += d
            lines.append("file '%s'" % str(sil.resolve()))
            t += gap_s
        lst.write_text("\n".join(lines) + "\n", encoding="utf-8")
        r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                            "-c", "copy", str(out_wav)], capture_output=True, text=True)
        if r.returncode != 0:
            r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                                str(out_wav)], capture_output=True, text=True)
            if r.returncode != 0:
                return None
    return spans
