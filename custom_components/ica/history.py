"""The items a household has added before, and suggestions built from them.

Pure functions, so they can be tested without Home Assistant. The history is a
JSON-friendly dict keyed by `name_key`:

    {"toalettpapper": {"name": "Toalettpapper", "count": 7,
                       "last_used": "2026-11-13T08:00:00Z",
                       "groups": {"11": 6, "9": 1}, "last_group": 11}}

`count` is how often an item with that name was added to a list. `groups` counts
the category each of those rows ended up in (rows without a category are not
counted), so the most used one can be given to the next row with that name.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any

from .categories import GroupMatch, is_unspecified, name_key
from .const import DEFAULT_ARTICLE_GROUP_ID

# Names kept in the history; the least used ones are dropped first
MAX_HISTORY_ITEMS = 2000


def _rows_by_id(rows: Iterable[Mapping] | None) -> dict[str, Mapping]:
    return {
        str(r.get("offlineId", "")).casefold(): r
        for r in rows or []
        if r.get("offlineId")
    }


def _group(row: Mapping) -> int | None:
    group_id = row.get("articleGroupId")
    if is_unspecified(group_id) or not isinstance(group_id, int):
        return None
    return group_id


def _count_group(entry: dict, group_id: int | None, step: int) -> None:
    if group_id is None:
        return
    groups = entry.setdefault("groups", {})
    key = str(group_id)
    value = groups.get(key, 0) + step
    if value > 0:
        groups[key] = value
    else:
        groups.pop(key, None)
    if step > 0:
        entry["last_group"] = group_id


def record_rows(
    history: Mapping[str, Any] | None,
    old_rows: Iterable[Mapping] | None,
    new_rows: Iterable[Mapping] | None,
    now: str,
) -> dict[str, Any] | None:
    """The history with the changes between two versions of a list's rows.

    - A row that is new counts as one more use of its name.
    - A row whose category changed moves its count to the new category.

    Returns None when nothing changed, so the caller does not have to save.
    The input is not modified.
    """
    old = _rows_by_id(old_rows)
    result = dict(history or {})
    changed = False

    def entry_for(key: str) -> dict:
        # Copy an entry before its first change in this call
        entry = result.get(key)
        if entry is None or entry is (history or {}).get(key):
            entry = {**(entry or {}), "groups": dict((entry or {}).get("groups", {}))}
            result[key] = entry
        return entry

    for uid, row in _rows_by_id(new_rows).items():
        key = name_key(row.get("productName"))
        if not key:
            continue
        previous = old.get(uid)
        if previous is None:
            entry = entry_for(key)
            entry["name"] = str(row.get("productName")).strip()
            entry["count"] = int(entry.get("count", 0)) + 1
            entry["last_used"] = now
            _count_group(entry, _group(row), 1)
            changed = True
            continue
        old_group, new_group = _group(previous), _group(row)
        if old_group == new_group:
            continue
        entry = entry_for(key)
        entry.setdefault("name", str(row.get("productName")).strip())
        entry.setdefault("count", 1)
        # Only take back what was counted, e.g. not for a row from before the history
        if old_group is not None and str(old_group) in entry["groups"]:
            _count_group(entry, old_group, -1)
        _count_group(entry, new_group, 1)
        changed = True

    if not changed:
        return None
    return prune(result)


def prune(
    history: Mapping[str, Any], max_items: int = MAX_HISTORY_ITEMS
) -> dict[str, Any]:
    """The history without the least used, oldest names beyond `max_items`."""
    if len(history) <= max_items:
        return dict(history)
    ranked = sorted(history.items(), key=_rank, reverse=True)
    return dict(ranked[:max_items])


def _rank(item: tuple[str, Mapping]) -> tuple[int, str]:
    entry = item[1]
    return (int(entry.get("count", 0)), str(entry.get("last_used", "")))


def most_used_group(entry: Mapping) -> int | None:
    """The category most rows with this name ended up in.

    A tie goes to the category used last.
    """
    groups = {int(k): v for k, v in (entry.get("groups") or {}).items() if v > 0}
    if not groups:
        return None
    best = max(groups.values())
    tied = [g for g, n in groups.items() if n == best]
    last = entry.get("last_group")
    return last if last in tied else min(tied)


def history_groups(history: Mapping[str, Any] | None) -> dict[str, int]:
    """`name_key` -> most used category, for the names that have one."""
    result: dict[str, int] = {}
    for key, entry in (history or {}).items():
        group_id = most_used_group(entry)
        if group_id is not None:
            result[key] = group_id
    return result


def _matches(name: str, query: str) -> int | None:
    """How well a name matches what was typed: 0 starts with it, 1 a word does,
    2 contains it, None not at all."""
    text = name.casefold()
    if text.startswith(query):
        return 0
    if any(word.startswith(query) for word in text.split()):
        return 1
    if query in text:
        return 2
    return None


def build_suggestions(
    history: Mapping[str, Any] | None,
    favorites: Iterable[Mapping] | None,
    articles: Iterable[Mapping] | None,
    group_for: Callable[[str], GroupMatch | None],
    query: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Item names to suggest while typing, best first.

    1. names from the history, most used first,
    2. the account's favourite items (ICA "baseitems"),
    3. ICA's articles, by name.

    Each name appears once. `group_for` gives the category an item with that
    name would get, so the suggestion shows what will happen when it is added.
    With a `query`, only names matching it are returned, the ones starting
    with it first.
    """
    candidates: list[tuple[str, str, int | None]] = []
    ranked_history = sorted((history or {}).items(), key=_rank, reverse=True)
    candidates.extend(
        (str(e.get("name") or k), "history", int(e.get("count", 0)))
        for k, e in ranked_history
    )
    candidates.extend(
        (str(f["text"]), "favorite", None)
        for f in sorted(favorites or [], key=lambda f: int(f.get("sortOrder") or 0))
        if f.get("text")
    )
    candidates.extend(
        (str(a["name"]), "article", None)
        for a in sorted(articles or [], key=lambda a: str(a.get("name", "")).casefold())
        if a.get("name")
    )

    needle = (query or "").strip().casefold()
    seen: set[str] = set()
    found: list[tuple[int, int, dict[str, Any]]] = []
    for order, (name, source, count) in enumerate(candidates):
        quality = _matches(name, needle) if needle else 0
        if quality is None:
            continue
        key = name_key(name)
        if not key or key in seen:
            continue
        seen.add(key)
        match = group_for(name)
        item: dict[str, Any] = {
            "name": name,
            "group_id": match.group_id if match else DEFAULT_ARTICLE_GROUP_ID,
            "source": source,
        }
        if count is not None:
            item["count"] = count
        found.append((quality, order, item))

    found.sort(key=lambda x: (x[0], x[1]))
    items = [item for _, _, item in found]
    return items[:limit] if limit else items
