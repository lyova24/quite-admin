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
    logo="assets/logo.svg",
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
`language="en"` and a neutral light theme with a restrained green accent.

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
It is also used in the HTML description metadata. If empty, those pages omit the introduction
and the description meta tag. Built-in screens contain no marketing slogans.
Both settings are escaped as text; they do not accept HTML.

Set `logo` to an existing local SVG, PNG, JPEG, WebP or GIF file. Relative paths are resolved
against the application's working directory. It is served from the admin's `/logo` route,
including mount/proxy prefixes, and appears in the sidebar and sign-in page.
It defaults to the `q.` mark. Missing files and unsupported extensions raise `ValueError`.
Custom templates receive `logo_url`; no external image hosts or CSP changes are required.

## Colors

`Theme` accepts hexadecimal `#RGB` or `#RRGGBB` colors, case-insensitively.
Invalid colors raise `ValueError` when constructing the theme.

| Option | Default | Used for |
| --- | --- | --- |
| `primary` | `#3e6656` | Primary actions, selected navigation and active search/sort indicators |
| `background` | `#f5f6f8` | Main page background |
| `surface` | `#ffffff` | Sidebar, header, cards, inputs and panels |
| `text` | `#20252b` | Main text |
| `muted` | `#626b76` | Secondary text and hints |
| `border` | `#dce0e5` | Separators and borders |
| `danger` | `#b43e3e` | Delete actions and error messages |
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

## Shared interface system

Built-in screens share the same tokens and components. The system font stack is retained;
no font download is required. Typography uses 28 px page titles, 16 px section headings,
14 px inputs, body text and table values, 13 px labels and 12 px secondary details. Spacing follows
a 4 px grid; corners use 4 px badges, 6 px controls and 8 px panels. White surfaces sit on a
neutral page background with 1 px borders and no decorative shadows or gradients.

Lists use 44 px rows, right-aligned numeric columns and tabular numerals. The current sort
has a directional arrow and `aria-sort`; a newly selected column sorts ascending first.
The toolbar sits above the table frame, and the record count sits beside the page title.
An active search is shown below the toolbar. Clearing it resets the page and preserves
sorting and page size. Rows retain keyboard-accessible record links and a separate delete
confirmation link. Hover and keyboard focus identify the current row; there is no bulk selection.
Boolean values use neutral text: true/false does not imply success/failure.
The accent identifies actions and selection; red identifies destructive actions and errors.

Record forms group writable fields, structured JSON data, read-only values and relationships
into sections within one surface. The footer keeps save/cancel actions visible while scrolling.
Built-in controls link their hints and validation errors with `aria-describedby` and mark invalid
fields with `aria-invalid`. Custom field templates should follow the same pattern. Custom record
actions appear in a separate Actions section. On small screens, forms use a single column,
navigation scrolls horizontally and tables retain horizontal scrolling for comparison.

Use the tokens in your own same-origin stylesheet when extending the interface:

| Tokens | Purpose |
| --- | --- |
| `--text-xs`, `--text-sm`, `--text-base`, `--text-section`, `--text-title` | Typography scale |
| `--space-1` … `--space-6`, `--space-8`, `--space-10` | 4, 8, 12, 16, 20, 24, 32 and 40 px spacing |
| `--radius-sm`, `--radius-control`, `--radius` | Badge, control and surface corners |
| `--bg`, `--paper`, `--subtle`, `--hover` | Page, surface, inset and row interaction levels |
| `--line`, `--border`, `--control-height` | Borders and shared 38 px control height |

Existing custom templates that extend the base template inherit the palette and shared styles.
To use the grouped form layout, wrap each `.form-grid` in a `.form-section` with a labelled
section heading. `.record-form` supplies the outer surface spacing; `.form-footer` supplies
the sticky action area. Template overrides can be compared with the built-in `form.html`.

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
