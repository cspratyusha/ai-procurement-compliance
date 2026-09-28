"""data/apply_bis_status.py: titles and replacements taken from BIS's record for each edition."""

import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO / "data"))

from apply_bis_status import (  # noqa: E402
    clean_bis_title, current_editions, newer_current_edition, repair_title, title_damage,
)
from text_repair import fix_text  # noqa: E402

_CORPUS = _REPO / "data" / "standards_corpus_full.json"


class TestTitles:
    def test_the_three_kinds_of_broken_title(self):
        assert title_damage("gov.in.is.16242.1.2014") == "archive_id"
        assert title_damage("2019: Laying of Paver Blocks \u2014 Code of Practice") == "year_prefix"
        assert title_damage("Part 1 : 2014: Automotive Vehicles - Wheel Rims") == "year_prefix"
        assert title_damage("metal chairs for office purposes") == "lower_case"
        assert title_damage("Portland Slag Cement - Specification") is None

    def test_bis_notes_are_not_part_of_the_title(self):
        assert clean_bis_title("Bonded Abrasive Grinding Wheels - Part 2 : Dimensions (Withdrawn)") == \
            "Bonded Abrasive Grinding Wheels - Part 2 : Dimensions"
        assert clean_bis_title("Paving Bitumen - Specification ( Third Revision )") == "Paving Bitumen - Specification"
        assert clean_bis_title("Cement (First Revision of IS 269)") == "Cement"
        # A parenthesis that is part of the name stays.
        assert clean_bis_title("Uninterruptible power systems (UPS): Part 1") == "Uninterruptible power systems (UPS): Part 1"

    def test_bis_title_replaces_a_broken_one(self):
        assert repair_title("gov.in.is.16242.1.2014", "Uninterruptible power systems (UPS)", None) == \
            ("Uninterruptible power systems (UPS)", "bis")
        assert repair_title("2019: Laying of Paver Blocks \u2014 Code of Practice", "Laying of paver blocks - Code of practice",
                            None) == ("Laying of paver blocks - Code of practice", "bis")

    def test_an_all_capitals_bis_title_is_used_only_when_nothing_better_exists(self):
        assert repair_title("2021: Utilization of Fly Ash Guidelines", "UTILIZATION OF FLY ASH GUIDELINES", None) == \
            ("Utilization of Fly Ash Guidelines", "archive_mended")
        assert repair_title("gov.in.is.1.1990", "SOME TITLE", None) == ("SOME TITLE", "bis")

    def test_an_id_with_no_record_takes_another_editions_title(self):
        assert repair_title("gov.in.is.10500.1984", "", "Drinking water - Specification") == \
            ("Drinking water - Specification", "bis_other_edition")
        assert repair_title("gov.in.is.1.1990", "", None) == (None, None)

    def test_a_good_title_is_left_alone(self):
        assert repair_title("Portland Slag Cement - Specification", "PORTLAND SLAG CEMENT", None) == (None, None)


class TestTextRepair:
    """BIS stores some text double-encoded: UTF-8 read back as Windows-1252."""

    def test_double_encoding_decodes_back_exactly(self):
        assert fix_text("Earth-Moving Machinery â€“ Safety") == "Earth-Moving Machinery – Safety"

    def test_text_encoded_twice_over_is_decoded_fully(self):
        assert fix_text("Boots for Miners Ã¢â‚¬” Specification") == \
            "Boots for Miners \u2014 Specification"

    def test_a_character_lost_before_publication_becomes_a_dash(self):
        assert fix_text("SILVER ALLOYS ï¿½ FINENESS") == "SILVER ALLOYS - FINENESS"

    def test_clean_text_is_untouched(self):
        for text in ("Plain and reinforced concrete", "IS 1554 (Part 1) \u2014 cables", "", None):
            assert fix_text(text) == text

    def test_bis_titles_are_repaired_when_cleaned(self):
        assert clean_bis_title("Earth-Moving Machinery â€“ Safety (Withdrawn)") == \
            "Earth-Moving Machinery – Safety"


class TestNewerEdition:
    BIS = {
        "IS 4246:2002": {"withdrawn": True},
        "IS 4246:2025": {"withdrawn": False},
        "IS 5405:1980": {"withdrawn": True},
        "IS 5405:2019": {"withdrawn": True},
        "IS 5405:2025": {"withdrawn": False},
        "IS 101 (PART 1/SEC 2):2023": {"withdrawn": False},
        "IS 2062:2011": {"withdrawn": True},
    }

    def test_bis_listing_a_newer_current_edition_names_it(self):
        current = current_editions(self.BIS)
        assert newer_current_edition("IS 4246:2002", current) == "IS 4246:2025"
        assert newer_current_edition("IS 5405:1980", current) == "IS 5405:2025"
        # Corpus spelling, whatever case BIS's key uses.
        assert newer_current_edition("IS 101 (Part 1/Sec 2):1987", current) == "IS 101 (Part 1/Sec 2):2023"

    def test_no_newer_current_edition_names_nothing(self):
        current = current_editions(self.BIS)
        assert newer_current_edition("IS 2062:2011", current) is None
        assert newer_current_edition("IS 4246:2025", current) is None      # it is the current one


@pytest.mark.skipif(not _CORPUS.exists(), reason="full corpus not present")
class TestServedCorpus:
    @pytest.fixture(scope="class")
    def corpus(self):
        return {s["number"]: s for s in json.loads(_CORPUS.read_text(encoding="utf-8"))}

    def test_no_broken_title_is_served_where_bis_has_one(self, corpus):
        broken = [n for n, s in corpus.items() if title_damage(s["title"]) is not None]
        assert len(broken) < 40, broken[:10]
        garbled = [n for n, s in corpus.items() if fix_text(s["title"]) != s["title"]]
        assert garbled == []
        assert corpus["IS 16242 (Part 1):2014"]["title"].startswith("Uninterruptible power systems")
        assert corpus["IS 16242 (Part 1):2014"]["archive_title"] == "gov.in.is.16242.1.2014"

    def test_a_withdrawal_names_the_newer_edition_bis_lists(self, corpus):
        record = corpus["IS 4246:2002"]
        assert (record["superseded_by_number"], record.get("replacement_source")) == \
            ("IS 4246:2025", "bis_newer_edition")
        # BIS named IS 14543:2024 itself, so it is not marked as inferred.
        assert corpus["IS 14543:2016"]["superseded_by_number"] == "IS 14543:2024"
        assert "replacement_source" not in corpus["IS 14543:2016"]
