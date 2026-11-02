"""Validated colors for an individual admin instance."""

from __future__ import annotations

import re
from dataclasses import dataclass

COLOR = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})")


def _color(name: str, value: str) -> str:
    if not isinstance(value, str) or not COLOR.fullmatch(value):
        raise ValueError(f"Theme.{name} must be a #RGB or #RRGGBB color.")
    value = value.lower()
    if len(value) == 4:
        value = "#" + "".join(character * 2 for character in value[1:])
    return value


def _mix(color: str, background: str, weight: float) -> str:
    channels = (
        round(
            int(color[index : index + 2], 16) * weight
            + int(background[index : index + 2], 16) * (1 - weight)
        )
        for index in (1, 3, 5)
    )
    return "#" + "".join(f"{channel:02x}" for channel in channels)


@dataclass(init=False, kw_only=True)
class Theme:
    """Main UI colors, as #RGB or #RRGGBB. Related shades are derived automatically."""

    primary: str = "#3395fd"
    background: str = "#181818"
    surface: str = "#202020"
    text: str = "#fefefe"
    muted: str = "#b7b2bf"
    border: str = "#3b3b45"
    danger: str = "#ff8798"
    on_primary: str = "#111111"
    on_danger: str = "#111111"

    def __init__(
        self,
        *,
        primary: str = "#3395fd",
        background: str = "#181818",
        surface: str = "#202020",
        text: str = "#fefefe",
        muted: str = "#b7b2bf",
        border: str = "#3b3b45",
        danger: str = "#ff8798",
        on_primary: str = "#111111",
        on_danger: str = "#111111",
    ) -> None:
        self.primary = _color("primary", primary)
        self.background = _color("background", background)
        self.surface = _color("surface", surface)
        self.text = _color("text", text)
        self.muted = _color("muted", muted)
        self.border = _color("border", border)
        self.danger = _color("danger", danger)
        self.on_primary = _color("on_primary", on_primary)
        self.on_danger = _color("on_danger", on_danger)

    def stylesheet(self) -> str:
        colors = {
            "bg": self.background,
            "paper": self.surface,
            "text": self.text,
            "muted": self.muted,
            "line": self.border,
            "accent": self.primary,
            "accent-hover": _mix(self.primary, self.text, 0.8),
            "accent-soft": _mix(self.primary, self.surface, 0.08),
            "accent-border": _mix(self.primary, self.border, 0.3),
            "on-accent": self.on_primary,
            "danger": self.danger,
            "danger-soft": _mix(self.danger, self.surface, 0.08),
            "danger-border": _mix(self.danger, self.border, 0.3),
            "on-danger": self.on_danger,
            "subtle": _mix(self.text, self.surface, 0.02),
            "hover": _mix(self.text, self.surface, 0.04),
            "json-key": self.primary,
            "json-string": _mix(self.primary, self.text, 0.65),
            "json-number": self.text,
            "json-literal": self.muted,
        }
        channels = [int(self.surface[i : i + 2], 16) / 255 for i in (1, 3, 5)]
        light = sum(c * w for c, w in zip(channels, (0.2126, 0.7152, 0.0722), strict=True))
        scheme = "dark" if light < 0.5 else "light"
        return (
            ":root{"
            + ";".join(f"--{name}:{value}" for name, value in colors.items())
            + f";color-scheme:{scheme};accent-color:var(--accent)"
            + "}\n"
        )
