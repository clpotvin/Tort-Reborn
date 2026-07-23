import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import discord

from Helpers.panel_render import build_embeds, asset_keys, ASSET_REGISTRY


def test_build_embeds_maps_fields_and_color():
    data = [{
        "title": "Rules",
        "description": "Be nice",
        "color": 3447003,
        "image_asset_key": None,
        "fields": [
            {"name": "1", "value": "No spam", "inline": False},
            {"name": "2", "value": "No leaks", "inline": True},
        ],
    }]
    embeds, files = build_embeds(data)
    assert len(embeds) == 1
    assert files == []
    e = embeds[0]
    assert e.title == "Rules"
    assert e.description == "Be nice"
    assert e.colour == discord.Colour(3447003)
    assert [(f.name, f.value, f.inline) for f in e.fields] == [
        ("1", "No spam", False), ("2", "No leaks", True)
    ]


def test_build_embeds_attaches_known_asset_once():
    key = next(iter(ASSET_REGISTRY))
    data = [
        {"title": "A", "fields": [], "image_asset_key": key},
        {"title": "B", "fields": [], "image_asset_key": key},
    ]
    embeds, files = build_embeds(data)
    assert len(files) == 1  # deduped
    assert embeds[0].image.url == embeds[1].image.url
    assert embeds[0].image.url.startswith("attachment://")


def test_build_embeds_ignores_unknown_asset_key():
    data = [{"title": "A", "fields": [], "image_asset_key": "does_not_exist"}]
    embeds, files = build_embeds(data)
    assert files == []
    assert embeds[0].image is None


def test_asset_keys_nonempty():
    assert len(asset_keys()) >= 1
