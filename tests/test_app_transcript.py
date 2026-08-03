import datetime

from Helpers.app_transcript import (
    classify_transcript_candidate,
    AUTO_TRANSCRIBE_DELAY,
    CLOSED_POLL_STATUS,
)

UTC = datetime.timezone.utc
NOW = datetime.datetime(2026, 7, 27, 12, 0, tzinfo=UTC)


def _head(**overrides):
    base = {
        "poll_status": CLOSED_POLL_STATUS,
        "channel_id": 123,
        "effective_closed_at": NOW - datetime.timedelta(days=4),
    }
    base.update(overrides)
    # Mirror _fetch_transcript_head: effective_closed_at is
    # COALESCE(closed_at, reviewed_at), so closed_at tracks the effective
    # timestamp unless a test explicitly decouples them (reviewed-but-open).
    if "closed_at" not in overrides:
        base["closed_at"] = base["effective_closed_at"]
    return base


def test_none_when_no_head():
    assert classify_transcript_candidate(None, NOW) == "none"


def test_wait_when_head_still_open():
    head = _head(poll_status=":green_circle: Received", closed_at=None, effective_closed_at=None)
    assert classify_transcript_candidate(head, NOW) == "wait"


def test_transcribe_when_closed_at_set_despite_stale_poll_status():
    # Regression: auto-registration completing after close overwrote poll_status
    # (Closed -> Registered) and stalled the queue. closed_at is stamped once and
    # never regresses, so it wins over poll_status.
    head = _head(poll_status=":orange_circle: Registered")
    assert classify_transcript_candidate(head, NOW) == "transcribe"


def test_skip_when_closed_at_set_stale_poll_status_and_no_channel():
    head = _head(poll_status=":orange_circle: Registered", channel_id=None)
    assert classify_transcript_candidate(head, NOW) == "skip"


def test_wait_when_closed_at_set_but_delay_not_elapsed():
    head = _head(
        poll_status=":orange_circle: Registered",
        closed_at=NOW - datetime.timedelta(days=2),
        effective_closed_at=NOW - datetime.timedelta(days=2),
    )
    assert classify_transcript_candidate(head, NOW) == "wait"


def test_wait_when_reviewed_but_not_closed():
    # reviewed_at feeds effective_closed_at via COALESCE; a reviewed-but-open
    # ticket (no closed_at, poll_status not Closed) must still wait.
    head = _head(
        poll_status=":orange_circle: Accepted",
        closed_at=None,
        effective_closed_at=NOW - datetime.timedelta(days=10),
    )
    assert classify_transcript_candidate(head, NOW) == "wait"


def test_skip_when_no_channel():
    assert classify_transcript_candidate(_head(channel_id=None), NOW) == "skip"


def test_wait_when_delay_not_elapsed():
    assert classify_transcript_candidate(_head(effective_closed_at=NOW - datetime.timedelta(days=2)), NOW) == "wait"


def test_wait_when_no_closed_timestamp():
    assert classify_transcript_candidate(_head(effective_closed_at=None), NOW) == "wait"


def test_transcribe_when_closed_and_elapsed():
    assert classify_transcript_candidate(_head(), NOW) == "transcribe"


def test_transcribe_exactly_at_boundary():
    assert classify_transcript_candidate(_head(effective_closed_at=NOW - AUTO_TRANSCRIBE_DELAY), NOW) == "transcribe"


from types import SimpleNamespace

from Helpers.app_transcript import build_transcript_text


def _msg(content="hi there", author_name="Alice", bot=False):
    return SimpleNamespace(
        created_at=datetime.datetime(2026, 7, 20, 9, 30, tzinfo=UTC),
        author=SimpleNamespace(display_name=author_name, bot=bot),
        content=content,
        embeds=[],
        attachments=[],
    )


def test_build_transcript_text_includes_header_and_body():
    app = {
        "answers": {"ign": "Zorak"},
        "application_type": "guild",
        "discord_username": "alice",
        "discord_id": "42",
        "status": "accepted",
    }
    text = build_transcript_text(app, [_msg()], "accepted-3726-zorak")
    assert "=== Application Transcript ===" in text
    assert "Channel: #accepted-3726-zorak" in text
    assert "Type: Guild Member" in text
    assert "IGN: Zorak" in text
    assert "Alice" in text
    assert "hi there" in text


def test_build_transcript_text_community_label_and_bot_tag():
    app = {
        "answers": {},
        "application_type": "community",
        "discord_username": "bob",
        "discord_id": "7",
        "status": "denied",
    }
    text = build_transcript_text(app, [_msg(author_name="TortBot", bot=True)], "c-denied-3727-bob")
    assert "Type: Community Member" in text
    assert "IGN: N/A" in text
    assert "TortBot [BOT]" in text
