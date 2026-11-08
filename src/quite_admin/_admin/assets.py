"""Built-in UI assets and content hashes shared by rendering and the browser demo."""

from __future__ import annotations

import base64
import hashlib
from functools import lru_cache
from pathlib import Path

BUILTIN_SCRIPTS = {
    "relations.js": (),
    "schema.js": (),
    "filters.js": (),
    "forms.js": ("datetime.js",),
    "datetime.js": (),
    "navigation.js": (),
    "table-navigation.js": (),
    "dashboard.js": (),
    "listing.js": (),
    "inline.js": (),
    "history.js": ("datetime.js",),
    "values.js": (),
}
STYLESHEETS = (
    "admin.css",
    "shell.css",
    "table-navigation.css",
    "dashboard.css",
    "schema-layout.css",
)


def script_names(names: tuple[str, ...]) -> tuple[str, ...]:
    """Expand the fixed dependencies once, preserving the caller's script order."""
    ordered = {}
    for name in names:
        if name not in BUILTIN_SCRIPTS:
            raise ValueError("Unknown built-in script.")
        for dependency in (*BUILTIN_SCRIPTS[name], name):
            ordered[dependency] = None
    return tuple(ordered)


def script_integrity(path: Path) -> str:
    stat = path.stat()
    # Invalidate for edits and atomic replacements, including equal-size files
    # whose modification time was preserved by a build or deployment tool.
    revision = (stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size, stat.st_ino)
    return _script_integrity(path, revision)


@lru_cache(maxsize=128)
def _script_integrity(path: Path, revision: tuple[int, ...]) -> str:
    digest = base64.b64encode(hashlib.sha256(path.read_bytes()).digest()).decode()
    return "sha256-" + digest
