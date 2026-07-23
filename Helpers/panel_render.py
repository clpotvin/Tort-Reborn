import os
from pathlib import Path

import discord

# Banner assets live alongside the bot's other guild-info images.
_GUILD_INFO_ASSET_DIR = Path(__file__).parent.parent / "images" / "guild_info"

# Asset key -> absolute PNG path. Reuses the existing banner files.
ASSET_REGISTRY = {
    "guild_rules_banner": str(_GUILD_INFO_ASSET_DIR / "guild_rules_banner.png"),
    "guild_info_banner": str(_GUILD_INFO_ASSET_DIR / "guild_info_banner.png"),
    "taq_faq": str(_GUILD_INFO_ASSET_DIR / "taq_faq.png"),
    "applications": str(_GUILD_INFO_ASSET_DIR / "applications.png"),
}


def asset_keys():
    return list(ASSET_REGISTRY.keys())


def build_embeds(panel_embeds):
    """Render stored panel jsonb into (embeds, files).

    Each element: {title, description, color, image_asset_key, fields:[{name,value,inline}]}.
    Unknown/missing asset keys are ignored. Identical assets are attached once.
    """
    embeds = []
    files = []
    used_filenames = set()

    for item in panel_embeds:
        e = discord.Embed()
        if item.get("title"):
            e.title = item["title"]
        if item.get("description"):
            e.description = item["description"]
        if item.get("color") is not None:
            e.colour = discord.Colour(int(item["color"]))
        for f in item.get("fields", []) or []:
            e.add_field(
                name=f.get("name", "​"),
                value=f.get("value", "​"),
                inline=bool(f.get("inline")),
            )
        key = item.get("image_asset_key")
        if key and key in ASSET_REGISTRY:
            path = ASSET_REGISTRY[key]
            filename = os.path.basename(path)
            if filename not in used_filenames:
                files.append(discord.File(path, filename=filename))
                used_filenames.add(filename)
            e.set_image(url=f"attachment://{filename}")
        embeds.append(e)

    return embeds, files
