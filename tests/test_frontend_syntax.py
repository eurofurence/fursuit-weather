"""The frontend has to parse on the oldest browser we claim to support.

There is no build step here -- the .js files in static/ are served verbatim --
so a single `?.` anywhere in them is a SyntaxError on Chrome 72, the whole
script is discarded, and the page comes up as nothing but its loading skeleton.
Nothing else in the test suite would notice: the API would still be perfect.

esprima-python parses at roughly the ES2017/2018 level, which makes it a decent
stand-in for that browser. It is a dev dependency only; the container never
needs it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

esprima = pytest.importorskip("esprima", reason="pip install -r requirements-dev.txt")

STATIC = Path(__file__).resolve().parent.parent / "static"

#: Everything we ship ourselves. vendor/ is third-party and pinned; it is not
#: ours to rewrite, and Leaflet 1.9 is ES5 anyway.
OUR_SCRIPTS = sorted(p for p in STATIC.glob("*.js"))


def test_there_are_scripts_to_check():
    # Guards the glob itself: an empty list would make every test below pass.
    assert OUR_SCRIPTS, f"no scripts found in {STATIC}"


@pytest.mark.parametrize("path", OUR_SCRIPTS, ids=lambda p: p.name)
def test_script_parses_without_es2020_syntax(path: Path):
    """No optional chaining, nullish coalescing or logical assignment."""
    try:
        esprima.parseScript(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - esprima raises its own Error type
        pytest.fail(
            f"{path.name} does not parse as ES2018: {exc}\n"
            "Chrome 72 and other pre-2020 browsers would discard the whole file. "
            "Use dig()/orElse() from app.js instead of `?.` and `??`."
        )
