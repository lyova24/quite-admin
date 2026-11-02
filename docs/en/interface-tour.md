# Interface tour: 0.5

This tour covers **0.5.0**. Open the
[browser demo](https://lyova24.github.io/quite-admin/demo/) with `admin` / `admin`.
Use **Reset demo** for the initial fictional records. See [demo coverage](browser-demo.md)
for the features that need the Python application.

## Edit without leaving the list

Open **Products**, click the pencil beside **Price**, enter `19.50` and **Save changes**.
The cell updates in place. **Cancel** or Escape discards an unsaved value. The **Active**
switch saves immediately. Open **Schedules** to try a nullable **Approved** switch;
∅ sets it to NULL, distinct from false. Open a full record by its Id/row link.

![Inline edit in the Products list](../assets/screenshots/inline-edit.png)

These use the same field controls as record forms. Concurrent changes are checked before
saving. To try a conflict, open the same record in two tabs, save one, then submit the other.
The second form retains its draft and offers **Reload record**.
[Configuration](configuration.md) explains `list_editable`, field policies and revisions.

## Dates, time and structured data

Open **Schedules → Catalog launch**. **Day** is DATE; **Starts At** combines date and time;
**Reminder At** is optional TIME. Open a calendar, select a day, then save the record.
There is no extra calendar Apply step in forms. **More options** reveals the original
six fractional digits and an optional UTC offset; opening the form preserves precision.
The example's SQLite columns use naive local values, without a timezone.

![Schedule form with a compact calendar and direct time fields](../assets/screenshots/date-time-form.png)

**Description** demonstrates a full-width TEXT textarea. Below it, **Settings** has JSON
highlighting, syntax feedback and **Format JSON**. Edit valid JSON and save; invalid JSON
cannot be persisted. **Approved** explicitly distinguishes NULL from true/false.

![JSON editor with formatting and syntax status](../assets/screenshots/json-editor.png)

In the Schedules list, choose **+ Add filter → Day → Between** for a two-endpoint calendar.
DATETIME/TIME ranges include time. Filter Apply/Cancel operates on a draft; record calendars
update their form field immediately. Details are in [field controls](configuration.md)
and [list filters](filters.md).

## Find who changed a value

Open **Activity history**. The default **Journal** groups events by day and shows field
names with **Before / After** values. Your price and boolean changes appear alongside
clearly identified fictional sample events. Expand one event or **Expand all changes**.

![Activity journal with field comparisons](../assets/screenshots/activity-history.png)

Choose **+ Add filter → User** and select Demo Admin or Olivia Chen. Add **Collection**,
**Action** or **Result** through the same editor as list filters. The period sits in the
same toolbar: use a quick preset, a **Specific day**, or a **Date range**. Both range
endpoints include the entire UTC day. Switching to **Table** preserves these selections.

![History period with two inclusive UTC calendars](../assets/screenshots/activity-period.png)

The Python application records authenticated activity automatically, with no application
migration. It defaults to its own SQLite file; another SQLite/PostgreSQL/MySQL store is
optional. `Admin(history_enabled=False, ...)` disables the feature. Read
[storage and history](storage.md) for permissions, redaction, backups and durability limits.

## Navigate and export

Collapse a sidebar group and navigate elsewhere: its state is remembered. The current
collection's group opens automatically. **Orders** illustrates cursor-style paging; its
real ASGI counterpart uses database keysets and signed cursors without exact counts.

In **Products**, apply a filter, open **Export data**, select columns and download CSV.
It contains all matches, including other pages. Use the local ASGI example for **XLSX**
and related columns such as Tags → Name; [exports](exports.md) documents limits and batching.

Finally, change a product's tags on its record page and explore **Database schema**:
expand fields, toggle **N:M** to reveal `product_tags`, and move a table. **Auto layout**
releases the fixed positions. Both the [relationship editor](relationships.md) and
[schema](database-schema.md) remain available alongside the new screens.
