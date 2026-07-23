"""One-off: seed promotions + taq-faq as info_panels rows.

Run once against the target DB. Idempotent by name: skips a panel that already exists.
Set the channel IDs below to the real target channels before running:

    python -m scripts.seed_info_panels

message_id is left NULL, so on first publish the bot posts a fresh message and stores its id.
"""
import json

import discord

from Helpers.database import DB
from Commands.generate import (
    _build_promotions_embeds,
    _build_taq_faq_embeds_page1,
    _build_taq_faq_embeds_page2,
)

# TODO(Aiden): set these to the live channels the old /generate commands posted to.
PROMOTIONS_CHANNEL_ID = 0
FAQ_CHANNEL_ID = 0

# The old FAQ command attaches the banner as a standalone message-level file. Our panel
# model only supports per-embed images, so the banner goes on the first page-1 embed.
FAQ_PAGE1_BANNER = "taq_faq"


def _embed_to_dict(embed: discord.Embed, image_asset_key):
    d = embed.to_dict()
    fields = [
        {"name": f.get("name", ""), "value": f.get("value", ""), "inline": bool(f.get("inline"))}
        for f in d.get("fields", [])
    ]
    return {
        "title": d.get("title"),
        "description": d.get("description"),
        "color": d.get("color"),
        "image_asset_key": image_asset_key,
        "fields": fields,
    }


def _seed(name, channel_id, embed_dicts):
    payload = json.dumps(embed_dicts)
    db = DB()
    try:
        db.connect()
        db.cursor.execute("SELECT 1 FROM info_panels WHERE name = %s", (name,))
        if db.cursor.fetchone():
            print(f"skip (exists): {name}")
            return
        db.cursor.execute(
            "INSERT INTO info_panels (name, channel_id, draft, published, sync_state) "
            "VALUES (%s, %s, %s::jsonb, %s::jsonb, 'idle')",
            (name, channel_id or None, payload, payload),
        )
        db.connection.commit()
        print(f"seeded: {name}")
    finally:
        db.close()


def main():
    promo = [_embed_to_dict(e, None) for e in _build_promotions_embeds()]
    _seed("Promotions", PROMOTIONS_CHANNEL_ID, promo)

    # Banner on the first embed only; the rest carry no image.
    faq1 = [
        _embed_to_dict(e, FAQ_PAGE1_BANNER if i == 0 else None)
        for i, e in enumerate(_build_taq_faq_embeds_page1())
    ]
    _seed("TAq FAQ (1)", FAQ_CHANNEL_ID, faq1)

    faq2 = [_embed_to_dict(e, None) for e in _build_taq_faq_embeds_page2()]
    _seed("TAq FAQ (2)", FAQ_CHANNEL_ID, faq2)


if __name__ == "__main__":
    main()
