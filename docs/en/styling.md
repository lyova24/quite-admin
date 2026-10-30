# Customize the interface

Use `Theme` for the palette, CSS tokens for proportions and density, and template
overrides for structure. These settings apply to one `Admin` instance and work with
all adapters. No frontend build is required.

## Palette and identity

```python
from quite_admin import Admin, Theme

admin = Admin(
    auth=auth_backend,
    secret_key=session_secret,
    title="Operations",
    logo="assets/company.svg",
    theme=Theme(
        primary="#345c50",
        background="#f5f6f8",
        surface="#ffffff",
        text="#20252b",
        muted="#626b76",
        border="#dce0e5",
        danger="#b43e3e",
    ),
    templates_dir="templates",
)
```

The accent identifies primary actions and selected items. `danger` identifies deletion
and errors. Boolean values remain neutral; changing the palette does not change status
semantics. `on_primary` and `on_danger` control button text. The
[complete palette reference](customization.md#colors) includes a dark example and defaults.

## Load your stylesheet

Serve a CSS file from the **same origin** as the admin. For example, in FastAPI:

```python
from starlette.staticfiles import StaticFiles

# app is your existing FastAPI application, mounted at the origin root.
app.mount("/admin-style", StaticFiles(directory="admin-style"), name="admin-style")
admin.mount_fastapi(app)
```

In Litestar, use the application's static-file router for the same public asset path.
Create `admin-style/custom.css`. To include it on every admin screen, copy the packaged
base template to your override directory once:

```python
from importlib.resources import files
from pathlib import Path

output = Path("templates/quite_admin/base.html")
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(
    files("quite_admin").joinpath("templates/quite_admin/base.html").read_text(),
    encoding="utf-8",
)
```

In that copy, replace the empty `head` block with:

```jinja
{% block head %}
<link rel="stylesheet" href="/admin-style/custom.css">
{% endblock %}
```

This loads custom CSS **after** the base stylesheet and generated `theme.css`.
Set `href` to your application's public asset URL, including a deployment/proxy prefix
when applicable. The admin's `url()` helper resolves paths inside its own mount;
it does not resolve an unrelated application asset route. Do not edit installed
package files. Keep the copied base template in sync when upgrading. A base override
cannot extend `quite_admin/base.html` itself: that would recursively load the override.
A custom page can simply extend the packaged base and add its own `head` block.

## Density, typography and surfaces

```css
/* admin-style/custom.css */
:root {
  --table-row-height: 40px; /* default 44px */
  --control-height: 36px;  /* default 38px */
  --text-title: 26px;      /* default 28px */
  --radius-control: 4px;   /* default 6px */
}

/* Keep application-specific components in the same visual system. */
.operations-summary {
  padding: var(--space-6);
  color: var(--text);
  background: var(--paper);
  border: var(--border);
  border-radius: var(--radius);
}
```

| Tokens | Role |
|---|---|
| `--text-xs`, `--text-sm`, `--text-base`, `--text-section`, `--text-title` | 12 / 13 / 14 / 16 / 28 px typography |
| `--space-1` … `--space-6`, `--space-8`, `--space-10` | 4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 px spacing |
| `--radius-sm`, `--radius-control`, `--radius` | 4 / 6 / 8 px corners |
| `--bg`, `--paper`, `--subtle`, `--hover` | Page, main surface, inset and hover surface |
| `--text`, `--muted`, `--line`, `--border` | Text, secondary text and separators |
| `--accent`, `--accent-soft`, `--accent-border`, `--on-accent` | Actions and selection |
| `--danger`, `--danger-soft`, `--danger-border`, `--on-danger` | Destructive actions and errors |

Keep the system font stack unless the application needs another readable local font.
Tables retain numeric alignment and horizontal scrolling on narrow screens. Prefer
changes through tokens over selectors targeting individual rows or generated labels.

## Templates and field labels

`ModelOptions(label=...)` names collections. `FieldOptions(label=..., help_text=...)`
changes field labels and hints without replacing HTML. A field-specific `template`
can customize its control; see [field extensions](extensions.md).

Custom screens can reuse `.page-heading`, `.panel`, `.form-section`, `.form-grid`,
`.form-footer`, `.record-list` and `.button.primary` / `.button.secondary`.
Use a panel for an independent block and sections for groups within a form.
See [custom pages and overrides](custom-pages.md) for registration.

Keep `__csrf`, `__revision`, `form_action`, field names, read-only rendering, errors,
labels and `aria-describedby` when overriding forms. Keep the base template's `scripts`
loop for built-in filter editors, relationship pickers and the schema viewer.
Stylesheets must remain same-origin: CSP
blocks inline styles and external CDNs. Custom JavaScript is not enabled by CSS or
template overrides. Built-in interactive components receive only their exact script hashes.

After changing the theme, check a list with active filters, a long edit form, validation
and stale-edit errors, a read-only record, the database schema and a narrow viewport.
Verify text contrast,
keyboard focus and that the sticky form footer leaves the final fields reachable.
