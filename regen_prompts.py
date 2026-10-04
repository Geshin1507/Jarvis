"""Regenerate ``app/ai/prompts.py`` from recovered bytecode.

The prompt strings are the one place where exact wording matters more than
structure, and they are pure string constants. Executing the surviving bytecode
yields the original values, so we emit them back as source literals (falling
back to ``repr`` when a value cannot be written safely as a triple-quoted
literal).

Usage (from backend/):
    .venv/Scripts/python.exe ../.recovery/regen_prompts.py
"""

from __future__ import annotations

import marshal
import pathlib
import sys
import types

BACKEND = pathlib.Path(__file__).resolve().parent.parent / "backend"
PYC = BACKEND / "app" / "ai" / "__pycache__" / "prompts.cpython-314.pyc"
TARGET = BACKEND / "app" / "ai" / "prompts.py"

HEADER = """\"\"\"{doc}\"\"\"

from __future__ import annotations

"""

ORDER = [
    "COMMON_RULES",
    "IDENTITY",
    "CLASSIFIER_SYSTEM",
    "CLASSIFIER_SCHEMA_HINT",
    "ORCHESTRATOR_SYSTEM",
    "RESEARCH_SYSTEM",
    "COMMERCIAL_SYSTEM",
    "PLACEMENT_SYSTEM",
    "AUDIT_SYSTEM",
    "KNOWLEDGE_SYSTEM",
    "OUTREACH_SYSTEM",
    "CALL_SCRIPT_SYSTEM",
    "APPROVAL_SYSTEM",
    "SYSTEM_HEALTH_SYSTEM",
    "SCHEDULER_SYSTEM",
    "VOICE_SYSTEM",
    "OPPORTUNITY_EXTRACT_SYSTEM",
    "FOLLOWUP_SUMMARY_SYSTEM",
    "REPORT_SYSTEM",
]


def load_recovered():
    sys.modules.setdefault("app.ai", types.ModuleType("app.ai"))
    sys.modules["app.ai"].__path__ = [str(BACKEND / "app" / "ai")]
    code = marshal.loads(PYC.read_bytes()[16:])
    mod = types.ModuleType("app.ai.prompts")
    mod.__package__ = "app.ai"
    sys.modules["app.ai.prompts"] = mod
    exec(code, mod.__dict__)
    return mod


def literal(value: str) -> tuple[str, bool]:
    """Return (source literal, used_triple_quotes)."""
    safe = '"""' not in value and not value.endswith('"') and "\\" not in value
    if safe:
        return f'"""{value}"""', True
    return repr(value), False


def main() -> int:
    mod = load_recovered()
    doc = (mod.__doc__ or "").strip()

    missing = [n for n in ORDER if not hasattr(mod, n)]
    if missing:
        raise SystemExit(f"recovered module is missing: {missing}")

    parts = [HEADER.format(doc=doc)]
    fallbacks: list[str] = []
    for name in ORDER:
        value = getattr(mod, name)
        if not isinstance(value, str):
            raise SystemExit(f"{name} is {type(value).__name__}, expected str")
        src, triple = literal(value)
        if not triple:
            fallbacks.append(name)
        parts.append(f"{name} = {src}\n\n")

    TARGET.write_text("".join(parts), encoding="utf-8")

    # verify the written file reproduces the recovered values exactly
    ns: dict = {}
    exec(compile(TARGET.read_text(encoding="utf-8"), str(TARGET), "exec"), ns)
    mismatches = [n for n in ORDER if ns[n] != getattr(mod, n)]
    extra = [
        n
        for n in vars(mod)
        if (n.isupper() or (n[:1].isupper() and not n.startswith("_"))) and n not in ORDER
    ]

    print(f"wrote {TARGET}")
    print(f"constants written : {len(ORDER)}")
    print(f"triple-quoted     : {len(ORDER) - len(fallbacks)}")
    print(f"repr fallbacks    : {fallbacks or 'none'}")
    print(f"value mismatches  : {mismatches or 'none'}")
    print(f"unaccounted names : {extra or 'none'}")
    print(f"total prompt text : {sum(len(getattr(mod, n)) for n in ORDER)} chars")
    return 1 if (mismatches or extra) else 0


if __name__ == "__main__":
    sys.exit(main())
