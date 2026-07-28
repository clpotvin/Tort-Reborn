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
    return base


def test_none_when_no_head():
    assert classify_transcript_candidate(None, NOW) == "none"


def test_wait_when_head_still_open():
    assert classify_transcript_candidate(_head(poll_status=":green_circle: Received"), NOW) == "wait"


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
