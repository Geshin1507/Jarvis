"""Differential verification: rebuilt agents/registry.py vs recovered bytecode."""

from __future__ import annotations

import json
import marshal
import pathlib
import sys
import types

sys.path.insert(0, ".")

FAILS: list[str] = []


def check(label: str, a, b) -> None:
    if a != b:
        FAILS.append(f"{label}: orig={a!r} new={b!r}")


def load_orig(pyc: str, name: str, package: str):
    code = marshal.loads(pathlib.Path(pyc).read_bytes()[16:])
    mod = types.ModuleType(name)
    mod.__package__ = package
    sys.modules[name] = mod
    exec(code, mod.__dict__)
    return mod


orig = load_orig(
    "app/agents/__pycache__/registry.cpython-314.pyc", "_orig_registry", "app.agents"
)
from app.agents import registry as mine  # noqa: E402

check("FORBIDDEN_TOOLS", orig.FORBIDDEN_TOOLS, mine.FORBIDDEN_TOOLS)
check("FORBIDDEN_CAPABILITIES", orig.FORBIDDEN_CAPABILITIES, mine.FORBIDDEN_CAPABILITIES)
check("INTENT_AGENT_MAP", orig.INTENT_AGENT_MAP, mine.INTENT_AGENT_MAP)
check("INTENT_AGENT_MAP order", list(orig.INTENT_AGENT_MAP), list(mine.INTENT_AGENT_MAP))
check("AGENTS keys", list(orig.AGENTS), list(mine.AGENTS))

for key in orig.AGENTS:
    if key not in mine.AGENTS:
        FAILS.append(f"AGENTS missing {key}")
        continue
    o, n = orig.AGENTS[key], mine.AGENTS[key]
    check(f"{key}.as_dict", o.as_dict(), n.as_dict())
    check(f"{key}.input_schema", o.input_schema, n.input_schema)
    check(f"{key}.output_schema", o.output_schema, n.output_schema)
    check(f"{key}.system_prompt", o.system_prompt, n.system_prompt)
    check(f"{key}.system_prompt is prompts.X", o.system_prompt, n.system_prompt)
    check(f"{key} frozen", o.__class__.__dataclass_params__.frozen, n.__class__.__dataclass_params__.frozen)

# dataclass field names + defaults
check(
    "dataclass fields",
    [(f.name, f.default) for f in orig.AGENTS["voice"].__dataclass_fields__.values()],
    [(f.name, f.default) for f in mine.AGENTS["voice"].__dataclass_fields__.values()],
)

check("validate_registry", orig.validate_registry(), mine.validate_registry())
check("registry_summary", orig.registry_summary(), mine.registry_summary())
check("get_agent missing", orig.get_agent("nope"), mine.get_agent("nope"))
check("agent_for_intent unknown", orig.agent_for_intent("unknown").name, mine.agent_for_intent("unknown").name)
check("agent_for_intent all", [orig.agent_for_intent(i).name for i in orig.INTENT_AGENT_MAP],
      [mine.agent_for_intent(i).name for i in mine.INTENT_AGENT_MAP])

TOOLS = list(orig.FORBIDDEN_TOOLS) + [
    "system_health", "search_knowledge", "search_database", "fetch_public_page",
    "create_evidence", "update_crm_record", "create_opportunity", "read_student_data",
    "run_website_audit", "create_report", "read_approved_document", "create_draft",
    "create_approval_request", "schedule_reminder", "nope",
]
mismatch = 0
for agent in list(orig.AGENTS) + ["nope"]:
    for tool in TOOLS:
        if orig.agent_allows_tool(agent, tool) != mine.agent_allows_tool(agent, tool):
            mismatch += 1
            FAILS.append(f"agent_allows_tool({agent},{tool}) mismatch")
check("allow_tool cases", 0, mismatch)

# docstrings must match exactly
for name in ("_agents", "get_agent", "agent_for_intent", "agent_allows_tool",
             "registry_summary", "validate_registry"):
    check(f"{name}.__doc__", getattr(getattr(orig, name), "__doc__", None),
          getattr(getattr(mine, name), "__doc__", None))
check("as_dict.__doc__", orig.AGENTS["voice"].as_dict.__doc__, mine.AGENTS["voice"].as_dict.__doc__)
check("module __doc__", orig.__doc__, mine.__doc__)
check("AgentSpec __doc__", orig.AgentSpec.__doc__, mine.AgentSpec.__doc__)

print(json.dumps({"checks_failed": len(FAILS), "failures": FAILS[:25]}, indent=2))
