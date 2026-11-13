"""Find the article group (category) of a shopping list item.

Pure functions, so they can be tested without Home Assistant. The coordinator
feeds them ICA's article database and the choices the household made earlier.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from .const import DEFAULT_ARTICLE_GROUP_ID
from .utils import normalize_product_name

# A compound word ("havremjölk") matches on its ending ("mjölk") only when both
# parts are long enough, so "kost" does not match "ost".
MIN_COMPOUND_HEAD = 2
MIN_COMPOUND_TAIL = 3

_WORD_RE = re.compile(r"[^\W\d_]+")


@dataclass(frozen=True)
class GroupMatch:
    """The article group found for an item, and how it was found."""

    group_id: int
    extended_id: int | None
    source: str  # "choice", "exact", "word" or "compound"


@dataclass(frozen=True)
class _Group:
    group_id: int
    extended_id: int | None


def _stem(word: str) -> str:
    """Singular-like form of a word, the same for all its forms.

    `normalize_product_name` is applied until the word stops changing, since one
    pass is not stable: "bananer" -> "banan", but "banan" -> "bana".
    """
    for _ in range(5):
        stemmed = normalize_product_name(word)
        if stemmed == word:
            break
        word = stemmed
    return word


def _words(name: str | None) -> list[str]:
    """The words of a name, lower case and singular-like ("2 st Tomater" -> ["tomat"])."""
    return [_stem(w) for w in _WORD_RE.findall((name or "").casefold())]


def name_key(name: str | None) -> str:
    """Key used to compare item names: case, plural, numbers and spacing ignored."""
    return " ".join(_words(name))


def build_article_index(articles: Iterable[Mapping] | None) -> dict[str, _Group]:
    """Map the names of ICA's articles to their article group.

    Both `name` and `pluralName` are indexed. Articles without a group are skipped.
    """
    index: dict[str, _Group] = {}
    for article in articles or []:
        group_id = article.get("parentId")
        if not isinstance(group_id, int) or group_id == DEFAULT_ARTICLE_GROUP_ID:
            continue
        group = _Group(group_id, article.get("parentIdExtended"))
        for field in ("name", "pluralName"):
            if key := name_key(article.get(field)):
                index.setdefault(key, group)
    return index


def _compound_match(word: str, index: Mapping[str, _Group]) -> _Group | None:
    """The longest article name that `word` ends with ("havremjölk" -> "mjölk")."""
    for start in range(MIN_COMPOUND_HEAD, len(word) - MIN_COMPOUND_TAIL + 1):
        if group := index.get(word[start:]):
            return group
    return None


def match_article_group(
    product_name: str | None,
    index: Mapping[str, _Group],
    choices: Mapping[str, int] | None = None,
) -> GroupMatch | None:
    """Find the article group for an item name, or None when nothing matches.

    In order:
    1. a group the household chose earlier for the same name (`choices`),
    2. an ICA article with the same name,
    3. an ICA article named like one of the words, first word first
       ("Tvål badrum" -> "tvål"),
    4. an ICA article that a word ends with ("havremjölk" -> "mjölk").
    """
    key = name_key(product_name)
    if not key:
        return None

    if choices and (chosen := choices.get(key)) is not None:
        return GroupMatch(int(chosen), None, "choice")

    if group := index.get(key):
        return GroupMatch(group.group_id, group.extended_id, "exact")

    words = key.split()
    if len(words) > 1:
        for word in words:
            if group := index.get(word):
                return GroupMatch(group.group_id, group.extended_id, "word")

    for word in words:
        if group := _compound_match(word, index):
            return GroupMatch(group.group_id, group.extended_id, "compound")
    return None


def is_unspecified(group_id: object) -> bool:
    """Whether a row has no real article group yet."""
    return group_id in (None, "", 0, DEFAULT_ARTICLE_GROUP_ID)


def recategorized_rows(
    rows: Iterable[Mapping],
    index: Mapping[str, _Group],
    choices: Mapping[str, int] | None = None,
    skip: Iterable[str] = (),
) -> list[dict]:
    """Open rows without a real group that now match one, with the new group set.

    Rows whose `offlineId` is in `skip` (tried before) are left out, so a change
    ICA does not keep is not sent again on every update.
    """
    skipped = {str(x).casefold() for x in skip}
    changed: list[dict] = []
    for row in rows:
        if row.get("isStrikedOver") or not is_unspecified(row.get("articleGroupId")):
            continue
        if str(row.get("offlineId", "")).casefold() in skipped:
            continue
        match = match_article_group(row.get("productName"), index, choices)
        if match is None or is_unspecified(match.group_id):
            continue
        new_row = dict(row)
        new_row["articleGroupId"] = match.group_id
        if match.extended_id is not None:
            new_row["articleGroupIdExtended"] = match.extended_id
        changed.append(new_row)
    return changed


def group_names(groups: Iterable[Mapping] | None) -> dict[int, str]:
    """Article group id -> name."""
    return {
        g["id"]: g.get("name") or str(g["id"])
        for g in groups or []
        if isinstance(g.get("id"), int)
    }
