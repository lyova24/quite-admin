# Language and appearance

Configure each admin instance when you create it. The same options work in FastAPI and Litestar:

```python
from quite_admin import Admin, Theme

admin = Admin(
    auth=auth_backend,
    secret_key=session_secret,
    title="Store administration",
    description="Products, customers and orders in one place.",
    language="en",
    theme=Theme(
        primary="#2563eb",
        background="#f8fafc",
        surface="#ffffff",
        text="#0f172a",
        muted="#64748b",
        border="#e2e8f0",
        danger="#dc2626",
        on_primary="#ffffff",
        on_danger="#ffffff",
    ),
)
```

All settings are optional. Defaults are `title="Quite Admin"`, `description=""`,
`language="en"` and the original light theme with a green accent.

## Language

Set `language="en"` for English or `language="ru"` for Russian. Other values raise `ValueError`.
The language applies to all built-in screens: sign-in, navigation, CRUD actions, empty states,
pagination, boolean labels, validation errors and standard library error messages.
Russian record, collection and field counts use the appropriate plural forms.
The HTML `lang` attribute follows the selected language.

Language selection is application configuration. There is no browser-language detection,
per-user language preference or built-in language switcher.
Different admin instances can use different languages and themes in the same application.
Give them different `session_cookie` names when mounting multiple instances on the same host.

Model and field labels, help text, enum choices, custom adapter errors, custom-page text
and record values belong to your application. They are not translated automatically.
Use `ModelOptions(label=...)` and `FieldOptions(label=..., help_text=...)` to name your own fields.
Only known library messages are translated; unknown error messages are displayed as supplied.
Submitted boolean values remain `true` / `false`, and stored data, URLs and log event names do not change.

## Name and description

`title` is the admin name in the browser title, sidebar and the main heading on the sign-in
and overview pages. The footer retains the Quite Admin library name.

`description` is plain text shown below the name on the sign-in and overview pages.
It is also used in the HTML description metadata. If empty, those pages show their localized
default introduction and omit the description meta tag.
Both settings are escaped as text; they do not accept HTML.

## Colors

`Theme` accepts hexadecimal `#RGB` or `#RRGGBB` colors, case-insensitively.
Invalid colors raise `ValueError` when constructing the theme.

| Option | Default | Used for |
| --- | --- | --- |
| `primary` | `#3e6656` | Primary buttons, navigation accents, icons and positive badges |
| `background` | `#f7f8fa` | Main page background |
| `surface` | `#ffffff` | Sidebar, header, cards, inputs and panels |
| `text` | `#1c2635` | Main text |
| `muted` | `#7b8594` | Secondary text and hints |
| `border` | `#e9ecf1` | Separators and borders |
| `danger` | `#ba4949` | Delete actions and error messages |
| `on_primary` | `#ffffff` | Text on primary buttons and brand marks |
| `on_danger` | `#ffffff` | Text on destructive buttons |

Hover colors and tinted backgrounds are derived from the palette. Choose readable text/background
combinations, including `on_primary` and `on_danger`. For a dark palette:

```python
theme = Theme(
    primary="#93c5fd",
    background="#0f172a",
    surface="#172033",
    text="#e2e8f0",
    muted="#94a3b8",
    border="#334155",
    danger="#fca5a5",
    on_primary="#0f172a",
    on_danger="#450a0a",
)
```

The theme is served from the admin's own `/theme.css` route and loaded after the base stylesheet.
Mount paths and reverse-proxy prefixes are included automatically.
No inline styles, external CDN or JavaScript are required; the existing `style-src 'self'` policy stays in place.

## Custom templates

Templates extending `quite_admin/base.html` inherit the configured name, language and colors.
The shared context includes `title`, `description`, `language`, `theme`, `t` and `tn`:

```html
{% extends "quite_admin/base.html" %}
{% block content %}
  <h1>{{ 'Отчёты' if language == 'ru' else 'Reports' }}</h1>
  <p>{{ t('Save changes') }}</p>
  <p>{{ total }} {{ tn('record', 'records', total) }}</p>
{% endblock %}
```

`t(message, **values)` and `tn(singular, plural, count)` use the built-in message catalog.
Custom copy needs your application's translations, as shown in the heading above.
In Python, the same helpers are available as `admin.gettext(...)` and `admin.ngettext(...)`.

Use `var(--accent)`, `var(--paper)`, `var(--text)`, `var(--muted)`, `var(--line)` and
`var(--danger)` in your own same-origin stylesheets to follow the selected palette.
See [custom pages and templates](custom-pages.md) for template registration.
