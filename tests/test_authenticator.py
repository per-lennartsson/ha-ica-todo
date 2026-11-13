"""Tests for the ICA authenticator."""

from unittest.mock import patch

from custom_components.ica.authenticator import IcaAuthenticator


def test_refresh_does_not_mutate_the_original_state() -> None:
    """A refreshed token must not leak into the state it was created from.

    Home Assistant only persists config entry data when it differs from the current
    data, so mutating the shared token dict in place would mean the refreshed token
    is never written to disk.
    """
    original = {
        "client": {"client_id": "id", "client_secret": "secret", "scope": "s"},
        "token": {
            "access_token": "old-access",
            "refresh_token": "old-refresh",
            "expires_in": 2592000,
            "expiry": "2000-01-01 00:00:00+00:00",
        },
    }
    auth = IcaAuthenticator({"username": "u", "password": "p"}, original)

    with patch.object(
        IcaAuthenticator,
        "get_refresh_token",
        return_value={"access_token": "new-access", "refresh_token": "new-refresh"},
    ):
        new_state = auth.ensure_login()

    assert new_state["token"]["access_token"] == "new-access"
    assert new_state["token"]["refresh_token"] == "new-refresh"
    assert original["token"]["access_token"] == "old-access"
    assert original["token"]["refresh_token"] == "old-refresh"
    assert new_state != original
