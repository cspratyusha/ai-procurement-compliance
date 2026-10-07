"""Everyday product words: expansion to the standards' terms, and BIS product names."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import certification  # noqa: E402
import expansion  # noqa: E402


def test_everyday_words_get_the_standards_terms():
    for query, phrase in [
        ("laptop for office use", "information technology equipment safety"),
        ("water geyser 25 litre", "storage type electric water heaters"),
        ("solar panel 330 W", "crystalline silicon terrestrial photovoltaic modules"),
        ("plastic water tank 1000 litre", "rotational moulded polyethylene water storage tanks"),
        ("cotton bedsheet", "bed sheets"),
        ("fly ash bricks", "pulverized fuel ash-lime bricks"),
        ("PE pipes for drinking water", "polyethylene pipes for water supply"),
        ("house wiring cable", "polyvinyl chloride insulated cables with rigid and flexible conductor for building wiring"),
        ("cables for wiring inside a house", "polyvinyl chloride insulated cables with rigid and flexible conductor for building wiring"),
    ]:
        expanded, added = expansion.expand(query)
        assert added == [phrase], query
        assert expanded.startswith(query)           # the user's words stay first


def test_ambiguous_and_technical_queries_are_left_alone():
    for query in ("paracetamol tablets", "AC contactor 32 A", "PVC insulated copper cable",
                  "information technology equipment safety",
                  "PE pipes for gas supply",
                  "modular switches 6 A for domestic wiring"):  # switches, not cable                # PE for gas has a standard of its own
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


def test_tender_shorthand_reaches_the_held_standard():
    for query, phrase in [
        ("M25 grade concrete for RCC work", "plain and reinforced concrete"),      # IS 456
        ("RCC hume pipes NP3 class 600 mm dia", "precast concrete pipes"),        # IS 458
        ("AAC blocks 600x200x150", "autoclaved cellular aerated concrete blocks"),   # IS 2185 (Part 3)
        ("RMC for slab casting", "ready-mixed concrete"),                         # IS 4926
        ("ISMB 300 and ISMC 150 sections", "hot rolled steel beam column channel and angle sections"),  # IS 808
        ("AB cable 3x95+1x70 sq mm", "aerial bunched cables"),                    # IS 14255
        ("PPR pipes 25 mm", "polypropylene random copolymer pipes"),              # IS 15801
        ("VRLA battery 12V 100Ah", "stationary regulated lead acid batteries"),    # IS 15549
        ("UPS 10 kVA online", "uninterruptible power systems"),                   # IS 16242 (Part 1)
        ("RCBO 32 A", "residual current operated circuit-breakers with integral overcurrent protection"),
        ("RMU 11 kV 3 way", "high-voltage switchgear and controlgear AC metal-enclosed"),  # IS/IEC 62271-200
    ]:
        assert phrase in expansion.expand(query)[1], query


def test_shorthand_with_another_meaning_is_left_alone():
    # M20 is also a bolt thread; a concrete grade needs a concrete word beside it.
    for query in ("M20 bolts and nuts", "M25 steel rod", "UPS battery 12V"):
        assert not any(p in ("plain and reinforced concrete", "uninterruptible power systems")
                       for p in expansion.expand(query)[1]), query
    # The fuller concrete phrase wins over RCC's shorter one.
    assert expansion.expand("M25 grade concrete for RCC work")[1] == ["plain and reinforced concrete"]


def test_short_forms_written_with_full_stops_are_read_too():
    """Schedules of rates write 'G.I. pipe', 'D.I. fitting', 'R.C.C. pipes'."""
    for query, phrase in [
        ("Providing ISI mark G.I. pipe of following class and dia", "galvanized steel tubes tubulars and other wrought steel fittings"),
        ("Providing and supplying D.I. fitting with socket push-on joints", "ductile iron fittings for pressure pipes"),
        ("Providing ISI standard R.C.C. pipes in standard lengths", "precast concrete pipes"),
    ]:
        assert phrase in expansion.expand(query)[1], query


def test_rate_boilerplate_is_not_searched():
    """'Rates including transportation, loading, unloading' says nothing about the goods."""
    text, _ = expansion.expand(
        "Providing and supplying HDPE pipes PE 100 PN 10. Rates including transportation, internal "
        "testing, loading, unloading and stacking, excluding GST levied by GOI")
    assert "transportation" not in text and "GST" not in text
    assert text.startswith("Providing and supplying HDPE pipes PE 100 PN 10")
    # A line that is all boilerplate is searched as typed rather than emptied.
    assert expansion.search_text("excluding GST") == "excluding GST"


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


def _notes(query):
    """Every product note the engine would show: the query, then each added phrase."""
    numbers = []
    for text in [query, *expansion.expand(query)[1]]:
        numbers += [p["is_number"] for p in certification.products_for_query(text) if p["is_number"] not in numbers]
    return numbers


def test_tender_phrasing_is_not_the_product():
    """'Supply of ... cable' is a cable, not BIS's 'Power Supplies' (IS/IEC 62368-1)."""
    notes = _notes("Supply of 3 core 2.5 sq mm PVC insulated flexible copper cable 1100 V grade")
    assert notes and notes[0].startswith("IS 694")
    assert not any(n.startswith("IS/IEC 62368") for n in notes)
    assert _notes("Supply, installation, testing and commissioning of LED street light luminaire 90 W")[0] \
        .startswith("IS 10322")
    assert _notes("SITC of 11 kV distribution transformer")[0].startswith("IS 1180")
    # A product named with one of those verbs is still a product, not a verb.
    assert _notes("universal testing machine") == []


def test_what_is_said_about_a_product_is_not_the_product():
    """'...quality requirements' once matched a wheel-rim listing that shortens to 'Requirements'."""
    assert not any(n.startswith("IS 16192") for n in _notes("drinking water quality requirements"))


def test_a_different_kind_of_the_same_product_gets_no_note():
    # A solar water heater is not an electric one.
    assert "storage type electric water heaters" not in expansion.expand("solar water heater")[1]
    assert not any(n.startswith(("IS 2082", "IS 368", "IS 302")) for n in _notes("solar water heater"))
    assert _notes("geyser for bathroom")                       # the electric one still gets its note
    # An air circuit breaker is not a residual current one.
    assert not any(n.startswith(("IS 12640", "IS 8828")) for n in _notes("air circuit breaker 800 A 4 pole"))
    assert _notes("residual current circuit breaker")[0].startswith("IS 12640")


def test_office_furniture_names_the_furniture_order_standards():
    """Furniture (Quality Control) Order, 2025: IS 17631 to IS 17636."""
    for query, phrase, number in [
        ("office chair", "work chairs", "IS 17631"),
        ("plastic chairs for canteen", "general purpose chairs and stools", "IS 17632"),
        ("computer table", "tables and desks", "IS 17633"),
        ("steel almirah", "storage units", "IS 17634"),
    ]:
        added = expansion.expand(query)[1]
        assert phrase in added, query
        assert _notes(query)[0].startswith(number), query
    # "Computer table" is furniture, not information technology equipment.
    assert "information technology equipment" not in expansion.expand("computer table")[1]
