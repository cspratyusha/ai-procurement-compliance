"""Which titles the ranking holds back for a buyer naming goods, and when not."""

import main


def secondary(title):
    return bool(main._SECONDARY_TITLE.search(title))


def asks_for_it(query):
    return bool(main._SECONDARY_QUERY.search(query))


def test_guides_dimensions_management_systems_and_glossaries_are_secondary():
    assert secondary("Guide for manufacture of hand-made common burnt-clay building bricks")
    assert secondary("Dimensions for special shapes of clay bricks")
    assert secondary("Drinking Water Supply Management System - Requirements for Piped Drinking Water Supply")
    assert secondary("Glossary of terms relating to paints")


def test_specifications_and_codes_of_practice_are_not():
    assert not secondary("Common Burnt Clay Building Bricks - Specification")
    assert not secondary("Drinking water - Specification")
    assert not secondary("Code of practice for earthing")          # for works, the code is the answer
    assert not secondary("Plain and Reinforced Concrete - Code of Practice")


def test_a_query_that_asks_for_one_is_not_held_back():
    assert asks_for_it("dimensions of special shaped clay bricks")
    assert asks_for_it("terminology of textiles")
    assert asks_for_it("quality management system for water utilities")
    assert not asks_for_it("drinking water quality requirements")
    assert not asks_for_it("long term water storage tank")         # "term" is not "terms"
