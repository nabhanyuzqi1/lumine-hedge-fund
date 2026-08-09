#!/usr/bin/env python3
"""WCAG AA contrast audit for semantic token pairs on bg-base."""

import math

COLORS = {
    "bg-base": "#0b0f17",
    "text-primary": "#e8eef7",
    "text-secondary": "#a7b3c5",
    "text-muted": "#6d7c92",
    "accent": "#4d8dff",
    "up": "#34d399",
    "down": "#f0555b",
    "warn": "#ffb020",
    "danger": "#ff4d5e",
    "info": "#22d3ee",
}

PAIRS = [
    ("text-primary", "bg-base"),
    ("text-secondary", "bg-base"),
    ("text-muted", "bg-base"),
    ("accent", "bg-base"),
    ("up", "bg-base"),
    ("down", "bg-base"),
    ("warn", "bg-base"),
    ("danger", "bg-base"),
    ("info", "bg-base"),
]


def hex_to_rgb(hex_color: str) -> tuple[float, float, float]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))


def luminance(rgb: tuple[float, float, float]) -> float:
    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else math.pow((c + 0.055) / 1.055, 2.4)

    return 0.2126 * channel(rgb[0]) + 0.7152 * channel(rgb[1]) + 0.0722 * channel(rgb[2])


def contrast_ratio(fg_hex: str, bg_hex: str) -> float:
    l1 = luminance(hex_to_rgb(fg_hex))
    l2 = luminance(hex_to_rgb(bg_hex))
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def main() -> None:
    print("WCAG AA contrast audit (normal text ≥ 4.5:1)\n")
    all_pass = True
    for fg_name, bg_name in PAIRS:
        ratio = contrast_ratio(COLORS[fg_name], COLORS[bg_name])
        status = "PASS" if ratio >= 4.5 else "FAIL"
        if status == "FAIL":
            all_pass = False
        print(f"{fg_name:14} on {bg_name:10}  {ratio:5.2f}:1  {status}")

    print()
    if all_pass:
        print("All pairs meet WCAG AA for normal text.")
    else:
        print("Some pairs fall below WCAG AA for normal text.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
