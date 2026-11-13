"""Tests for categorising list items and the category services."""

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.ica.const import CONF_AUTO_CATEGORIZE, DOMAIN

from .conftest import LIST_ID

LIST_ENTITY = "todo.ica_veckohandling"


def _row(fake_api, uid):
    return next(r for r in fake_api.lists[LIST_ID]["rows"] if r["offlineId"] == uid)


async def test_unspecified_rows_get_a_category_on_update(hass, loaded_entry, mock_api):
    # "Gurka" is an ICA article in group 3, the row had no group
    sync = next(s for s in mock_api.syncs if s.get("changedRows"))
    assert [r["offlineId"] for r in sync["changedRows"]] == ["row-gurka"]
    assert _row(mock_api, "row-gurka")["articleGroupId"] == 3
    # Rows that don't match are left alone
    assert "articleGroupId" not in _row(mock_api, "row-banan")


async def test_a_row_is_only_categorised_once(hass, loaded_entry, mock_api):
    coordinator = loaded_entry.runtime_data
    syncs = len(mock_api.syncs)
    # Pretend ICA did not keep the change
    mock_api.lists[LIST_ID]["rows"][0]["articleGroupId"] = 12
    await coordinator.async_refresh_all()
    assert len(mock_api.syncs) == syncs


async def test_auto_categorize_can_be_turned_off(hass, config_entry, mock_api):
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        config_entry, options={**config_entry.options, CONF_AUTO_CATEGORIZE: False}
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_api.syncs == []
    await hass.config_entries.async_unload(config_entry.entry_id)


async def test_get_article_groups(hass, loaded_entry):
    response = await hass.services.async_call(
        DOMAIN, "get_article_groups", {}, blocking=True, return_response=True
    )
    assert {"id": 10, "name": "Mejeri"} in response["article_groups"]


async def test_get_article_groups_falls_back_to_built_in_list(
    hass, loaded_entry, mock_api
):
    async def broken():
        raise ValueError("bad answer")

    coordinator = loaded_entry.runtime_data
    coordinator._ica_article_groups._value = None
    coordinator._ica_article_groups._value_factory = broken

    groups = await coordinator.async_get_article_groups()
    assert len(groups) == 10
    assert {"id": 7, "name": "Hälsa & Skönhet"} in groups


async def test_get_shopping_list_items(hass, loaded_entry):
    response = await hass.services.async_call(
        DOMAIN,
        "get_shopping_list_items",
        {"entity_id": LIST_ENTITY},
        blocking=True,
        return_response=True,
    )
    items = {i["uid"]: i for i in response[LIST_ENTITY]["items"]}
    assert items["row-gurka"]["quantity"] == 1
    assert items["row-mjolk"]["completed"] is True
    assert items["row-banan"]["article_group"] == {"id": 12, "name": "Ospecificerad"}


async def test_set_item_article_group_updates_ica_and_is_remembered(
    hass, loaded_entry, mock_api
):
    response = await hass.services.async_call(
        DOMAIN,
        "set_item_article_group",
        {
            "entity_id": LIST_ENTITY,
            "items": [
                {"uid": "row-banan", "article_group_id": 4},
                {"uid": "missing", "article_group_id": 4},
            ],
        },
        blocking=True,
        return_response=True,
    )
    assert response[LIST_ENTITY] == {"updated": ["row-banan"], "not_found": ["missing"]}
    banan = _row(mock_api, "row-banan")
    assert banan["articleGroupId"] == 4
    assert banan["articleGroupIdExtended"] == 4
    # Other fields of the row are kept
    assert banan["offerId"] == "offer-1"

    # A new "Bananer" gets the same group without any article match
    await hass.services.async_call(
        "todo",
        "add_item",
        {"entity_id": LIST_ENTITY, "item": "2 Bananer"},
        blocking=True,
    )
    created = mock_api.syncs[-1]["createdRows"][0]
    assert created["articleGroupId"] == 4


async def test_set_item_article_group_without_remember(hass, loaded_entry):
    await hass.services.async_call(
        DOMAIN,
        "set_item_article_group",
        {
            "entity_id": LIST_ENTITY,
            "items": [{"uid": "row-banan", "article_group_id": 4}],
            "remember": False,
        },
        blocking=True,
        return_response=True,
    )
    assert loaded_entry.runtime_data.category_choices() == {}


async def test_set_item_article_group_rejects_unknown_groups(hass, loaded_entry):
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "set_item_article_group",
            {
                "entity_id": LIST_ENTITY,
                "items": [{"uid": "row-banan", "article_group_id": 999}],
            },
            blocking=True,
            return_response=True,
        )
