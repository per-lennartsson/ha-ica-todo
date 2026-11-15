"""Tests for the item history and the suggestions built from it."""

from custom_components.ica.categories import GroupMatch, name_key
from custom_components.ica.history import (
    build_suggestions,
    history_groups,
    most_used_group,
    prune,
    record_rows,
)

NOW = "2026-11-13T08:00:00Z"


def _row(uid, name, group=None):
    row = {"offlineId": uid, "productName": name}
    if group is not None:
        row["articleGroupId"] = group
    return row


def test_new_rows_are_counted_with_their_group():
    history = record_rows(
        None, [], [_row("a", "Toalettpapper", 9), _row("b", "Doftsak", 12)], NOW
    )
    assert history[name_key("Toalettpapper")] == {
        "name": "Toalettpapper",
        "count": 1,
        "last_used": NOW,
        "groups": {"9": 1},
        "last_group": 9,
    }
    # Rows without a category are counted, but not their group
    assert history["doftsak"]["count"] == 1
    assert history["doftsak"]["groups"] == {}


def test_rows_seen_before_are_not_counted_again():
    rows = [_row("a", "Mjölk", 10)]
    history = record_rows(None, [], rows, NOW)
    assert record_rows(history, rows, rows, NOW) is None


def test_the_same_name_in_new_rows_adds_up():
    history = record_rows(None, [], [_row("a", "Tomat", 4)], NOW)
    history = record_rows(history, [], [_row("b", "Tomater", 4)], NOW)
    assert history["tomat"]["count"] == 2
    assert history["tomat"]["groups"] == {"4": 2}
    # The name as it was typed last
    assert history["tomat"]["name"] == "Tomater"


def test_a_changed_category_moves_the_count():
    history = record_rows(None, [], [_row("a", "Toalettpapper", 9)], NOW)
    history = record_rows(
        history, [_row("a", "Toalettpapper", 9)], [_row("A", "Toalettpapper", 11)], NOW
    )
    assert history[name_key("Toalettpapper")]["groups"] == {"11": 1}
    assert history[name_key("Toalettpapper")]["count"] == 1


def test_a_row_that_gets_its_first_category_is_counted():
    history = record_rows(None, [], [_row("a", "Doftsak", 12)], NOW)
    history = record_rows(
        history, [_row("a", "Doftsak", 12)], [_row("a", "Doftsak", 11)], NOW
    )
    assert history["doftsak"]["groups"] == {"11": 1}


def test_record_rows_does_not_modify_the_input():
    history = record_rows(None, [], [_row("a", "Mjölk", 10)], NOW)
    before = {k: dict(v, groups=dict(v["groups"])) for k, v in history.items()}
    record_rows(history, [], [_row("b", "Mjölk", 6)], NOW)
    assert history == before


def test_most_used_group_and_ties():
    assert most_used_group({"groups": {"9": 1, "11": 3}}) == 11
    assert most_used_group({"groups": {"9": 2, "11": 2}, "last_group": 9}) == 9
    assert most_used_group({"groups": {"9": 2, "11": 2}}) == 9
    assert most_used_group({"groups": {}}) is None


def test_history_groups_leaves_out_names_without_a_group():
    history = {
        "toalettpapper": {"groups": {"11": 2}},
        "doftsak": {"groups": {}},
    }
    assert history_groups(history) == {"toalettpapper": 11}


def test_prune_keeps_the_most_used():
    history = {
        "a": {"count": 5, "last_used": "2026-01-01"},
        "b": {"count": 1, "last_used": "2026-11-01"},
        "c": {"count": 1, "last_used": "2026-02-01"},
    }
    assert list(prune(history, max_items=2)) == ["a", "b"]


def _group_for(name):
    return GroupMatch(10, None, "exact") if "mjölk" in name.casefold() else None


HISTORY = {
    "kaffe": {"name": "Kaffe", "count": 2, "groups": {"9": 2}},
    "toalettpapper": {"name": "Toalettpapper", "count": 7, "groups": {"11": 7}},
}
FAVORITES = [
    {"text": "Mjölk", "sortOrder": 1},
    {"text": "Kaffe", "sortOrder": 0},
]
ARTICLES = [
    {"name": "Tomat", "parentId": 4},
    {"name": "Havremjölk", "parentId": 10},
    {"name": "Toalettborste", "parentId": 9},
    {"name": None},
]


def test_suggestions_are_ordered_history_favorites_articles():
    items = build_suggestions(HISTORY, FAVORITES, ARTICLES, _group_for)
    assert [(i["name"], i["source"]) for i in items] == [
        ("Toalettpapper", "history"),
        ("Kaffe", "history"),
        ("Mjölk", "favorite"),
        ("Havremjölk", "article"),
        ("Toalettborste", "article"),
        ("Tomat", "article"),
    ]
    assert items[0]["count"] == 7
    assert "count" not in items[2]
    assert items[2]["group_id"] == 10
    assert items[4]["group_id"] == 12


def test_suggestions_for_a_query_start_with_names_beginning_with_it():
    items = build_suggestions(HISTORY, FAVORITES, ARTICLES, _group_for, query="MJÖ")
    assert [i["name"] for i in items] == ["Mjölk", "Havremjölk"]

    items = build_suggestions(HISTORY, FAVORITES, ARTICLES, _group_for, query="toa")
    assert [i["name"] for i in items] == ["Toalettpapper", "Toalettborste"]


def test_suggestions_limit():
    items = build_suggestions(HISTORY, FAVORITES, ARTICLES, _group_for, limit=2)
    assert len(items) == 2
