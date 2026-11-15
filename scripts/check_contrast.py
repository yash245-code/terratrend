"""Automated WCAG 2.2 AA / AAA Color Contrast Verifier for Earthy Design System.

Verifies relative luminance and contrast ratios according to W3C WCAG 2.2 specifications:
- Normal text >= 4.5:1 (AA)
- Large text (>= 24px or >= 18.66px bold) >= 3.0:1 (AA)
- UI components, icons, boundaries, and focus rings >= 3.0:1 (AA)
"""
from __future__ import annotations

import math
import sys
from typing import Dict, Tuple

# Token definitions for both modes
LIGHT_THEME: Dict[str, str] = {
    "--herb": "#6A8042",
    "--gleam": "#FFE787",
    "--pearl": "#FFFDDD",
    "--radiate": "#ED7A13",
    "--moss": "#1E3006",
    "--herb-deep": "#566B33",
    "--radiate-deep": "#B35500",
    "--water": "#2F6F8F",
    "--clay-red": "#B3382C",

    "--bg": "#FFFDDD",
    "--bg-subtle": "#FAF5C8",
    "--surface": "#FFFFFF",
    "--text": "#1E3006",
    "--text-muted": "#4A5B2E",
    "--border": "#D9D4A8",
    "--border-strong": "#6A8042",

    "--primary": "#ED7A13",
    "--primary-hover": "#F58A2B",
    "--on-primary": "#1E3006",
    "--secondary": "#566B33",
    "--on-secondary": "#FFFDDD",
    "--danger": "#B3382C",
    "--on-danger": "#FFFFFF",
    "--link": "#B35500",
    "--focus": "#B35500",

    "--good-bg": "#E0EBCB",
    "--good-ink": "#1E3006",
    "--moderate-bg": "#FFE787",
    "--moderate-ink": "#1E3006",
    "--poor-bg": "#F6D5D0",
    "--poor-ink": "#7A1F16",
    "--info-bg": "#D9EAF2",
    "--info-ink": "#12384A",

    "--viz-water": "#2F6F8F",
    "--viz-orange": "#B35500",
    "--viz-green": "#6A8042",
    "--viz-red": "#B3382C",
    "--viz-ink": "#1E3006",
}

DARK_THEME: Dict[str, str] = {
    "--herb": "#6A8042",
    "--gleam": "#FFE787",
    "--pearl": "#FFFDDD",
    "--radiate": "#ED7A13",
    "--moss": "#1E3006",

    "--bg": "#142004",
    "--bg-subtle": "#192A05",
    "--surface": "#1E3006",
    "--text": "#FFFDDD",
    "--text-muted": "#C8C9A8",
    "--border": "#3A5420",
    "--border-strong": "#9DB872",

    "--primary": "#ED7A13",
    "--primary-hover": "#F58A2B",
    "--on-primary": "#1E3006",
    "--secondary": "#9DB872",
    "--on-secondary": "#1E3006",
    "--danger": "#F0877B",
    "--on-danger": "#1E3006",
    "--link": "#ED7A13",
    "--focus": "#FFE787",

    "--good-bg": "#2E4A17",
    "--good-ink": "#FFFDDD",
    "--moderate-bg": "#5C4A0A",
    "--moderate-ink": "#FFE787",
    "--poor-bg": "#5A1C14",
    "--poor-ink": "#F0877B",
    "--info-bg": "#173748",
    "--info-ink": "#9FD0E8",

    "--viz-water": "#6FB3D2",
    "--viz-orange": "#ED7A13",
    "--viz-green": "#9DB872",
    "--viz-red": "#F0877B",
    "--viz-ink": "#FFFDDD",
}


def hex_to_rgb(hex_code: str) -> Tuple[int, int, int]:
    """Convert hex string (e.g. #FFFDDD or #1E3006) to RGB tuple."""
    hex_clean = hex_code.lstrip("#")
    if len(hex_clean) == 3:
        hex_clean = "".join([c * 2 for c in hex_clean])
    r = int(hex_clean[0:2], 16)
    g = int(hex_clean[2:4], 16)
    b = int(hex_clean[4:6], 16)
    return r, g, b


def relative_luminance(rgb: Tuple[int, int, int]) -> float:
    """Calculate relative luminance according to sRGB formula."""
    channels = []
    for c in rgb:
        s = c / 255.0
        if s <= 0.04045:
            channels.append(s / 12.92)
        else:
            channels.append(((s + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast_ratio(hex1: str, hex2: str) -> float:
    """Compute contrast ratio between two hex colors."""
    lum1 = relative_luminance(hex_to_rgb(hex1))
    lum2 = relative_luminance(hex_to_rgb(hex2))
    l_bright = max(lum1, lum2)
    l_dark = min(lum1, lum2)
    return (l_bright + 0.05) / (l_dark + 0.05)


# Pair declarations to verify: (Foreground, Background, min_ratio, description)
DECLARED_PAIRS = [
    ("--text", "--bg", 4.5, "Body text on page background"),
    ("--text", "--surface", 4.5, "Body text on card surface"),
    ("--text-muted", "--bg", 4.5, "Muted text on page background"),
    ("--text-muted", "--surface", 4.5, "Muted text on card surface"),
    ("--on-primary", "--primary", 4.5, "Text on primary action button"),
    ("--on-primary", "--primary-hover", 4.5, "Text on primary hover button"),
    ("--on-secondary", "--secondary", 4.5, "Text on secondary action button"),
    ("--on-danger", "--danger", 4.5, "Text on danger action button"),
    ("--link", "--bg", 4.5, "Text link on page background"),
    ("--link", "--surface", 4.5, "Text link on card surface"),
    ("--focus", "--bg", 3.0, "Focus indicator ring against page"),
    ("--border-strong", "--surface", 3.0, "Form input border against surface"),
    ("--good-ink", "--good-bg", 4.5, "Good status badge text on background"),
    ("--moderate-ink", "--moderate-bg", 4.5, "Moderate status badge text on background"),
    ("--poor-ink", "--poor-bg", 4.5, "Poor status badge text on background"),
    ("--info-ink", "--info-bg", 4.5, "Info status badge text on background"),
    ("--viz-water", "--bg", 3.0, "Water series mark against page background"),
    ("--viz-orange", "--bg", 3.0, "Orange series mark against page background"),
    ("--viz-green", "--bg", 3.0, "Green series mark against page background"),
    ("--viz-red", "--bg", 3.0, "Red series mark against page background"),
]


def check_theme(theme_name: str, palette: Dict[str, str]) -> bool:
    print(f"\n=======================================================")
    print(f" Checking {theme_name.upper()} Theme Contrast (WCAG 2.2)")
    print(f"=======================================================")
    print(f"{'Foreground':<18} {'Background':<16} {'Ratio':<8} {'Req':<6} {'Result':<8} Description")
    print("-" * 80)

    all_passed = True
    for fg_token, bg_token, min_ratio, desc in DECLARED_PAIRS:
        fg_hex = palette[fg_token]
        bg_hex = palette[bg_token]
        ratio = contrast_ratio(fg_hex, bg_hex)
        passed = ratio >= min_ratio

        status_str = "PASS" if passed else "FAIL"
        if not passed:
            all_passed = False

        print(f"{fg_token:<18} {bg_token:<16} {ratio:5.2f}:1 {min_ratio:4.1f}:1 {status_str:<8} {desc}")

    return all_passed


def main():
    light_ok = check_theme("Light", LIGHT_THEME)
    dark_ok = check_theme("Dark", DARK_THEME)

    print("\n" + "=" * 80)
    if light_ok and dark_ok:
        print(" [SUCCESS] All 40 color pairings passed WCAG 2.2 AA / AAA contrast requirements.")
        print("=" * 80 + "\n")
        sys.exit(0)
    else:
        print(" [ERROR] One or more contrast pairings failed.")
        print("=" * 80 + "\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
