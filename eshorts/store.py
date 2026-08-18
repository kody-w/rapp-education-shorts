"""store.py — one directory per short, and an append-only, hash-chained ledger.

    shorts/<slug>/
      BRIEF.md            what was asked (topic, audience, tone, length)
      SCRIPT.json         the linted script the compiler reads
      drafts/attempt-N.txt  raw model output, kept as evidence
      project/            the HyperFrames project (index.html, package.json, hyperframes.json)
      out/<slug>.mp4      the render
      out/poster.png      first-frame poster (when a renderer is available)
      state/ledger.jsonl  every stage, chained; each entry names the artifact hash it produced
"""

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import SCHEMA_LEDGER


def utc_now():
    n = datetime.now(timezone.utc)
    return n.strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (n.microsecond // 1000)


def slugify(text, limit=48):
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return re.sub(r"-{2,}", "-", s)[:limit].strip("-") or "short"


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, str(path))
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    os.chmod(path, 0o644)


def write_json(path, value):
    write_text(path, json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


class Short:
    """The working directory of one short."""

    def __init__(self, root, slug):
        self.slug = slugify(slug)
        self.dir = Path(root) / self.slug
        for sub in ("drafts", "project", "out", "state"):
            (self.dir / sub).mkdir(parents=True, exist_ok=True)

    @property
    def brief(self):
        return self.dir / "BRIEF.md"

    @property
    def script(self):
        return self.dir / "SCRIPT.json"

    @property
    def project(self):
        return self.dir / "project"

    @property
    def out(self):
        return self.dir / "out"

    @property
    def ledger_path(self):
        return self.dir / "state" / "ledger.jsonl"

    # ── ledger ───────────────────────────────────────────────────────────
    def read_ledger(self):
        if not self.ledger_path.exists():
            return []
        out = []
        for line in self.ledger_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    out.append(json.loads(line))
                except Exception:
                    out.append({"corrupt": line[:80]})
        return out

    @staticmethod
    def _entry_hash(entry):
        body = {k: v for k, v in entry.items() if k != "hash"}
        return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"),
                                         ensure_ascii=False).encode("utf-8")).hexdigest()

    def record(self, stage, payload):
        entries = self.read_ledger()
        entry = {"schema": SCHEMA_LEDGER, "seq": len(entries), "utc": utc_now(),
                 "stage": stage, "payload": payload,
                 "prev": entries[-1].get("hash") if entries else None}
        entry["hash"] = self._entry_hash(entry)
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.ledger_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
        return entry

    def verify_ledger(self):
        prev = None
        entries = self.read_ledger()
        for i, e in enumerate(entries):
            if "corrupt" in e:
                return False, "entry %d is not JSON" % i
            if e.get("prev") != prev or e.get("seq") != i or self._entry_hash(e) != e.get("hash"):
                return False, "entry %d does not chain" % i
            prev = e["hash"]
        return True, "%d entries verified" % len(entries)

    def status(self):
        led = self.read_ledger()
        mp4 = self.out / (self.slug + ".mp4")
        return {
            "slug": self.slug,
            "dir": str(self.dir),
            "brief": self.brief.exists(),
            "script": self.script.exists(),
            "composed": (self.project / "index.html").exists(),
            "rendered": mp4.exists(),
            "mp4": str(mp4) if mp4.exists() else None,
            "stages": [e.get("stage") for e in led],
            "ledger": self.verify_ledger()[1],
        }
