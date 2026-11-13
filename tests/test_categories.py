"""Tests for finding the article group (category) of an item."""

from custom_components.ica.categories import (
    build_article_index,
    group_names,
    match_article_group,
    name_key,
    recategorized_rows,
)

ARTICLES = [
    {"name": "Mjölk", "pluralName": None, "parentId": 10, "parentIdExtended": 101},
    {"name": "Tvål", "parentId": 7, "parentIdExtended": 70},
    {"name": "Tomat", "pluralName": "Tomater", "parentId": 4},
    {"name": "Ost", "parentId": 10},
    {"name": "Okänd", "parentId": 12},
    {"name": "Utan grupp"},
]
INDEX = build_article_index(ARTICLES)


def _group(name, choices=None):
    match = match_article_group(name, INDEX, choices)
    return (match.group_id, match.source) if match else None


def test_name_key_ignores_case_plural_numbers_and_spacing():
    assert name_key("  2 st TOMATER ") == "st tomat"
    assert name_key("Tomat") == name_key("tomater")
    assert name_key("") == ""
    assert name_key(None) == ""


def test_exact_name_and_plural_name():
    assert _group("mjölk") == (10, "exact")
    assert _group("Tomater") == (4, "exact")


def test_extended_group_comes_from_the_article():
    match = match_article_group("Mjölk", INDEX)
    assert match.extended_id == 101


def test_first_matching_word():
    assert _group("Tvål badrum") == (7, "word")
    assert _group("Badrum tvål") == (7, "word")


def test_compound_word_matches_its_ending():
    assert _group("Havremjölk") == (10, "compound")
    assert _group("Prästost") == (10, "compound")


def test_compound_needs_long_enough_parts():
    # "kost" ends with "ost", but "k" is too short to be a word of its own
    assert _group("Kost") is None


def test_unknown_items_and_unspecified_articles_do_not_match():
    assert _group("Doftsak toa") is None
    assert _group("Okänd") is None
    assert _group("Utan grupp") is None
    assert _group("") is None


def test_a_choice_wins_over_the_articles():
    choices = {name_key("Tvål badrum"): 11}
    assert _group("tvål  badrum", choices) == (11, "choice")
    # Other names are not affected
    assert _group("Tvål", choices) == (7, "exact")


def test_recategorized_rows_only_changes_open_unspecified_rows():
    rows = [
        {"offlineId": "a", "productName": "Mjölk", "articleGroupId": 12},
        {"offlineId": "b", "productName": "Tvål", "isStrikedOver": True},
        {"offlineId": "c", "productName": "Tomat", "articleGroupId": 9},
        {"offlineId": "d", "productName": "Doftsak toa", "articleGroupId": 12},
        {"offlineId": "e", "productName": "Havremjölk"},
    ]
    changed = recategorized_rows(rows, INDEX)

    assert [(r["offlineId"], r["articleGroupId"]) for r in changed] == [
        ("a", 10),
        ("e", 10),
    ]
    assert changed[0]["articleGroupIdExtended"] == 101
    # The input rows are not modified
    assert rows[0]["articleGroupId"] == 12


def test_recategorized_rows_skips_rows_tried_before():
    rows = [{"offlineId": "ABC", "productName": "Mjölk", "articleGroupId": 12}]
    assert recategorized_rows(rows, INDEX, skip=["abc"]) == []


def test_group_names():
    groups = [{"id": 10, "name": "Mejeri"}, {"id": 4}, {"name": "no id"}]
    assert group_names(groups) == {10: "Mejeri", 4: "4"}
