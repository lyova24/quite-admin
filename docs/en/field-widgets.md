# Field controls and custom widgets

Controls are selected from adapter metadata: bounded strings use single-line inputs,
TEXT uses a textarea, dates/times use the shared picker, JSON uses a local editor,
booleans use nullable-aware switches and enums use selects. See the full
[control table](configuration.md#database-type-controls), including precision and no-script behavior.

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
