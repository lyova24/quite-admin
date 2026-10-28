"""Validated colors for an individual admin instance."""

from __future__ import annotations

import re
from dataclasses import dataclass, fields

COLOR = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})")


def _mix(color: str, background: str, weight: float) -> str:
    channels = (
        round(
            int(color[index : index + 2], 16) * weight
            + int(background[index : index + 2], 16) * (1 - weight)
        )
        for index in (1, 3, 5)
    )
    return "#" + "".join(f"{channel:02x}" for channel in channels)


@dataclass(frozen=True, kw_only=True)
class Theme:
    """Main UI colors, as #RGB or #RRGGBB. Related shades are derived automatically."""

    primary: str = "#3e6656"
    background: str = "#f7f8fa"
    surface: str = "#ffffff"
    text: str = "#1c2635"
    muted: str = "#7b8594"
    border: str = "#e9ecf1"
    danger: str = "#ba4949"
    on_primary: str = "#ffffff"
    on_danger: str = "#ffffff"

    def __post_init__(self) -> None:
        for item in fields(self):
            value = getattr(self, item.name)
            if not isinstance(value, str) or not COLOR.fullmatch(value):
                raise ValueError(f"Theme.{item.name} must be a #RGB or #RRGGBB color.")
            value = value.lower()
            if len(value) == 4:
                value = "#" + "".join(character * 2 for character in value[1:])
            object.__setattr__(self, item.name, value)

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
            "hover": _mix(self.primary, self.surface, 0.03),
        }
        return ":root{" + ";".join(f"--{name}:{value}" for name, value in colors.items()) + "}\n"
