"""aibast.py — ground a brief in the OFFICIAL AIBAST Agents Library.

Source of truth: https://microsoft.github.io/aibast-agents-library/registry.json —
the 52 advertised solutions carry a `_solution` block (advertised name, executive
summary, industries, personas, featured tools, capabilities, outcomes, customer
scenario, Microsoft AI story, sample prompts) and each solution publishes captured
eval transcripts (persona · prompt · assistant response · agent tables) at
solutions/<slug>/evals/transcripts.json. The video talks about THE SOLUTION the
way the library does — never about how it is built.
"""

import json
import re
import urllib.request

BASE = "https://microsoft.github.io/aibast-agents-library/"

FORBIDDEN_TERMS = ("RAPP", "rapp", "agent.py", "brainstem", "RAR", "registry", "single-file", "single file",
                   "install", "GitHub", "github", "curl", "python", "repo", "repository", "open source", "open-source")


def fetch_json(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "rapp-education-shorts"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def registry():
    return fetch_json(BASE + "registry.json")


def solutions(reg=None):
    reg = reg or registry()
    out = [a for a in reg["agents"] if isinstance(a.get("_solution"), dict) and a["_solution"].get("is_primary", True)]
    return out


def slug_of(agent):
    pkg = (agent.get("_solution") or {}).get("package") or {}
    return pkg.get("slug") or agent["name"].split("/")[-1]


def transcripts(slug):
    try:
        doc = fetch_json(BASE + "solutions/%s/evals/transcripts.json" % slug)
    except Exception:
        return []
    items = doc.get("transcripts") or []
    return [i for i in items if isinstance(i, dict) and i.get("prompt")]


def _clean(text, limit):
    text = re.sub(r"[\U0001F300-\U0001FAFF☀-➿]", "", str(text or ""))
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:limit] + ("…" if len(text) > limit else "")


def brief_for(agent, cases=None):
    """topic / audience / tone / notes for one solution — the notes are the grounding."""
    sol = agent["_solution"]
    name = sol.get("advertised_name") or agent.get("display_name")
    cases = cases if cases is not None else transcripts(slug_of(agent))
    industries = ", ".join(sol.get("industries") or []) or (agent.get("category") or "").replace("_", " ")
    personas = ", ".join(sol.get("personas") or [])
    tools = ", ".join(sol.get("featured_tools") or [])
    lines = []
    lines.append("SOLUTION: %s. %s" % (name, sol.get("executive_summary") or agent.get("description") or ""))
    lines.append("INDUSTRIES: %s. PERSONAS: %s. MICROSOFT PRODUCTS INVOLVED: %s." % (industries, personas, tools))
    if sol.get("microsoft_ai_story"):
        lines.append("HOW IT IS DELIVERED (Microsoft AI story): %s" % sol["microsoft_ai_story"])
    if sol.get("customer_challenge_copy"):
        lines.append("CUSTOMER CHALLENGE: %s" % sol["customer_challenge_copy"])
    if sol.get("customer_scenario"):
        lines.append("%s %s" % (sol.get("challenge_intro") or "Before the agent:", " | ".join(sol["customer_scenario"])))
    if sol.get("opportunity_statements"):
        lines.append("%s %s" % (sol.get("actions_intro") or "With the agent, teams can:", " | ".join(sol["opportunity_statements"])))
    if sol.get("capabilities"):
        lines.append("CAPABILITIES: " + " | ".join(sol["capabilities"]))
    if sol.get("outcomes"):
        lines.append("%s %s" % (sol.get("outcomes_intro") or "Outcomes:", " | ".join(sol["outcomes"])))
    if sol.get("business_value"):
        lines.append("BUSINESS VALUE: " + " | ".join(sol["business_value"]))
    arch = sol.get("architecture") or {}
    if arch.get("business_flow"):
        lines.append("FLOW OF WORK: " + " → ".join(arch["business_flow"]))
    if arch.get("capabilities"):
        lines.append("WHAT THE AGENT DOES (operations): " + " | ".join(
            "%s — %s" % (c.get("name"), c.get("purpose")) for c in arch["capabilities"] if isinstance(c, dict)))
    if cases:
        lines.append("CAPTURED WALKTHROUGH (real prompts and answers from the solution's demo — use these, abridged, for the "
                     "prompt/response turns; keep names, numbers and tables exactly as given, never add new facts):")
        for c in cases[:6]:
            lines.append("  CASE %s (%s; promise: %s)\n    PROMPT: %s\n    ANSWER: %s\n    AGENT TABLES: %s" % (
                c.get("case_id"), c.get("persona"), c.get("onepager_promise"), c.get("prompt"),
                _clean(c.get("assistant_response"), 900), _clean(c.get("agent_logs"), 900)))
    if sol.get("scenario_name"):
        lines.append("EXAMPLE CUSTOMER TO NAME (generic): %s." % sol["scenario_name"])
    lines.append("All account/customer names in the demo are synthetic (e.g. Acme Corporation); it is fine to use them "
                 "as the worked example. Do NOT talk about how the agent is built, packaged, installed or where its code "
                 "lives — this video is about the solution and what the persona gets.")
    return {
        "slug": slug_of(agent),
        "topic": "%s — %s" % (name, sol.get("executive_summary") or agent.get("description") or ""),
        "audience": "business decision makers and %s in %s evaluating Copilot agents" % (personas or "practitioners", industries or "their industry"),
        "tone": "calm, confident, concrete, enterprise-friendly, no hype",
        "notes": "\n".join(lines),
        "meta": {"name": agent["name"], "advertised_name": name, "category": agent.get("category"),
                 "industries": sol.get("industries"), "personas": sol.get("personas"), "tools": sol.get("featured_tools"),
                 "demo_video": sol.get("demo_video"), "cases": len(cases or [])},
    }


def briefs(limit=None, order="industry_first"):
    reg = registry()
    sols = solutions(reg)
    if order == "industry_first":
        sols.sort(key=lambda a: (0 if (a.get("_stack_vertical") or "") not in ("b2b_sales", "general", "") else 1,
                                 a.get("_stack_vertical") or "", a["name"]))
    out = []
    for a in (sols[:limit] if limit else sols):
        out.append(brief_for(a))
    return out


def forbidden_hits(text):
    """Whole-word / whole-token hits only ("repo" must not match "report")."""
    import re as _re
    text = str(text or "")
    hits = set()
    for t in FORBIDDEN_TERMS:
        pat = r"(?<![A-Za-z0-9])" + _re.escape(t) + r"(?![A-Za-z0-9])"
        if _re.search(pat, text):
            hits.add(t)
    return sorted(hits)
