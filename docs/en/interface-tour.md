# Interface tour

The screenshots show the local Python example with fictional records and the default charcoal-and-blue palette. Open the
[browser demo](https://lyova24.github.io/quite-admin/demo/) with `admin` / `admin`.
Use **Reset demo** for the initial fictional records. See [demo coverage](browser-demo.md)
for the features that need the Python application.

Select any screenshot to view it at full size.

## Sign in and navigate

The compact sign-in card places the logo beside the application title.
Custom logos use the same alignment.

[![Sign-in card with the logo beside the title](../assets/screenshots/login.png)](../assets/screenshots/login.png)

**Home** shows the configured admin logo, title and description. It also brings together
pinned and recently opened tables, plus shortcuts to the schema, activity history and
custom pages. Opening Home uses authorized metadata without scanning table records.

Home cards use three equal-width columns on desktop. One or two cards keep the
same width instead of filling the row. Tablet screens use two columns and narrow
screens use one.

Choose **Find a table** or press **Ctrl/⌘ K** on any authenticated page. The search
opens with its input focused and matches table labels, technical names and groups.
Use arrows and Enter to open a result; Escape closes search and returns focus.
The SVG star beside each search result or beside a table's record-list heading
adds it to the pinned tables on Home. Its filled state stays synchronized between
search, the record list and Home; select it again to unpin. Up to 12 pinned and 8 recent table identifiers are
stored per user and admin mount in this browser; permissions are checked again
on every page. Search terms and record data are not stored.

Use the × button on a recently opened table to remove it from that list. This
leaves its pinned state unchanged. Opening the table again adds it back to recent tables.

If you cannot remember a name, expand **All tables** on Home and browse the full
catalog by group. Each link shows its label and technical name. This catalog also
works with native keyboard navigation and without JavaScript.

The left navigation is a permanent **3.5 rem icon rail** for Home, Database schema,
Activity history and custom pages. It has no expandable table panel or resize handle.
The avatar stays at the bottom: click it to open your name and **Sign out** to its right.
On authenticated pages other than Home, the header shows the admin logo and title
on the right. Breadcrumbs use the plain text **Home** link and the current table
or record for context. Home keeps its branding in the main content.

## Edit without leaving the list

Open **Products**, click the pencil beside **Price**, enter `19.50` and **Save changes**.
The cell updates in place. **Cancel** or Escape discards an unsaved value. The **Active**
switch saves immediately. Open **Schedules** to try a nullable **Approved** switch;
∅ sets it to NULL, distinct from false. Open a full record by its Id/row link.

[![Inline edit in the Products list](../assets/screenshots/inline-edit.png)](../assets/screenshots/inline-edit.png)

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

[![Schedule form with a compact calendar and direct time fields](../assets/screenshots/date-time-form.png)](../assets/screenshots/date-time-form.png)

**Description** demonstrates a full-width TEXT textarea. Below it, **Settings** has JSON
highlighting, syntax feedback and **Format JSON**. Edit valid JSON and save; invalid JSON
cannot be persisted. **Approved** explicitly distinguishes NULL from true/false.

[![JSON editor with formatting and syntax status](../assets/screenshots/json-editor.png)](../assets/screenshots/json-editor.png)

In the Schedules list, choose **+ Add filter → Day → Between** for a two-endpoint calendar.
DATETIME/TIME ranges include time. Filter Apply/Cancel operates on a draft; record calendars
update their form field immediately. Details are in [field controls](configuration.md)
and [list filters](filters.md).

## Find who changed a value

Open **Activity history**. The default **Journal** groups events by day and shows field
names with **Before / After** values. Your price and boolean changes appear alongside
clearly identified fictional sample events. Expand one event or **Expand all changes**.

[![Activity journal with field comparisons](../assets/screenshots/activity-history.png)](../assets/screenshots/activity-history.png)

Choose **+ Add filter → User** and select Demo Admin or Olivia Chen. Add **Table**,
**Action** or **Result** through the same editor as list filters. The period sits in the
same toolbar: use a quick preset, a **Specific day**, or a **Date range**. Both range
endpoints include the entire UTC day. Switching to **Table** preserves these selections.

[![History period with two inclusive UTC calendars](../assets/screenshots/activity-period.png)](../assets/screenshots/activity-period.png)

The Python application records committed record changes automatically with
`history_level="changes"`. Choose `"audit"` to include authentication, exports and failed
writes, or `"all"` for reads too. Its default SQLite file needs a persistent writable
directory; SQLite/PostgreSQL/MySQL storage is configurable.
`Admin(history_enabled=False, ...)` disables the feature. Read
[storage and history](storage.md) for permissions, redaction, backups and durability limits.

## Navigate and export

On Home, expand **All tables**, then a group to browse its tables. Explicit group
choices are remembered for your user and admin mount in this browser. **Orders** illustrates cursor-style paging; its
real ASGI counterpart uses database keysets and signed cursors without exact counts.

In **Products**, apply a filter, open **Export data**, select columns and download CSV.
It contains all matches, including other pages. Use the local ASGI example for **XLSX**
and related columns such as Tags → Name; [exports](exports.md) documents limits and batching.

Finally, change a product's tags on its record page and explore **Database schema**:
expand fields, toggle **N:M** to reveal `product_tags`, and move a table. **Auto layout**
releases the fixed positions. Both the [relationship editor](relationships.md) and
[schema](database-schema.md) show the same registered tables and relationships.

[![Database schema with the expanded product_tags junction](../assets/screenshots/database-schema.png)](../assets/screenshots/database-schema.png)

The schema fills the available height below the header. Its wider table picker
keeps long names readable and scrolls on short screens. Schemas with more than
100 permitted tables still start with manual selection; the layout does not enable
all tables automatically. See [schema selection](database-schema.md#initial-selection-for-large-databases).
