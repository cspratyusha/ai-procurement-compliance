"""similar.similar_scope: related product standards, read from the dense index."""

import sys
from pathlib import Path

import faiss
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import similar  # noqa: E402
from data.models import Standard  # noqa: E402
from editions import Editions  # noqa: E402


def std(sid, number, title, status="active"):
    return Standard(id=sid, number=number, title=title, scope="", description="", category="",
                    version="", last_amended="", status=status)


def _unit(v):
    v = np.array(v, dtype=np.float32)
    return v / np.linalg.norm(v)


@pytest.fixture
def fake_index(monkeypatch):
    """A handful of standards with vectors chosen so the similarities are known."""
    corpus = [
        std("a", "IS 694:2010", "PVC insulated cables for working voltages up to 1100 V"),
        std("b", "IS 694:1990", "PVC insulated cables, older edition", "superseded"),       # own standard
        std("c", "IS 1554 (Part 1):1988", "PVC insulated heavy duty electric cables", "superseded"),
        std("d", "IS 1554 (Part 1):2020", "PVC insulated heavy duty electric cables"),
        std("e", "IS 6808:2023", "Domestic hand grinder - Specification"),                 # look-alike
        std("f", "IS 7098 (Part 1):1988", "Crosslinked polyethylene insulated cables"),
        std("g", "IS 9999:2000", "Aerial cables of no real relation"),                      # below the floor
    ]
    base = _unit([1, 0, 0, 0])
    vectors = [
        base,
        _unit([0.99, 0.1, 0, 0]),
        _unit([0.95, 0.3, 0, 0]),
        _unit([0.94, 0.33, 0, 0]),
        _unit([0.97, 0, 0.25, 0]),
        _unit([0.93, 0, 0, 0.37]),
        _unit([0.5, 0, 0, 0.86]),
    ]
    index = faiss.IndexFlatIP(4)
    index.add(np.stack(vectors))
    ids = [s.id for s in corpus]
    monkeypatch.setattr("indexing.embed_index.load_index", lambda *a, **k: (index, ids))
    return corpus


def test_neighbours_share_the_product_and_skip_look_alikes(fake_index):
    by_id = {s.id: s for s in fake_index}
    found = similar.similar_scope(fake_index[0], by_id, Editions(fake_index))
    numbers = [s.number for s, _ in found]
    # Other editions of IS 694 are the standard itself, not a relative.
    assert not any(n.startswith("IS 694") for n in numbers)
    # The hand grinder scores high but shares no word of the title.
    assert "IS 6808:2023" not in numbers
    # Below the floor, nothing is offered however the title reads.
    assert "IS 9999:2000" not in numbers
    assert numbers == ["IS 1554 (Part 1):2020", "IS 7098 (Part 1):1988"]


def test_a_superseded_neighbour_is_shown_as_its_current_edition(fake_index):
    by_id = {s.id: s for s in fake_index}
    found = similar.similar_scope(fake_index[0], by_id, Editions(fake_index))
    assert found[0][0].number == "IS 1554 (Part 1):2020"          # vector was the 1988 edition's


def test_standards_already_shown_are_not_repeated(fake_index):
    by_id = {s.id: s for s in fake_index}
    found = similar.similar_scope(fake_index[0], by_id, Editions(fake_index), exclude=["IS 1554 (Part 1):2020"])
    assert [s.number for s, _ in found] == ["IS 7098 (Part 1):1988"]


def test_title_words_drop_what_every_title_says():
    assert similar.title_words("Domestic Pressure Cooker - Specification") == {"pressure", "cooker"}
    assert similar.title_words("Protective helmets for motorcycle riders") == {"helmet", "motorcycle", "rider"}
