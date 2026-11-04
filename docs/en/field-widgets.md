# Field controls and custom widgets

Controls are selected from adapter metadata: bounded strings use single-line inputs,
TEXT uses a textarea, dates/times use the shared picker, JSON uses a local editor,
booleans use nullable-aware switches and enums use selects. See the full
[control table](configuration.md#database-type-controls), including precision and no-script behavior.

## Built-in value displays

Choose a display without changing the database type or adding a template:

```python
admin.configure("links", options=ModelOptions(fields={
    "long_url": FieldOptions(display="url"),
    "hash": FieldOptions(url_template="https://short.example/{value}"),
    "metadata": FieldOptions(display="json"),
    "description": FieldOptions(display="multiline"),
}))
```

| Option | Behavior |
|---|---|
| `display=None` or `"text"` | Existing plain display; default |
| `display="url"` | Open an absolute HTTP(S) URL and copy the displayed value |
| `url_template="https://short.example/{value}"` | Build a URL for display; implies `display="url"` |
| `display="json"` | Format valid JSON with indentation; invalid text remains escaped text |
| `display="multiline"` | Preserve line breaks and reveal long values in lists |

These controls apply to list cells and read-only fields on record pages. JSON/long
text expands with native details controls; record pages show the full text. Writable
URL fields also show a link/copy preview beside their normal input. Explicit rich
displays use the full record editor rather than inline editing; ordinary displayed
columns retain their existing inline behavior. Service changes to rich fields refresh
those cells after another column is saved inline.

`url_template` accepts only `{value}` placeholders in an absolute HTTP(S) URL. The
formatted scalar value is URL-encoded as one component, so `abc/123` becomes `abc%2F123`.
It changes only presentation: forms, persistence, filtering, sorting, exports and
history keep their original value. An existing `formatter` continues to affect its
usual surfaces; URL display can also use its output. No other record fields or Python
expressions are evaluated by URL templates. Use `display="url"` or leave `display`
unset with `url_template`; other combinations are configuration errors.

Links allow only absolute HTTP(S) addresses, open with `noopener noreferrer` and
remain escaped. Relative/unsafe addresses are displayed as text. JSON/text is never
interpreted as HTML. Copying uses the browser clipboard API; when unavailable, the
value is selected for manual copying. Links and disclosure work without JavaScript;
copy buttons appear only after the built-in script loads. Values are not stored in
browser storage or sent to external services. Existing visibility, password and
read-only restrictions still apply. The built-in script follows the normal CSP/SRI
policy and needs no application asset registration.

## Choose a supported extension

| Need | Configuration |
|---|---|
| Change a label, hint or read-only state | `FieldOptions(label=..., help_text=..., read_only=True)` |
| Parse or format an application value | `FieldOptions(parser=..., formatter=...)` |
| Render a custom input | `FieldOptions(template="counter.html")` and `Admin(templates_dir="templates")` |
| Collect a password or other value absent from the model | `ModelOptions(input_fields=(Field(...),))` and a [write handler](extensions.md) |
| Validate a form with Pydantic 2 | `create_schema` / `update_schema` and the `pydantic` extra |
| Change layout and colors | [Theme, same-origin CSS and template overrides](styling.md) |

There is no named widget registry or automatic registration of custom JavaScript assets.
Use the supported hooks below; custom templates retain the existing CSP.

## Render and parse a custom input

For an integer displayed as `#7`, configure the field on its collection:

```python
from quite_admin import FieldOptions, ModelOptions

admin.configure("products", options=ModelOptions(fields={
    "stock": FieldOptions(
        label="Stock", help_text="Use # followed by a whole number",
        parser=lambda raw: int(raw.removeprefix("#")),
        formatter=lambda value: "#" + str(value),
        template="counter.html",
    ),
}))
```

Create `templates/counter.html` in the configured `templates_dir`:

```jinja
{% set described_by %}{% if help and help.help_text %}help-{{ field.name }} {% endif %}{% if errors.get(field.name) %}error-{{ field.name }}{% endif %}{% endset %}
<input id="field-{{ field.name }}" name="{{ field.name }}" type="text"
       value="{{ values.get(field.name, '') }}"
       aria-invalid="{{ 'true' if errors.get(field.name) else 'false' }}"
       {% if described_by|trim %}aria-describedby="{{ described_by|trim }}"{% endif %}>
```

The surrounding form supplies the label, hint, error message, CSRF and revision token.
The include receives `field`, `help`, `values`, `errors`, `editable` and shared template
context. Keep autoescaping, submit one canonical value under `field.name` and preserve
keyboard operation. A parser returns a native value or raises `ValueError`; its message
appears as a field error. A formatter returns display text, which templates escape.

Custom templates apply only to writable form fields. Fields with a custom template use
the full record page rather than inline cell editing. Neither the template nor the parser
can grant write access to hidden/read-only fields or override adapter constraints.

## Password and form-only values

Use `Field("password", kind="password")` in `input_fields` for credentials, with a
handler that validates/hashes them and saves real model columns. Password controls
remain blank after errors and take precedence over custom field templates. Form-only
values are excluded from lists, search, exports, revisions and activity details.
See [form-only inputs](configuration.md#form-only-input-fields) for the complete contract.

For whole-form validation, schemas run after permissions, CSRF and scalar parsing,
before hooks and persistence. They do not generate additional controls. Use optional
fields in an update schema when accepting partial/inline changes; see
[services and form schemas](extensions.md#per-model-services-and-form-schemas).
