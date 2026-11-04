"""Escaped value presentation, independent of field parsing and persistence."""

import json
from urllib.parse import quote, urlsplit


def display_kind(options):
    return options.display or ("url" if options.url_template is not None else "text")


def display_value(resource, field, value, *, formatted=False):
    options = resource.options.fields.get(field.name)
    kind = display_kind(options) if options is not None else "text"
    text = str(value) if formatted else str(field.format(value))
    if options is not None and options.url_template is not None and text:
        text = options.url_template.replace("{value}", quote(text, safe=""))
    if kind == "json" and text:
        try:
            text = json.dumps(json.loads(text), ensure_ascii=False, indent=2, allow_nan=False)
        except (ValueError, TypeError, RecursionError):
            pass
    preview = " ".join(text.split())
    return {
        "kind": kind,
        "text": text,
        "href": _http_url(text) if kind == "url" else None,
        "preview": preview[:90] + ("…" if len(preview) > 90 else ""),
        "expandable": len(text) > 90 or "\n" in text,
    }


def _http_url(value):
    if value != value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in value):
        return None
    try:
        url = urlsplit(value)
        if url.scheme.lower() in {"http", "https"} and url.hostname and "\\" not in value:
            return value
    except ValueError:
        pass
    return None
