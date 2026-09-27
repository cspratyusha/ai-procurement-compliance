"""Everyday product words: expansion to the standards' terms, and BIS product names."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import certification  # noqa: E402
import expansion  # noqa: E402


def test_everyday_words_get_the_standards_terms():
    for query, phrase in [
        ("laptop for office use", "information technology equipment"),
        ("water geyser 25 litre", "storage type electric water heaters"),
        ("solar panel 330 W", "crystalline silicon terrestrial photovoltaic modules"),
        ("plastic water tank 1000 litre", "rotational moulded polyethylene water storage tanks"),
    ]:
        expanded, added = expansion.expand(query)
        assert added == [phrase], query
        assert expanded.startswith(query)           # the user's words stay first


def test_ambiguous_and_technical_queries_are_left_alone():
    for query in ("paracetamol tablets", "AC contactor 32 A", "PVC insulated copper cable",
                  "information technology equipment safety"):
        assert expansion.expand(query)[1] == [], query


def test_tender_abbreviations_are_expanded():
    for query, phrase in [
        ("OPC 43 grade cement", "ordinary portland cement"),
        ("TMT bars Fe 500D 12 mm", "high strength deformed steel bars"),
        ("GI pipe 25 mm medium class", "galvanized steel tubes tubulars and other wrought steel fittings"),
        ("XLPE cable 3 core 11 kV", "cross-linked polyethylene"),
        ("DI pipes K9 for water supply", "ductile iron pipes"),
        ("MCB 32 A double pole", "circuit-breakers for overcurrent protection"),
    ]:
        assert phrase in expansion.expand(query)[1], query


def test_the_specific_abbreviation_wins_over_the_general_one():
    """'MS pipe' is mild steel tubes (IS 1239); the bare 'MS' entry must not add a second phrase."""
    assert expansion.expand("MS pipe for handrail")[1] == ["mild steel tubes tubulars and other wrought steel fittings"]


def test_sizes_and_grades_are_not_the_product():
    """'...25 mm medium class' must not match 'watt-hour meters, class 0.5'."""
    numbers = [p["is_number"] for p in certification.products_for_query("GI pipe 25 mm medium class")]
    assert not any(n.startswith(("IS 13010", "IS 13779")) for n in numbers)
    # The engine also checks the expanded wording ("OPC" -> "ordinary portland cement").
    assert certification.products_for_query("ordinary portland cement 43 grade")[0]["is_number"].startswith("IS 269")


def test_abbreviation_letters_elsewhere_are_ignored():
    for query in ("SRC wall", "the class of the DI student", "ms office licence", "cis women", "rcc"):
        assert expansion.expand(query)[1] == [], query


def test_bis_product_names_answer_everyday_queries():
    names = {p["product"] for p in certification.products_for_query("laptop for office use")}
    assert any("Laptop" in n for n in names)
    assert certification.products_for_query("power bank")[0]["scheme"] == "CRS"
    assert certification.products_for_query("helmet for bike")[0]["is_number"].startswith("IS 4151")


def test_the_thing_bought_is_the_head_noun():
    """A copper cable is a cable: it must not match refined copper."""
    numbers = [p["is_number"] for p in certification.products_for_query("PVC insulated copper cable")]
    assert numbers and numbers[0].startswith("IS 694")
    assert not any(n.startswith("IS 191") for n in numbers)


def test_words_with_another_meaning_match_nothing():
    for query in ("paracetamol tablets", "notebook for students", "steel"):
        assert certification.products_for_query(query) == [], query


def test_a_bare_product_word_lists_the_kinds():
    numbers = {p["is_number"] for p in certification.products_for_query("cement")}
    assert any(n.startswith("IS 269") for n in numbers)
