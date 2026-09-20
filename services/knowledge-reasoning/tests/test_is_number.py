import pytest

from contracts.is_number import ISNumber, canonicalise_is_number, parse_is_number


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("IS 10322-5-3", ISNumber(base=10322, part=5, section=3)),
        ("IS 10322 Part 5 Section 3", ISNumber(base=10322, part=5, section=3)),
        ("IS:10322(Pt5/Sec3)", ISNumber(base=10322, part=5, section=3)),
        ("IS 456", ISNumber(base=456)),
        ("IS 456:2000", ISNumber(base=456, year=2000)),
        ("IS 456 : 2000", ISNumber(base=456, year=2000)),
        ("IS:456", ISNumber(base=456)),
        ("is 456", ISNumber(base=456)),
        ("I.S. 456", ISNumber(base=456)),
        ("IS456", ISNumber(base=456)),
        ("IS 1200-9", ISNumber(base=1200, part=9)),
        ("IS 1200 Pt 9", ISNumber(base=1200, part=9)),
        (
            "IS 10322 (Part 5/Sec 3) : 2020",
            ISNumber(base=10322, part=5, section=3, year=2020),
        ),
        (
            "as per IS 10322-5-3, the luminaire shall...",
            ISNumber(base=10322, part=5, section=3),
        ),
        ("IS  10322   Section 3", ISNumber(base=10322, section=3)),
    ],
)
def test_parse_variants(raw: str, expected: ISNumber) -> None:
    assert parse_is_number(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["", "   ", "not a standard", "ISO 9001", "BS 456", "just some text 10322"],
)
def test_parse_returns_none_for_non_is_numbers(raw: str) -> None:
    assert parse_is_number(raw) is None


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("IS 10322-5-3", "IS 10322-5-3"),
        ("IS 10322 Part 5 Section 3", "IS 10322-5-3"),
        ("IS:10322(Pt5/Sec3)", "IS 10322-5-3"),
        ("IS 456:2000", "IS 456:2000"),
        ("IS 456", "IS 456"),
        ("IS 10322 (Part 5/Sec 3) : 2020", "IS 10322-5-3:2020"),
    ],
)
def test_canonical_form(raw: str, expected: str) -> None:
    assert canonicalise_is_number(raw) == expected


def test_canonical_is_idempotent() -> None:
    # Re-parsing an already-canonical string must reproduce itself exactly.
    for raw in ["IS 10322-5-3:2020", "IS 456:2000", "IS 456", "IS 1200-9"]:
        assert canonicalise_is_number(raw) == raw


def test_canonicalise_raises_on_unparseable() -> None:
    with pytest.raises(ValueError):
        canonicalise_is_number("not a standard number")


def test_distinguishes_part_dash_from_year_colon() -> None:
    # Hyphen-separated trailing numbers are part/section; a colon-prefixed
    # 4-digit trailing number is a year. These must not be confused.
    assert parse_is_number("IS 1200-9") == ISNumber(base=1200, part=9)
    assert parse_is_number("IS 456:2000") == ISNumber(base=456, year=2000)


def test_extra_bare_numbers_beyond_part_and_section_are_ignored() -> None:
    # A fourth non-4-digit number has no slot left; parse degrades gracefully
    # rather than raising or silently overwriting part/section.
    result = parse_is_number("IS 10322-5-3-9")
    assert result is not None
    assert result.base == 10322
    assert result.part == 5
    assert result.section == 3
