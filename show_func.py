"""Show full detail for a single code object inside a recovered module.

Usage (from backend/):
    .venv/Scripts/python.exe ../.recovery/show_func.py <module> [name] [--all]

  <module>  dotted module path under app/, e.g. logging_setup, services.approvals
  <name>    optional qualname or name filter (substring, case-insensitive)
  --all     print every code object in the module

Without a name filter and without --all, only module-level detail is printed.
"""

from __future__ import annotations

import dis
import importlib.util
import marshal
import pathlib
import sys
from types import CodeType

APP = pathlib.Path(__file__).resolve().parent.parent / "backend" / "app"
MAGIC = importlib.util.MAGIC_NUMBER


def find_pyc(module: str) -> pathlib.Path:
    parts = module.split(".")
    pkg = APP.joinpath(*parts[:-1]) / "__pycache__"
    target = f"{parts[-1]}.cpython-314.pyc"
    p = pkg / target
    if not p.exists():
        cands = list(pkg.glob(f"{parts[-1]}.*.pyc"))
        if not cands:
            raise SystemExit(f"no bytecode for module {module} in {pkg}")
        return cands[0]
    return p


def code_iter(code: CodeType, prefix: str = ""):
    yield prefix, code
    for const in code.co_consts:
        if isinstance(const, CodeType):
            child = f"{prefix}.{const.co_name}" if prefix else const.co_name
            yield from code_iter(const, child)


def describe(prefix: str, code: CodeType, defaults_seen: tuple | None = None) -> None:
    print(f"\n{'=' * 78}")
    print(f"QUALNAME: {code.co_qualname if hasattr(code, 'co_qualname') else prefix}")
    print(f"flags={code.co_flags} (varargs={bool(code.co_flags & 4)} varkw={bool(code.co_flags & 8)} "
          f"generator={bool(code.co_flags & 0x20)} async={bool(code.co_flags & 0x80)})")
    print(f"argcount={code.co_argcount} posonly={getattr(code, 'co_posonlyargcount', 0)} "
          f"kwonly={code.co_kwonlyargcount} firstline={code.co_firstlineno}")
    print(f"varnames : {list(code.co_varnames)}")
    if code.co_freevars:
        print(f"freevars : {list(code.co_freevars)}")
    if code.co_cellvars:
        print(f"cellvars : {list(code.co_cellvars)}")
    print(f"names    : {list(code.co_names)}")
    print("\nconsts (non-code):")
    for i, c in enumerate(code.co_consts):
        if isinstance(c, CodeType):
            print(f"  [{i}] <code {c.co_name} @line {c.co_firstlineno}>")
        else:
            print(f"  [{i}] {c!r}")
    try:
        ins = list(dis.get_instructions(code))
    except Exception as exc:
        print(f"dis failed: {exc}")
        return
    print(f"\ndis ({len(ins)} instructions):")
    for i in ins:
        arg = "" if i.arg is None else f" {i.argrepr!r}" if isinstance(i.argrepr, str) else f" {i.argrepr}"
        print(f"  L{i.offset:<6} {i.opname:<28}{arg}")


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    module = sys.argv[1]
    name = None
    show_all = "--all" in sys.argv
    for a in sys.argv[2:]:
        if not a.startswith("--"):
            name = a.lower()
    code = marshal.loads(find_pyc(module).read_bytes()[16:])
    units = list(code_iter(code))
    if name is None and not show_all:
        units = units[:1]
    elif show_all:
        pass
    else:
        units = [(p, c) for p, c in units if name in p.lower()]
        if not units:
            raise SystemExit(f"no code object matching {name!r}")
    for prefix, unit in units:
        describe(prefix, unit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
