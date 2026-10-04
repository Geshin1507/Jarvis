"""Recover a reconstruction spec from surviving .pyc files.

The .py sources for many backend modules were deleted by an external event.
The compiled bytecode survives. Bytecode does not contain source text, but it
does contain: module/class/function names, argument names, default values,
docstrings, every string literal, and the bytecode itself. That is enough to
faithfully reconstruct the modules.

Usage (from backend/):
    .venv/Scripts/python.exe ../.recovery/dump_spec.py
"""

from __future__ import annotations

import dis
import importlib.util
import marshal
import pathlib
import sys
from types import CodeType as code_type

ROOT = pathlib.Path(__file__).resolve().parent.parent / "backend"
APP = ROOT / "app"
COMPACT = "--compact" in sys.argv
OUT = pathlib.Path(__file__).resolve().parent / ("spec_compact" if COMPACT else "spec")
MAGIC = importlib.util.MAGIC_NUMBER
FUNC_CAP = 45 if COMPACT else 90
MODULE_CAP = 90 if COMPACT else 220


def load_code(pyc: pathlib.Path):
    data = pyc.read_bytes()
    if data[:4] != MAGIC:
        raise ValueError(f"magic mismatch in {pyc}")
    return marshal.loads(data[16:])


def const_summary(value) -> str | None:
    """Return a readable one-line summary for a constant, or None to skip."""
    if isinstance(value, str):
        return repr(value)
    if isinstance(value, (int, float, complex, bool, type(None))):
        return repr(value)
    if isinstance(value, (bytes, bytearray)):
        return repr(bytes(value))
    if isinstance(value, tuple):
        return "(" + ", ".join(repr(v) for v in value) + ")"
    if isinstance(value, frozenset):
        return "frozenset(" + ", ".join(sorted(repr(v) for v in value)) + ")"
    if isinstance(value, (list, set)):
        return repr(value)
    return None


def flag_names(code) -> list[str]:
    names = []
    if code.co_flags & 0x04:
        names.append("varargs")
    if code.co_flags & 0x08:
        names.append("varkw")
    if code.co_flags & 0x20:
        names.append("generator")
    if code.co_flags & 0x80:
        names.append("async")
    if code.co_flags & 0x200:
        names.append("async-generator")
    if code.co_flags & 0x400:
        names.append("comprehension")
    return names


def signature(code) -> str:
    varnames = list(code.co_varnames)
    nargs = code.co_argcount
    nkwonly = code.co_kwonlyargcount
    args = varnames[:nargs]
    kwonly = varnames[nargs : nargs + nkwonly]
    idx = nargs + nkwonly
    vararg = None
    varkw = None
    if code.co_flags & 0x04:
        vararg = varnames[idx] if idx < len(varnames) else "args"
        idx += 1
    if code.co_flags & 0x08:
        varkw = varnames[idx] if idx < len(varnames) else "kwargs"
        idx += 1
    posonly = getattr(code, "co_posonlyargcount", 0)
    parts: list[str] = []
    for i, a in enumerate(args):
        parts.append(a)
        if posonly and i == posonly - 1:
            parts.append("/")
    if vararg:
        parts.append("*" + vararg)
    elif kwonly:
        parts.append("*")
    parts.extend(kwonly)
    if varkw:
        parts.append("**" + varkw)
    return "(" + ", ".join(parts) + ")"


def walk(code, out: list[str], qualname: str, depth: int = 0) -> None:
    pad = "  " * depth
    kids = [c for c in code.co_consts if isinstance(c, code_type)]
    doc = code.co_consts[0] if code.co_consts and isinstance(code.co_consts[0], str) else None

    if code.co_name == "<module>":
        out.append("# module")
    elif code.co_name == "<lambda>":
        out.append(f"{pad}- lambda @ line {code.co_firstlineno}")
    elif code.co_name == "<listcomp>":
        out.append(f"{pad}- listcomp @ line {code.co_firstlineno}")
    elif code.co_name == "<dictcomp>":
        out.append(f"{pad}- dictcomp @ line {code.co_firstlineno}")
    elif code.co_name == "<setcomp>":
        out.append(f"{pad}- setcomp @ line {code.co_firstlineno}")
    elif code.co_name == "<genexpr>":
        out.append(f"{pad}- genexpr @ line {code.co_firstlineno}")
    else:
        fl = flag_names(code)
        kind = "class" if code.co_name[0].isupper() and qualname.endswith(code.co_name) and not fl else "def"
        marker = " ".join(fl)
        out.append(
            f"{pad}{kind} {code.co_name}{signature(code)}"
            + (f"  [{marker}]" if marker else "")
            + f"   @line {code.co_firstlineno}"
        )

    if doc:
        out.append(f"{pad}    \"\"\"{doc.strip()}\"\"\"")

    # locals and non-code constants
    consts = [c for c in code.co_consts if not isinstance(c, code_type)]
    if consts and code.co_name != "<module>":
        out.append(f"{pad}    consts: {[const_summary(c) for c in consts]}")
    elif consts:
        out.append(f"{pad}    consts: {[const_summary(c) for c in consts]}")

    if code.co_names:
        label = "names" if code.co_name == "<module>" else "refs"
        out.append(f"{pad}    {label}: {list(code.co_names)}")
    if code.co_varnames and code.co_name != "<module>" and depth > 0:
        out.append(f"{pad}    locals: {list(code.co_varnames)}")

    # disassembly for short, logic-bearing units
    if COMPACT and code.co_name == "__annotate__":
        return
    cap = MODULE_CAP if code.co_name == "<module>" else FUNC_CAP
    try:
        ins = list(dis.get_instructions(code))
    except Exception:  # pragma: no cover
        ins = []
    if 0 < len(ins) <= cap:
        out.append(f"{pad}    --- dis ---")
        for i in ins:
            arg = "" if i.arg is None else f" {i.argrepr}"
            out.append(f"{pad}    L{i.offset:<5} {i.opname}{arg}")
    elif ins:
        out.append(f"{pad}    --- dis skipped ({len(ins)} instructions) ---")

    for kid in kids:
        kid_qual = f"{qualname}.{kid.co_name}"
        walk(kid, out, kid_qual, depth + 1)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    targets = sorted(APP.rglob("*.pyc"))
    index = []
    for pyc in targets:
        rel = pyc.relative_to(APP)
        mod_name = pyc.name.split(".")[0]
        pkg_parts = [p for p in rel.parent.parts if p != "__pycache__"]
        mod = "/".join(pkg_parts + [mod_name])
        src = APP / (mod + ".py")
        missing = not src.exists()

        try:
            code = load_code(pyc)
        except Exception as exc:  # pragma: no cover
            print(f"FAIL {mod}: {exc}")
            continue

        lines: list[str] = []
        lines.append(f"# {mod}")
        lines.append(f"# source present on disk: {not missing}")
        lines.append("")
        walk(code, lines, mod)
        text = "\n".join(lines)

        outpath = OUT / (mod.replace("/", "__") + ".md")
        outpath.write_text(text, encoding="utf-8")
        index.append(
            {
                "module": mod,
                "missing": missing,
                "lines": len(lines),
                "bytes": len(text),
                "names": len(code.co_names),
            }
        )

    print(f"modules dumped: {len(index)}")
    print(f"missing source: {sum(1 for i in index if i['missing'])}")
    for row in index:
        flag = "MISSING" if row["missing"] else "present"
        print(f"{flag:8} {row['module']:45} spec_lines={row['lines']:5} bytes={row['bytes']:6}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
