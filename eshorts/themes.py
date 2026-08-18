"""themes.py — palettes for the composition. One accent hue per short (the
kinetic-type rule), a deep background, and two blob colours for the ambient
layer. Pick by name or let the compiler hash the slug into one."""

import hashlib

THEMES = {
    "midnight": {"bg1": "#0b1020", "bg2": "#141b34", "ink": "#f5f7ff", "muted": "#aab3d6",
                 "accent": "#ffcc4d", "accent2": "#7c9cff", "blob1": "#3346a8", "blob2": "#8a2be2",
                 "card": "rgba(255,255,255,0.06)"},
    "ember":    {"bg1": "#170b0b", "bg2": "#2b1210", "ink": "#fff6f0", "muted": "#e0b8a8",
                 "accent": "#ff7a45", "accent2": "#ffd166", "blob1": "#a3341f", "blob2": "#f4a261",
                 "card": "rgba(255,255,255,0.06)"},
    "forest":   {"bg1": "#07140f", "bg2": "#0f2a1f", "ink": "#f1fff7", "muted": "#a9d6be",
                 "accent": "#9ef01a", "accent2": "#5ee6c3", "blob1": "#1b6b4a", "blob2": "#2d9b6f",
                 "card": "rgba(255,255,255,0.06)"},
    "paper":    {"bg1": "#fbf7ee", "bg2": "#f0e8d6", "ink": "#1c1a17", "muted": "#5b554a",
                 "accent": "#d7263d", "accent2": "#1b6ca8", "blob1": "#f6d365", "blob2": "#fda085",
                 "card": "rgba(0,0,0,0.05)"},
    "ocean":    {"bg1": "#031628", "bg2": "#06304f", "ink": "#eaf6ff", "muted": "#a5c8e6",
                 "accent": "#33e0ff", "accent2": "#ffd166", "blob1": "#0f4c81", "blob2": "#1e88a8",
                 "card": "rgba(255,255,255,0.07)"},
}


def pick(name=None, seed=""):
    if name and name in THEMES:
        return name, THEMES[name]
    keys = sorted(THEMES)
    k = keys[int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:4], 16) % len(keys)]
    return k, THEMES[k]
