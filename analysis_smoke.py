"""Authenticated end-to-end analysis of the running J.A.R.V.I.S. backend."""

from __future__ import annotations

import json

import httpx

BASE = "http://127.0.0.1:8010"
EMAIL = "admin@localhost"
PASSWORD = "AnalysisLocalhost123"

c = httpx.Client(base_url=BASE, timeout=180.0)

print("=" * 78)
print("LIVE ENDPOINT ANALYSIS  ->", BASE)
print("=" * 78)

spec = c.get("/openapi.json").json()
print(f"\n[api] {len(spec['paths'])} paths exposed")

r = c.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
print(f"[auth] login -> {r.status_code}")
if r.status_code != 200:
    print(r.text[:500])
    raise SystemExit(1)

me = c.get("/api/auth/me").json()
print(f"[auth] me -> {json.dumps(me)[:220]}")

st = c.get("/api/system/status").json()
print("\n[system] status:")
for key in ("overall", "model", "model_source", "provider", "database", "scheduler"):
    if key in st:
        print(f"   {key} = {json.dumps(st[key])[:140]}")
comps = st.get("components") or st.get("checks") or {}
if isinstance(comps, list):
    for comp in comps:
        print(f"   - {comp.get('name')}: {comp.get('status')} {str(comp.get('detail') or '')[:70]}")

hw = c.get("/api/system/hardware").json()
print("\n[hardware]", json.dumps(hw)[:300])

models = c.get("/api/system/models").json()
items = models.get("models") or models.get("installed") or []
print(f"\n[models] {len(items)} installed; selected = {models.get('selected')}")
for m in items:
    if isinstance(m, dict):
        print(
            f"   - {m.get('name'):26} usable={m.get('usable')} cloud={m.get('cloud')} "
            f"{str(m.get('reason') or '')[:60]}"
        )

agents = c.get("/api/system/agents").json()
alist = agents.get("agents", agents if isinstance(agents, list) else [])
print(f"\n[agents] {len(alist)} registered")
for a in alist[:12]:
    print(f"   - {a['name']:18} risk={a['risk_level']:6} tools={a['allowed_tools']}")

tools = c.get("/api/system/tools").json()
tlist = tools.get("tools", tools if isinstance(tools, list) else [])
print(f"\n[tools] {len(tlist)} registered")
for t in tlist:
    print(f"   - {t.get('name'):24} risk={t.get('risk_level')} approval={t.get('requires_approval')}")

print("\n[commands] intent classification:")
for cmd in (
    "Check system health",
    "Prepare a placement outreach email",
    "Research software companies hiring fresh graduates",
    "Audit this website",
    "Show pending placement approvals",
    "Show follow-ups due this week",
    "gibberish nonsense zzz",
):
    res = c.post("/api/commands/classify", json={"command_text": cmd})
    if res.status_code != 200:
        print(f"   {cmd[:44]:46} -> {res.status_code} {res.text[:80]}")
        continue
    d = res.json()
    print(
        f"   {cmd[:44]:46} -> {d.get('intent'):22} ws={d.get('workspace'):10} "
        f"risk={d.get('risk_level'):6} approval={d.get('requires_approval')} "
        f"({d.get('method', d.get('classifier'))})"
    )

run = c.post("/api/commands/run", json={"command_text": "Check system health"})
print(f"\n[commands] run 'Check system health' -> {run.status_code}")
if run.status_code == 200:
    d = run.json()
    print("   ", json.dumps(d)[:700])

jobs = c.get("/api/jobs").json()
jl = jobs.get("jobs", jobs if isinstance(jobs, list) else [])
print(f"\n[jobs] {len(jl)} recorded")

kb_mode = c.get("/api/knowledge/mode").json()
kb_docs = c.get("/api/knowledge/documents").json()
kb = {"mode": kb_mode, "documents": kb_docs}
print("\n[knowledge]", json.dumps(kb)[:300])

ap = c.get("/api/approvals").json()
apl = ap.get("approvals", ap if isinstance(ap, list) else [])
print(f"\n[approvals] {len(apl)} pending/recorded")

aud = c.get("/api/system/audit-events").json()
al = aud.get("events", aud if isinstance(aud, list) else [])
print(f"\n[audit] {len(al)} events; last 5:")
for e in al[-5:]:
    print(f"   - {e.get('action')} {e.get('outcome')} {e.get('risk_level')} {str(e.get('detail'))[:60]}")

sc = c.get("/api/startup-checks").json()
print(f"\n[startup] ok={sc.get('startup_ok')}")
for chk in sc.get("checks", []):
    print(f"   - {chk['check']:12} {chk['ok']} {str(chk['detail'])[:70]}")

print("\n" + "=" * 78)
