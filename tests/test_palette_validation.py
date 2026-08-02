"""Offline guardrail for the categorical palette tokens.

This intentionally uses only the standard library: it parses the authored CSS, applies
the Machado complete-dichromacy matrices in linear sRGB, and compares simulated colors
in CIE Lab. It is a reproducible design check, not a claim that one palette diagnoses or
fully accommodates every person's color vision.
"""

from __future__ import annotations

import math
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOKENS = ROOT / "static" / "css" / "tokens.css"
MODES = ("default", "universal", "protan", "deutan", "tritan", "mono")
TARGET_SIMULATION = {
    "default": None,
    "universal": None,
    "protan": "protan",
    "deutan": "deutan",
    "tritan": "tritan",
    "mono": None,
}
MATRICES = {
    "protan": ((0.152286, 1.052583, -0.204868), (0.114503, 0.786281, 0.099216), (-0.003882, -0.048116, 1.051998)),
    "deutan": ((0.367322, 0.860646, -0.227968), (0.280085, 0.672501, 0.047413), (-0.011820, 0.042940, 0.968881)),
    "tritan": ((1.255528, -0.076749, -0.178779), (-0.078411, 0.930809, 0.147602), (0.004733, 0.691367, 0.303900)),
}
LIGHT_SURFACE = "#ffffff"
DARK_SURFACE = "#171b22"
HEX = re.compile(r"#[0-9a-fA-F]{6}$")
PALETTE = re.compile(r"--palette-([a-z]+)-(\d):\s*(#[0-9a-fA-F]{6})")


def _palette_rows() -> dict[str, dict[str, list[str]]]:
    css = TOKENS.read_text(encoding="utf-8")
    light_css, dark_css = css.split("/* ---------- Color: dark theme ---------- */", maxsplit=1)

    def values(source: str) -> dict[str, dict[int, str]]:
        found: dict[str, dict[int, str]] = {mode: {} for mode in MODES}
        for mode, slot, value in PALETTE.findall(source):
            if mode in found:
                found[mode][int(slot)] = value.lower()
        return found

    light_values = values(light_css)
    dark_values = values(dark_css)
    light = {mode: [light_values[mode][slot] for slot in range(1, 9)] for mode in MODES}
    # A dark row only needs to override values that differ from Standard; missing
    # values inherit the light token exactly as CSS custom properties do.
    dark = {
        mode: [dark_values[mode].get(slot, light[mode][slot - 1]) for slot in range(1, 9)]
        for mode in MODES
    }
    return {"light": light, "dark": dark}


def _rgb(hex_value: str) -> tuple[float, float, float]:
    return tuple(int(hex_value[index : index + 2], 16) / 255 for index in (1, 3, 5))


def _linear(channel: float) -> float:
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def _lab(hex_value: str, simulation: str | None = None) -> tuple[float, float, float]:
    rgb = [_linear(channel) for channel in _rgb(hex_value)]
    if simulation:
        rgb = [max(0.0, min(1.0, sum(row[column] * rgb[column] for column in range(3)))) for row in MATRICES[simulation]]
    x = (0.4124564 * rgb[0] + 0.3575761 * rgb[1] + 0.1804375 * rgb[2]) / 0.95047
    y = 0.2126729 * rgb[0] + 0.7151522 * rgb[1] + 0.0721750 * rgb[2]
    z = (0.0193339 * rgb[0] + 0.1191920 * rgb[1] + 0.9503041 * rgb[2]) / 1.08883

    def f(value: float) -> float:
        return value ** (1 / 3) if value > 216 / 24389 else (24389 / 27 * value + 16) / 116

    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def _delta(first: str, second: str, simulation: str | None = None) -> float:
    a, b = _lab(first, simulation), _lab(second, simulation)
    return math.sqrt(sum((left - right) ** 2 for left, right in zip(a, b)))


def _luminance(hex_value: str) -> float:
    red, green, blue = (_linear(channel) for channel in _rgb(hex_value))
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _contrast(first: str, second: str) -> float:
    one, two = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (one + 0.05) / (two + 0.05)


def _minimum_pair_distance(colors: list[str], simulation: str | None) -> float:
    return min(_delta(colors[left], colors[right], simulation) for left in range(8) for right in range(left + 1, 8))


def _minimum_adjacent_distance(colors: list[str], simulation: str | None) -> float:
    return min(_delta(colors[index], colors[(index + 1) % 8], simulation) for index in range(8))


def test_palette_tokens_are_complete_valid_hexes_and_theme_aware() -> None:
    rows = _palette_rows()
    for theme in ("light", "dark"):
        for mode in MODES:
            assert len(rows[theme][mode]) == 8
            assert all(HEX.fullmatch(color) for color in rows[theme][mode])
            assert len(set(rows[theme][mode])) == 8


def test_target_simulations_keep_palette_slots_separated() -> None:
    rows = _palette_rows()
    for theme in ("light", "dark"):
        for mode in MODES:
            simulation = TARGET_SIMULATION[mode]
            colors = rows[theme][mode]
            # DeltaE 8 is a maintenance floor for all categorical hue pairs. The
            # monochrome option deliberately trades hue for ordered lightness, so
            # its evenly spaced gray steps have their own 4.5 DeltaE floor.
            minimum = 4.5 if mode == "mono" else 8
            assert _minimum_pair_distance(colors, simulation) >= minimum, (theme, mode)
            assert _minimum_adjacent_distance(colors, simulation) >= minimum, (theme, mode)
    # The general-purpose option must also avoid a collapse under all three types.
    for theme in ("light", "dark"):
        for simulation in MATRICES:
            assert _minimum_pair_distance(rows[theme]["universal"], simulation) >= 8, (theme, simulation)


def test_palette_marks_remain_visible_on_their_chart_surface() -> None:
    rows = _palette_rows()
    for theme, surface in (("light", LIGHT_SURFACE), ("dark", DARK_SURFACE)):
        for mode in MODES:
            # These are mark-vs-surface colors, not text. Labels remain --color-text;
            # a 1.5:1 floor prevents a swatch or chart series from disappearing.
            assert min(_contrast(color, surface) for color in rows[theme][mode]) >= 1.5, (theme, mode)


def main() -> int:
    rows = _palette_rows()
    checks = [
        ("complete theme-aware palette tokens", test_palette_tokens_are_complete_valid_hexes_and_theme_aware),
        ("target CVD separation", test_target_simulations_keep_palette_slots_separated),
        ("mark/surface visibility", test_palette_marks_remain_visible_on_their_chart_surface),
    ]
    failed = 0
    for name, check in checks:
        try:
            check()
            print(f"  PASS  {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  FAIL  {name}: {exc}")
    print("\nMinimum DeltaE (all pairs / adjacent, simulated target):")
    for theme in ("light", "dark"):
        for mode in MODES:
            colors, simulation = rows[theme][mode], TARGET_SIMULATION[mode]
            print(f"  {theme:5} {mode:9} {_minimum_pair_distance(colors, simulation):5.1f} / {_minimum_adjacent_distance(colors, simulation):5.1f}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
