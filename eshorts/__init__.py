"""rapp-education-shorts — an animated-short maker for educational YouTube Shorts.

brief → script (JSON, linted) → HyperFrames composition (9:16, one paused GSAP
timeline, seek-safe recipes) → `hyperframes check` → render → chained ledger.

Every stage is a file on disk you can inspect, edit, and re-run. The model (if
you use one) only ever writes the script JSON; the compiler is deterministic.
"""

__version__ = "0.1.0"
SCHEMA_SCRIPT = "rapp-education-short/1.0"
SCHEMA_LEDGER = "rapp-education-shorts-ledger/1.0"
SCENE_KINDS = ("hook", "point", "steps", "compare", "number", "quote", "recap", "cta")
