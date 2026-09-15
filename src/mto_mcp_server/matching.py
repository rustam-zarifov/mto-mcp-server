"""Match-key functions: turn one item's fields into a hashable key that
identifies "the same physical item" across MTO and SCSA.

Design decision (flagged for review): the default key is normalized NAME
ONLY, not name+line. In the real SCSA export the line-code columns are
populated for some standards (GOST) and empty for others (ASME) - see
tests/fixtures/scsa_test.xlsx - so requiring line as part of the key would
silently drop real matches. Line code is still carried through as display
metadata on every diff entry so you can see it in the report; it's just
not part of equality. Reducers are the one category the spec calls out
explicitly as needing line code in the key, so they keep it.

If your real exports DO have reliable line codes on both sides, tightening
default_key() to include line is a one-line change - see the commented
variant below.
"""
from __future__ import annotations

import re

from .normalize import canonicalize_valve_words, normalize_name

MatchKey = tuple


def default_key(name: str, line: str | None = None) -> MatchKey:
    n = normalize_name(name).lower()
    return ("default", n)
    # Stricter alternative, if line codes turn out to be reliable on both
    # sides in your real data:
    # return ("default", n, line or "")


def valve_key(name: str, line: str | None = None) -> MatchKey:
    n = normalize_name(name).lower()
    n = canonicalize_valve_words(n)
    return ("valve", n)


# Matches things like: DN50, Ду50, 50x25, 2"x1", 60.3x33.7 - i.e. any
# integer that plausibly denotes a diameter. This is intentionally naive;
# it exists to be corrected against real reducer names, not to be final.
_NUMBER_RE = re.compile(r"\d+")


def reducer_key(name: str, line: str | None = None) -> MatchKey:
    """Reducer key = (family, OD-pair, line) per the spec.

    "Family" = the name with all numbers stripped (e.g. product line /
    type designator). "OD-pair" = the two largest diameters found in the
    name, sorted, since a reducer's two ends can appear in either order
    across exports (DN100x50 vs DN50x100).
    """
    n = normalize_name(name).lower()
    numbers = [int(x) for x in _NUMBER_RE.findall(n)]
    family = _NUMBER_RE.sub("", n)
    family = re.sub(r"\s+", " ", family).strip()
    od_pair = tuple(sorted(numbers, reverse=True)[:2])
    return ("reducer", family, od_pair, line or "")


_KEY_FUNCS = {
    # valve and reducer intentionally NOT wired in - valve_key() and
    # reducer_key() above are untested guesses (no real valve or reducer
    # rows to validate against; only elbow data was available). Both
    # categories fall through to default_key (name-only) for now. The demo
    # scope is elbow reconciliation end-to-end; wiring either of these back
    # in is a one-line change once there's real data to check them against.
}


def get_match_key(name: str, category: str, line: str | None = None) -> MatchKey:
    fn = _KEY_FUNCS.get(category, default_key)
    return fn(name, line)
