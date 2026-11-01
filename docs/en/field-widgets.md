# Field widget extension design proposal

**Proposal only; no new widget API is implemented.** Existing `FieldOptions.template`,
`parser` and `formatter` hooks already allow application-owned field rendering and
conversion. See [extensions](extensions.md). The options below describe a possible future
API for a consistent, reusable widget mechanism across SQL reflection and ORM adapters.

| Approach | Advantages | Costs and risks |
|---|---|---|
| Extend template overrides with declared local CSS/JS assets | Smallest change; uses current Jinja context; easy for a single application | Validation and asset registration stay separate; repeated accessibility and initialization code; template context needs a stable contract |
| Named widget registry plus per-field widget name/options | Reusable widgets, explicit allowlist, automatic asset deduplication, easy defaults by field metadata | Needs a public context/schema, lifecycle and compatibility policy; config validation and default precedence become part of the API |
| Python Widget class/protocol with render/parse/assets methods | Rendering and conversion live together; easy server-side tests and composed widgets | More public Python API; risk of coupling business parsing to UI; async rendering and multi-input fields need precise rules |
| Frontend plugin or web-component registry | Suitable for rich editors, maps and code controls; can reuse frontend libraries | More JavaScript/build burden, CSP and dependency maintenance; hydration, no-script fallback and accessibility need explicit support |

## Recommended direction

Start with a **named registry**, with template-based widgets as its first implementation.
An optional Python protocol can be layered on later if composite fields require it.
Keep widget selection independent of the adapter: `Field` describes the data, collection
field settings select presentation. Match built-in defaults by logical kind plus optional
metadata such as multiline/max length; an explicit field choice takes precedence.

A future registration would conceptually associate a name with a template, validated
configuration and a manifest of local assets. This is a design sketch, not callable API.
Each field would receive a stable context: field metadata, value, name/id, label, help/error
IDs, nullable/default state and read-only state. Assets would load once on pages that use
them and contribute exact hashes to CSP. Arbitrary remote assets or inline executable
configuration should not become a shortcut around the current policy.

The first version should support one canonical submitted value per field, using existing
parser/formatter hooks. A multi-control widget would combine its values into that canonical
input; multi-field business updates should remain application/service operations until a
separate atomic parsing contract is designed. Widgets cannot grant edit rights, expose
hidden values, skip CSRF/revision checks or replace server-side validation.

Require keyboard/screen-reader behavior, translated messages, safe escaping, error/value
preservation after 422/409, explicit no-script fallback, initializer teardown and duplicate
asset handling. Integration tests should exercise a sample widget under FastAPI and Litestar,
with SQL reflection and an ORM, including read-only/hidden fields and timezone/number precision.

Keep the template context versioned separately from required adapter API version 1.
An additive registry does not need an adapter API bump; changing required adapter metadata
would. Do not ship a new extension API before settling the context and asset lifecycle.
