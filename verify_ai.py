"""Differential verification for the rebuilt ``app.ai`` modules.

Loads each original module straight from its surviving bytecode and compares it
with the reconstructed source across data and representative function inputs.

Usage (from backend/):
    .venv/Scripts/python.exe ../.recovery/verify_ai.py
"""

from __future__ import annotations

import json
import marshal
import pathlib
import sys
import types

BACKEND = pathlib.Path(__file__).resolve().parent.parent / "backend"
AI = BACKEND / "app" / "ai"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def load_original(stem: str, qualname: str):
    """Execute a deleted module's bytecode inside a synthetic package context."""
    sys.modules.setdefault("app.ai", types.ModuleType("app.ai"))
    sys.modules["app.ai"].__path__ = [str(AI)]
    code = marshal.loads((AI / "__pycache__" / f"{stem}.cpython-314.pyc").read_bytes()[16:])
    mod = types.ModuleType(qualname)
    mod.__package__ = "app.ai"
    sys.modules[qualname] = mod
    exec(code, mod.__dict__)
    return mod


FAILURES: list[str] = []


def check(label: str, a, b) -> None:
    if a != b:
        FAILURES.append(label)
        print(f"  FAIL  {label}\n        orig={a!r}\n        new ={b!r}")


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def main() -> int:
    import app.ai.json_utils as new_json
    import app.ai.text_utils as new_text
    import app.ai.profiles as new_profiles
    import app.ai.prompts as new_prompts

    orig_json = load_original("json_utils", "app.ai.json_utils")
    orig_text = load_original("text_utils", "app.ai.text_utils")
    orig_profiles = load_original("profiles", "app.ai.profiles")
    orig_prompts = load_original("prompts", "app.ai.prompts")

    section("ai.prompts")
    names = [n for n in vars(orig_prompts) if n.isupper()]
    check("prompt name set", sorted(names), sorted(n for n in vars(new_prompts) if n.isupper()))
    for n in names:
        check(f"prompt {n}", getattr(orig_prompts, n), getattr(new_prompts, n))
    check("docstring", (orig_prompts.__doc__ or "").strip(), (new_prompts.__doc__ or "").strip())

    section("ai.json_utils data")
    check("_FENCE_RE pattern", orig_json._FENCE_RE.pattern, new_json._FENCE_RE.pattern)
    check("_FENCE_RE flags", orig_json._FENCE_RE.flags, new_json._FENCE_RE.flags)

    section("ai.json_utils functions")
    outputs = [
        '{"a": 1}',
        '```json\n{"a": 1}\n```',
        "Sure! Here you go:\n{\"a\": {\"b\": 2}}\nHope that helps.",
        '{not json}',
        '{"a": "has } brace"}',
        'text {"x": 1} more {"y": 2}',
        '["{\\"a\\":1}"]',
        '"a string with { and }"',
        "",
        None,
        "```\nnot json at all\n```",
        '{"a": 1}',
        '{"escaped": "quote \\" inside"}',
        "no braces here",
        "{",
        "}",
        '{"nested": {"deep": {"deeper": [1,2,{"x":3}]}}}',
    ]
    for raw in outputs:
        try:
            expect = None if raw is None else None
        except Exception:
            pass
        try:
            a = orig_json.extract_json_object(raw) if raw is not None else None
        except Exception as exc:  # pragma: no cover
            a = f"raised {type(exc).__name__}"
        try:
            b = new_json.extract_json_object(raw) if raw is not None else None
        except Exception as exc:  # pragma: no cover
            b = f"raised {type(exc).__name__}"
        check(f"extract_json_object({raw!r:60})", a, b)

    for raw in outputs:
        if raw is None:
            continue
        check(f"strip_code_fences({raw!r:50})", orig_json.strip_code_fences(raw), new_json.strip_code_fences(raw))
        check(f"_first_balanced({raw!r:50})", orig_json._first_balanced_object(raw), new_json._first_balanced_object(raw))

    for v in [True, False, "true", " TRUE ", "yes", "1", "no", "0", "", 0, 1, None, [], [1], "maybe"]:
        check(f"coerce_bool({v!r})", orig_json.coerce_bool(v), new_json.coerce_bool(v))

    section("ai.json_utils validate_payload")
    spec_kwargs = dict(
        name=dict(type=str, required=True, enum=None, default=None),
        count=dict(type=int, required=False, enum=None, default=0),
        mode=dict(type=str, required=False, enum=("a", "b"), default="a"),
        flag=dict(type=bool, required=False, enum=None, default=False),
        note=dict(type=str, required=False, enum=None, default=None),
    )
    ospec = {k: orig_json.FieldSpec(**v) for k, v in spec_kwargs.items()}
    nspec = {k: new_json.FieldSpec(**v) for k, v in spec_kwargs.items()}
    payloads = [
        {"name": "ok", "count": 3, "mode": "A", "flag": True, "note": " hi "},
        {"count": 1},
        {"name": 5},
        {"name": True},
        {"name": "x", "mode": "z"},
        {"name": "x", "count": "not-an-int"},
        {},
        {"name": ""},
        {"name": "x", "flag": "true"},
    ]
    for p in payloads:
        check(f"validate_payload({json.dumps(p)})", orig_json.validate_payload(dict(p), ospec), new_json.validate_payload(dict(p), nspec))

    section("ai.text_utils")
    texts = ["", "hello", "a" * 100, "a" * 10000, None]
    for t in texts:
        if t is None:
            continue
        check(f"estimate_tokens(len={len(t)})", orig_text.estimate_tokens(t), new_text.estimate_tokens(t))
    check("CHARS_PER_TOKEN", orig_text.CHARS_PER_TOKEN, new_text.CHARS_PER_TOKEN)
    for t in [None, "", "short", "x" * 5000]:
        for budget in [-1, 0, 1, 10, 20000]:
            for tail in (False, True):
                if t is None:
                    continue
                check(
                    f"truncate_to_tokens(len={len(t)},max={budget},tail={tail})",
                    orig_text.truncate_to_tokens(t, budget, keep_tail=tail),
                    new_text.truncate_to_tokens(t, budget, keep_tail=tail),
                )
    check(
        "budget_prompt small",
        orig_text.budget_prompt("system rules", "user request"),
        new_text.budget_prompt("system rules", "user request"),
    )
    check(
        "budget_prompt huge",
        orig_text.budget_prompt("S" * 40000, "U" * 40000),
        new_text.budget_prompt("S" * 40000, "U" * 40000),
    )
    check(
        "budget_prompt system=None",
        orig_text.budget_prompt(None, "only user"),
        new_text.budget_prompt(None, "only user"),
    )

    section("ai.profiles data")
    check("_MODEL_RAM_HINTS_GB", orig_profiles._MODEL_RAM_HINTS_GB, new_profiles._MODEL_RAM_HINTS_GB)
    for const in ("PROFILE_TINY", "PROFILE_SMALL", "PROFILE_MEDIUM", "PROFILE_LARGE", "PROFILE_UNSUPPORTED"):
        check(const, getattr(orig_profiles, const), getattr(new_profiles, const))

    section("ai.profiles decision logic")
    cases = [
        dict(total_ram_gb=None, cpu_threads=2, cuda_available=False, gpu_vram_gb=None),
        dict(total_ram_gb=None, cpu_threads=8, cuda_available=False, gpu_vram_gb=None),
        dict(total_ram_gb=3.5, cpu_threads=4, cuda_available=False, gpu_vram_gb=None),
        dict(total_ram_gb=7.8, cpu_threads=4, cuda_available=False, gpu_vram_gb=None),
        dict(total_ram_gb=16.0, cpu_threads=8, cuda_available=False, gpu_vram_gb=None),
        dict(total_ram_gb=32.0, cpu_threads=16, cuda_available=False, gpu_vram_gb=None),
        dict(total_ram_gb=32.0, cpu_threads=8, cuda_available=False, gpu_vram_gb=None),
        dict(total_ram_gb=64.0, cpu_threads=16, cuda_available=True, gpu_vram_gb=24.0),
        dict(total_ram_gb=64.0, cpu_threads=16, cuda_available=True, gpu_vram_gb=12.0),
        dict(total_ram_gb=64.0, cpu_threads=16, cuda_available=True, gpu_vram_gb=8.0),
        dict(total_ram_gb=8.0, cpu_threads=4, cuda_available=True, gpu_vram_gb=None),
    ]
    for case in cases:
        o = orig_profiles.HardwareProfile(**case)
        n = new_profiles.HardwareProfile(**case)
        label = f"ram={case['total_ram_gb']} thr={case['cpu_threads']} cuda={case['cuda_available']} vram={case['gpu_vram_gb']}"
        check(f"estimate_profile({label})", orig_profiles.estimate_profile(o), new_profiles.estimate_profile(n))
        oprof = orig_profiles.estimate_profile(o)
        nprof = new_profiles.estimate_profile(n)
        check(f"_tuning_for({label})", orig_profiles._tuning_for(oprof, o), new_profiles._tuning_for(nprof, n))
        check(f"usable_model_ram_gb({label})", o.usable_model_ram_gb, n.usable_model_ram_gb)
        check(f"as_dict keys({label})", sorted(o.as_dict()), sorted(n.as_dict()))

    for size in ["0.5b", "2b", "5b", "7b", "8b", "12b", "20b", "26b", "70b", "5.1B", " 7B ", "3.5b", "abc", "", None, "0B"]:
        check(f"model_ram_hint_gb({size!r})", orig_profiles.model_ram_hint_gb(size), new_profiles.model_ram_hint_gb(size))

    section("ai.profiles live detection (same machine)")
    o_hw = orig_profiles.detect_hardware()
    n_hw = new_profiles.detect_hardware()
    # These two are read from the live system and legitimately drift between
    # the two calls, so they are compared with a tolerance instead of equality.
    volatile = {"free_ram_gb", "disk_free_gb"}
    for field_name in sorted(o_hw.as_dict()):
        a, b = o_hw.as_dict()[field_name], n_hw.as_dict()[field_name]
        if field_name in volatile and isinstance(a, float) and isinstance(b, float):
            if abs(a - b) <= 0.5:
                print(f"  ok    detect_hardware().{field_name} (volatile: {a} vs {b})")
            else:
                check(f"detect_hardware().{field_name}", a, b)
            continue
        check(f"detect_hardware().{field_name}", a, b)
    print(f"\n  detected profile : {n_hw.profile}")
    print(f"  total RAM (GB)   : {n_hw.total_ram_gb}")
    print(f"  cpu cores/threads: {n_hw.cpu_cores}/{n_hw.cpu_threads}")
    print(f"  gpu              : {n_hw.gpu_name!r} vram={n_hw.gpu_vram_gb} cuda={n_hw.cuda_available}")
    print(f"  disk free (GB)   : {n_hw.disk_free_gb}")
    print(f"  usable model RAM : {n_hw.usable_model_ram_gb} GB")
    print(f"  context / batch  : {n_hw.max_context_tokens} / {n_hw.batch_size}")

    print()
    print(f"FAILURES: {len(FAILURES)}")
    for f in FAILURES:
        print(f"  - {f}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
