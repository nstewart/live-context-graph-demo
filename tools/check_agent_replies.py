"""Leak-audit the agent's RUNTIME replies -- the surface no static guard covers.

Needs a running stack with the agent profile:

    make up-agent LABEL=<name>
    python3 tools/check_agent_replies.py <name>

Exits non-zero on any leak, so it can gate a demo.

check_label_leaks.py proves a label's *authored copy* is clean; check_source_leaks.py
proves *source literals* are clean. Neither sees what the model actually says, which is
assembled at runtime from tool return payloads. This closes that gap using the same
term list, so the standard is identical.
"""
import json, re, sys, urllib.request

sys.path.insert(0, "tools")
from check_label_leaks import GROCERY_TERMS, ALLOWED_PHRASES, IDENTIFIER_RE
from resolve_label import resolve

LABEL = resolve(sys.argv[1] if len(sys.argv) > 1 else "mortgage-underwriting")
ENUMS = {v for m in LABEL.get("enums", {}).values() for v in m}
ENUM_RE = re.compile("|".join(rf"\b{re.escape(v)}\b" for v in sorted(ENUMS, key=len, reverse=True)))

PROMPTS = [
    ("read/health",    "What's the state of underwriting operations right now?"),
    ("read/capacity",  "Which fulfillment centers are at capacity?"),
    ("read/risk",      "Any capacity emergencies?"),
    ("read/detail",    "Show me everything on LN-000501"),
    ("read/search",    "Find loan files for Kyle Lynch"),
    ("read/staff",     "Which underwriters are available at the Mid-Atlantic center?"),
    ("read/programs",  "What jumbo programs do we have capacity for at the Mid-Atlantic center?"),
    ("read/centers",   "List all fulfillment centers"),
    ("read/ontology",  "What entity types exist in the graph and how do they connect?"),
    ("write/status",   "Mark LN-000504 as in underwriting"),
    ("write/lines",    "Add a VA cash-out refinance to loan file LN-000501"),
]

def ask(msg, thread):
    body = json.dumps({"message": msg, "thread_id": thread}).encode()
    req = urllib.request.Request("http://localhost:8081/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=240)).get("response", "")

def leaks(text):
    prose = IDENTIFIER_RE.sub(" ", text)
    prose = ENUM_RE.sub(" ", prose)
    prose = prose.lower()
    for p in ALLOWED_PHRASES:
        prose = prose.replace(p, " ")
    hits = []
    for term in GROCERY_TERMS:
        for m in re.finditer(rf"\b{re.escape(term)}\w*", prose):
            hits.append((term, prose[max(0, m.start()-45):m.end()+35].replace("\n", " ")))
            break
    return hits

total = 0
for i, (tag, prompt) in enumerate(PROMPTS):
    try:
        reply = ask(prompt, f"audit-{i}")
    except Exception as e:
        print(f"[{tag}] ERROR {e}"); continue
    h = leaks(reply)
    total += len(h)
    mark = "LEAK" if h else "ok  "
    print(f"{mark} [{tag}] {prompt}")
    for term, ctx in h:
        print(f"       '{term}' -> ...{ctx}...")
print(f"\n{total} leaked term(s) across {len(PROMPTS)} prompts")
sys.exit(1 if total else 0)
