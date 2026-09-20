"""Parsing and canonicalisation of Indian Standard (IS) number strings.

Real IS numbers appear in the wild in every shape imaginable, e.g.:
    "IS 10322-5-3"
    "IS 10322 Part 5 Section 3"
    "IS:10322(Pt5/Sec3)"
    "IS 456 : 2000"
    "IS 10322 (Part 5/Sec 3) : 2020"

Every IS number that enters any Part 3 / Part 5 service is passed through
``parse_is_number`` and re-serialised via ``ISNumber.canonical()`` before it is
used, compared, or stored. Nothing downstream should ever compare raw strings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Annotated

from pydantic import BeforeValidator

# Matches an "IS" / "I.S." prefix, an optional colon/hyphen separator (this is
# what "IS:10322" uses), then the base standard number.
_PREFIX_RE = re.compile(r"(?i)\bI\.?\s?S\.?\s*[:\-]?\s*(\d{2,6})\b")

# Within the text that follows the base number, a keyword-tagged part/section,
# or a bare number, may appear in any order and with varied punctuation.
_TOKEN_RE = re.compile(
    r"(?i)(PART|PT|SECTION|SEC)\s*[:.\-]?\s*(\d{1,3})\b|(\d{1,6})\b"
)

_YEAR_MIN, _YEAR_MAX = 1900, 2099


@dataclass(frozen=True)
class ISNumber:
    """A parsed, structured Indian Standard number."""

    base: int
    part: int | None = None
    section: int | None = None
    year: int | None = None

    def canonical(self) -> str:
        """The single canonical string form used everywhere downstream."""
        s = f"IS {self.base}"
        if self.part is not None:
            s += f"-{self.part}"
            if self.section is not None:
                s += f"-{self.section}"
        if self.year is not None:
            s += f":{self.year}"
        return s

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.canonical()


def parse_is_number(raw: str) -> ISNumber | None:
    """Parse a free-form IS number string into a structured ``ISNumber``.

    Returns ``None`` if ``raw`` does not contain a recognisable IS number
    (no "IS"/"I.S." prefix followed by digits). Never raises on malformed
    input — callers that need a hard failure should check for ``None``
    themselves, since "this string is not an IS number" is an expected,
    not exceptional, outcome (e.g. when scanning free-text LLM output for
    hallucinated references).
    """
    if not raw or not raw.strip():
        return None

    m = _PREFIX_RE.search(raw)
    if m is None:
        return None

    base = int(m.group(1))
    rest = raw[m.end():]

    part: int | None = None
    section: int | None = None
    year: int | None = None

    for tok in _TOKEN_RE.finditer(rest):
        keyword, keyword_num, bare_num = tok.group(1), tok.group(2), tok.group(3)
        if keyword is not None:
            num = int(keyword_num)
            if keyword.upper() in ("PART", "PT"):
                part = num
            else:  # SECTION, SEC
                section = num
            continue

        num_str = bare_num
        num = int(num_str)
        if len(num_str) == 4 and _YEAR_MIN <= num <= _YEAR_MAX and year is None:
            year = num
        elif part is None:
            part = num
        elif section is None:
            section = num
        # A fourth bare number with no more slots to fill is ignored rather
        # than raising — real-world input is messy and we prefer a partial,
        # honest parse over rejecting the whole string.

    return ISNumber(base=base, part=part, section=section, year=year)


def canonicalise_is_number(raw: str) -> str:
    """Parse and re-serialise in one step. Raises ``ValueError`` if unparseable.

    This is the function pydantic validators call at the contract boundary —
    there, an unparseable IS number is a hard error, not an expected outcome.
    """
    parsed = parse_is_number(raw)
    if parsed is None:
        raise ValueError(f"not a recognisable IS number: {raw!r}")
    return parsed.canonical()


def _canonicalise_optional(raw: str | None) -> str | None:
    return None if raw is None else canonicalise_is_number(raw)


# Reusable pydantic field types: every IS number crossing a contract boundary
# is canonicalised on the way in, so nothing downstream ever compares or
# stores raw, un-normalised strings.
ISNumberStr = Annotated[str, BeforeValidator(canonicalise_is_number)]
OptionalISNumberStr = Annotated[str | None, BeforeValidator(_canonicalise_optional)]
