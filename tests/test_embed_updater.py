from Helpers.app_transcript import CLOSED_POLL_STATUS
from Helpers.embed_updater import is_poll_status_downgrade


def test_downgrade_from_closed_is_blocked():
    assert is_poll_status_downgrade(CLOSED_POLL_STATUS, ":orange_circle: Registered") is True


def test_closing_is_allowed():
    assert is_poll_status_downgrade(":orange_circle: Registered", CLOSED_POLL_STATUS) is False


def test_closed_to_closed_is_allowed():
    assert is_poll_status_downgrade(CLOSED_POLL_STATUS, CLOSED_POLL_STATUS) is False


def test_normal_lifecycle_transition_is_allowed():
    assert is_poll_status_downgrade(":green_circle: Received", ":orange_circle: Accepted") is False


def test_missing_current_status_is_allowed():
    assert is_poll_status_downgrade(None, ":orange_circle: Registered") is False
