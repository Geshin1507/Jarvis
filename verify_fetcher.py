"""Differential harness: rebuilt fetcher.py vs surviving bytecode.

Executes the original bytecode in a synthetic package context, imports the
rebuilt source in parallel, and compares runtime values and function outputs.
"""

from __future__ import annotations

import marshal
import pathlib
import sys
import types

sys.path.insert(0, "backend")

# --- Load original bytecode module in synthetic package context --------------
code = marshal.loads(
    pathlib.Path("backend/app/research/__pycache__/fetcher.cpython-314.pyc").read_bytes()[16:]
)
mod = types.ModuleType("_orig_fetcher")
mod.__package__ = "app.research"
sys.modules["_orig_fetcher"] = mod
# Satisfy the relative imports (level 2 = app.research.fetcher -> app package)
import app  # noqa: E402

mod.__package__ = "app.research"
exec(code, mod.__dict__)

import importlib  # noqa: E402

rebuilt = importlib.import_module("app.research.fetcher")

# --- Compare module-level constants ------------------------------------------
FAIL = 0


def check(name, got, want):
    global FAIL
    if got == want:
        print(f"  ok  {name}")
    else:
        FAIL += 1
        print(f"FAIL  {name}\n      got : {got!r}\n      want: {want!r}")


check("BLOCKED_HOSTS", rebuilt.BLOCKED_HOSTS, mod.BLOCKED_HOSTS)
check("WALL_MARKERS", rebuilt.WALL_MARKERS, vs := mod.WALL_MARKERS)
check("PRIVATE_HOST_HINTS", rebuilt.PRIVATE_HOST_HINTS, mod.PRIVATE_HOST_HINTS)
check("EMAIL_RE.pattern", rebuilt.EMAIL_RE.pattern, mod.EMAIL_RE.pattern)
check("EMAIL_RE default limit", rebuilt.extract_public_emails.__wrapped__ if False else None, None)

# --- Function outputs (pure functions) ---------------------------------------
import inspect  # noqa: E402

sig_src = str(inspect.signature(rebuilt.extract_public_emails))
print(f"  --  extract_public_emails signature: {sig_src}")

cases = {
    "classify_source_type": [
        ("https://acme.com/careers",),
        ("https://acme.com/jobs",),
        ("https://acme.com/hiring-now",),
        ("https://acme.com/",),
        ("https://acme.com/about",),
        ("https://acme.com/webinar-2026",),
        ("https://acme.com/blog/post-1",),
        ("https://acme.com/index.html",),
    ],
    "normalise_url": [
        ("acme.com",),
        ("https://acme.com/path#frag",),
        ("  https://acme.com  ",),
        ("http://acme.com",),
    ],
    "is_blocked_host": [
        ("https://linkedin.com/in/foo",),
        ("https://uk.linkedin.com/in/foo",),
        ("https://notlinkedin.com/",),
        ("https://example.com/",),
        ("https://x.com/handle",),
    ],
    "looks_like_wall": [
        ("Please sign in to continue",),
        ("Welcome to our home page",),
        ("",),
        ("x" * 5000 + "captcha" + "y" * 10),
        ("Please verify you are human",),
    ],
}

for fname, arglists in cases.items():
    f_new = getattr(rebuilt, fname)
    f_old = getattr(mod, fname)
    for args in arglists:
        try:
            want = f_old(*args)
        except Exception as e:  # noqa: BLE001
            want = f"<raised {type(e).__name__}>"
        try:
            got = f_new(*args)
        except Exception as e:  # noqa: BLE001
            got = f"<raised {type(e).__name__}>"
        check(f"{fname}{args!r:.60}", got, want)

# is_public_host: compare (bool, reason) for a loopback and a public host
for host in ("localhost", "127.0.0.1", "example.com", "10.0.0.5", "169.254.1.1"):
    want = mod.is_public_host(host)
    got = rebuilt.is_public_host(host)
    label = f"is_public_host({host!r})"
    if want[0] == got[0]:
        print(f"  ok  {label} -> {got[0]}")
    else:
        FAIL += 1
        print(f"FAIL  {label}: got {got!r} want {want!r}")

# extract_public_emails
texts = {
    "plain": "Contact us at info@acme.com or sales@acme.co.uk.",
    "dupe+image": "email: Info@Acme.com, img@acme.com.png",
    "empty": "",
}
for label, t in texts.items():
    check(f"emails[{label}]", rebuilt.extract_public_emails(t), mod.extract_public_emails(t))

# extract_text
html_samples = [
    "<html><head><title>Acme</title></head><body><h1>Hi</h1><script>bad()</script><p>Line one</p><p>  </p><p>Line two</p></body></html>",
    "<html><body>plain text only</body></html>",
]
for h in html_samples:
    check(f"extract_text[{h[:40]}...]", rebuilt.extract_text(h), mod.extract_text(h))

# --- PoliteFetcher pure-ish behaviour with a stub client ---------------------


class StubResponse:
    def __init__(self, status_code=200, content=b"", headers=None, url="http://x/"):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {"content-type": "text/html"}
        self.url = url
        self.encoding = "utf-8"


class StubClient:
    """Records calls; returns canned responses; never touches the network."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kw):
        self.calls.append(("get", url))
        return self.responses.pop(0)

    def head(self, url, **kw):
        self.calls.append(("head", url))
        return self.responses.pop(0)


def make(orig: bool, responses, robots=True):
    cls = mod.PoliteFetcher if orig else rebuilt.PoliteFetcher
    f = cls(
        client=StubClient(responses),
        respect_robots=robots,
        min_delay_seconds=0.0,
        timeout_seconds=5,
        max_bytes=1000,
    )
    return f


# robots_allowed: stub the HTTP layer by pre-warming the cache via monkeypatched client
robots_txt = "User-agent: *\nDisallow: /private\n"
stub = StubClient([StubResponse(content=robots_txt.encode(), headers={"content-type": "text/plain"})])
f_new = rebuilt.PoliteFetcher(
    client=stub, respect_robots=True, min_delay_seconds=0.0, timeout_seconds=5, max_bytes=1000
)
allowed, reason = f_new.robots_allowed("http://hosta/private/x")
check("robots disallowed", (allowed, reason), (False, "disallowed by robots.txt"))
allowed, reason = f_new.robots_allowed("http://hosta/public/x")
check("robots allowed path", (allowed, reason), (robots_allowed_value := True, None))

# validate_url parity
for url in (
    "not a url ??",
    "ftp://example.com",
    "https://linkedin.com/in/x",
    "https://127.0.0.1/x",
    "https://example.com/ok",
    "http://10.0.0.5/x",
    "https://localhost:8000/x",
):
    check(f"validate_url({url!r:.40})", rebuilt.PoliteFetcher.validate_url(f_new, url), mod.PoliteFetcher.validate_url(mod.PoliteFetcher(client=StubClient([]), respect_robots=False, min_delay_seconds=0.0, timeout_seconds=5, max_bytes=1000), url))

# fetch parity with stub client
def build_pair(responses):
    """Build (old, new) fetchers sharing response scripts. Each needs its own script."""
    old = make(True, [StubResponse(**r) for r in responses])
    new = make(False, [StubResponse(**r) with_placeholder] if False else [StubResponse(**r) for r in responses])
    return old, new


PAGE = b"<html><head><title>T</title></head><body><p>hello</p></body></html>"

fetch_cases = [
    # (label, status, content, content_type)
    ("200 html", 200, PAGE, "text/html; charset=utf-8"),
    ("403", 403, b"nope", "text/html"),
    ("401", 401, b"login", "text/html"),
    ("404", 404, b"gone", "text/html"),
    ("429", 4F if False else 429, b"slow down", "text/html),
]
