# Export table data

In **0.3.0**, open a collection list, apply search and [filters](filters.md), choose the
sort order, then expand **Export data**. Select columns, choose **CSV** or **XLSX** and
press **Download**. All matching records are exported, including other pages; pagination
settings do not limit the file. The selected columns affect only the download.

The initial selection matches the list columns. You can include other visible fields and
one-hop fields from related tables. A single related record contributes a scalar cell;
a missing relation leaves it empty. For 1:N and M:N, each cell contains one related value
per line. Related columns in the same relationship use the same record order. The export
keeps one row per source record; it does not multiply rows across collections.

This is an adapter-level join through discovered relationships, not an arbitrary SQL JOIN.
It supports all built-in relationship adapters, including composite keys. It respects
configured relationships, source/target field visibility and target list/view permissions.
Nested joins, arbitrary join conditions and filtering on related non-key columns are not
supported. Related-key filters from the listing apply to source records; they do not trim
the exported related collection. Large analytical exports should use application services.

**No ORM required:** `SQLAdapter` exports reflected SQL tables with the same column
selection, filters and formats. Foreign keys enable related columns automatically.
Custom adapters need only the normal `list` contract for scalar exports; related columns
require the optional `RelationAdapter` contract.

## Formats and safety

- CSV: UTF-8 with BOM, comma-separated and quoted with embedded newlines. Spreadsheet
  formula prefixes are escaped with an apostrophe. Import with UTF-8 and comma separator
  if the spreadsheet's locale expects a different delimiter.
- XLSX: a real Excel workbook with literal text cells, wrapped values and no formulas.
  Text preserves UUIDs, leading zeroes, Decimal precision and large integer values.
  Dates use ISO strings; NULL is empty. Numeric calculations require converting columns
  to numbers in your spreadsheet. JSON/JSONB field values remain formatted field text.

Both formats use field formatters. Export requires **list and view** permissions on the
source collection; related data also requires list/view access to its target. Hidden fields
cannot be exported by changing URL parameters. Downloads are marked `Cache-Control: no-store`.
CSV escaping changes formula-like strings intentionally; XLSX preserves them as literal text.

Exports are bounded: 10,000 source records, reduced to 1,000 when related columns are
selected; at most 1,000 records per related collection, 10,000 related records overall,
100 selected columns and 32 MiB of formatted UTF-8 data/output. XLSX cells have a 32,767
UTF-16-unit text limit. A limit violation returns HTTP 413 rather than a partial file.
Narrow filters or use CSV for very long cell values. Invalid filters return 422.

Reads can observe concurrent changes: this is not a database snapshot. Related lookups
run per source record and relationship. Export has no write side effects, and uses the
same authentication and read permissions as record browsing.

The square download icon beside search opens a compact export panel. Escape or a click
outside closes it; the panel also works without JavaScript through native disclosure.
