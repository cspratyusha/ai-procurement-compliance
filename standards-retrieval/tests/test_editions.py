"""editions.Editions.replacement: what to cite instead of a superseded edition."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.models import Standard  # noqa: E402
from editions import Editions  # noqa: E402


def std(number, status="active", superseded_by=None, withdrawn=False, note=None):
    return Standard(id=number, number=number, title=number, scope="", description="", category="",
                    version="", last_amended="", status=status, superseded_by_number=superseded_by,
                    withdrawn=withdrawn, withdrawal_note=note)


def test_the_active_edition_held_in_the_corpus():
    old, new = std("IS 1554 (Part 1):1988", "superseded"), std("IS 1554 (Part 1):2020")
    found = Editions([old, new]).replacement(old)
    assert (found["number"], found["held"]) == ("IS 1554 (Part 1):2020", True)


def test_a_replacement_named_by_bis_that_the_corpus_does_not_hold():
    old = std("IS 10258:2002", "superseded", superseded_by="IS 10258:2023", withdrawn=True)
    found = Editions([old]).replacement(old)
    assert (found["number"], found["held"], found["record"]) == ("IS 10258:2023", False, None)


def test_the_chain_is_followed_to_the_edition_in_force():
    """1982 -> 2002 (held, itself withdrawn) -> 2023 (not held)."""
    a = std("IS 10258:1982", "superseded", superseded_by="IS 10258:2002")
    b = std("IS 10258:2002", "superseded", superseded_by="IS 10258:2023", withdrawn=True)
    found = Editions([a, b]).replacement(a)
    assert found["number"] == "IS 10258:2023"
    assert found["held"] is False


def test_bis_replacement_wins_over_an_older_sibling_marked_active():
    old = std("IS 3400 (Part 5):2020", "superseded", superseded_by="IS 3400 (Part 5):2022", withdrawn=True)
    new = std("IS 3400 (Part 5):2022")
    found = Editions([old, new]).replacement(old)
    assert (found["number"], found["held"]) == ("IS 3400 (Part 5):2022", True)


def test_a_replacement_named_without_a_year_is_its_edition_in_force():
    """BIS names IS 15683 for IS 13849:1993; the corpus holds IS 15683:2006 and :2018."""
    old = std("IS 13849:1993", "superseded", superseded_by="IS 15683", withdrawn=True)
    mid = std("IS 15683:2006", "superseded", superseded_by="IS 15683:2018", withdrawn=True)
    new = std("IS 15683:2018")
    found = Editions([old, mid, new]).replacement(old)
    assert (found["number"], found["held"]) == ("IS 15683:2018", True)


def test_withdrawn_with_no_replacement_says_so():
    old = std("IS 10080:1982", "superseded", withdrawn=True, note="Decided by council")
    found = Editions([old]).replacement(old)
    assert found["number"] is None
    assert found["withdrawn_without_replacement"] is True
    assert found["note"] == "Decided by council"


def test_a_cycle_in_the_data_does_not_loop():
    a = std("IS 1:1990", "superseded", superseded_by="IS 1:2000")
    b = std("IS 1:2000", "superseded", superseded_by="IS 1:1990")
    found = Editions([a, b]).replacement(a)
    assert found["number"] in ("IS 1:2000", "IS 1:1990")
