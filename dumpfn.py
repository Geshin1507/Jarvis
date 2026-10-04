"""Dump full disassembly for named functions of a recovered module.

Usage: python dumpfn.py <module.dotted> <pyc-path> <fn> [fn ...]
"""

from __future__ import annotations

import dis
import io
import marshal
import pathlib
import sys
import types

dotted, pyc = sys.argv[1], sys.argv[2]
wanted = sys.argv[3:]

module_name = dotted.split(".")[-1]
package = ".".join(dotted.split(".")[:-1])
sys.path.insert(0, ".")

code = marshal.loads(pathlib.Path(pyc).read_bytes()[16:])
mod = types.ModuleType("_orig_" + module_name)
mod.__package__ = package
sys.modules[mod.__name__] = mod
exec(code, mod.__dict__)


def find_code(mod, name):
    """Locate the code object for `name`, searching nested classes."""
    for const in mod.__dict__.get("__loader__", None) and [] or []:
        pass
    out = []
    stack = [code]
    while stack:
        c = stack.pop()
        for const in c.co_consts:
            if isinstance(const, types.CodeType):
                if const.co_name == name:
                    out.append(const)
                stack.append(const)
    return out


def dump(c: types.CodeType) -> None:
    print(f"\n===== {c.co_qualname}  args={c.co_varnames[: c.co_argcount]}  free={c.co_freevars} =====")
    print("consts:", [repr(x)[:90] for x in c.co_consts if not isinstance(x, types.CodeType)])
    buf = io.StringIO()
    dis.dis(c, file=buf, depth=0)
    text = buf.getvalue()
    for line in text.splitlines():
        if "LOAD_COMMON_CONSTANT" in line or "CACHE" in line:
            continue
        print(line.rstrip())


for name in wanted:
    found = find_code(mod, name)
    if not found:
        print(f"!! no code object named {name}")
    for c in found:
        dump(c)
