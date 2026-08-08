from Commands import snipe


def test_stats_card_scales_long_ign(monkeypatch):
    long_ign = "VeryLongMinecraftIGN_ThatWouldOverflow"
    captured = {}
    original_add_line = snipe.addLine

    def capture_add_line(text, draw, font, x, y, *args, **kwargs):
        if text == long_ign:
            captured["font"] = font
            captured["draw"] = draw
        return original_add_line(text, draw, font, x, y, *args, **kwargs)

    monkeypatch.setattr(snipe, "addLine", capture_add_line)

    snipe._generate_snipe_card(
        long_ign,
        0,
        None,
        None,
        None,
        0,
        0,
        0,
        0,
        0,
        None,
        None,
        [],
        [],
        [],
        None,
        0,
        0,
        0,
    )

    assert captured
    width = captured["draw"].textbbox((0, 0), long_ign, font=captured["font"])[2]
    assert width <= 385
