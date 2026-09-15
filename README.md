# mto-mcp-server

An MCP server that reconciles a piping MTO (Material Take-Off) against a
Plant 3D SCSA export, for industrial EPC projects.

## The problem

MTOs drift out of sync with the model as a piping design evolves. Bringing
one back in line is a recurring, mechanical-but-error-prone task: diff two
Excel exports with different shapes, decide what changed, update quantities,
add new items, and — carefully — remove items that dropped out of the
design. Doing this by hand across hundreds of rows and 8 piping categories
(pipes, elbows, tees, reducers, flanges, valves, blind flanges, gaskets) is
slow and easy to get subtly wrong.

## Why MCP instead of a script

The reconciliation logic itself could be a plain script. What makes this an
agent tool rather than a script is the **shape of the two calls**:

- `diff_mto_scsa` only ever computes and reports. It's built so an LLM can
  call it, read the result, and reason about it in natural language — "SCSA
  shows 4 of these, MTO has 3, want me to bump it?" — before anything is
  written.
- `apply_mto_update` is split into a safe path (quantity corrections, new
  items — additive/corrective) and a gated path (removals — zeroing a
  quantity because the item left the design, which is destructive). The gate
  is two independent flags, `dry_run` and `include_removals`, not a single
  "confirm" toggle, so an agent (or a human driving it) can preview
  everything with `dry_run=True`, apply the safe part, and only zero items
  out once `include_removals=True` is passed explicitly and deliberately.

That two-tool shape — compute-and-explain, then gated-write — is the actual
point of the project: it's the difference between "a script that mutates
your MTO" and "a tool an agent can be trusted to drive."

## Scope

This project demonstrates the reconciliation logic end-to-end against
real elbow (Отвод) data — the two tools, the 3 scenarios, and the
confirm-gate on removals are all built and tested against real MTO/SCSA
files. Category-specific matching for other categories (valve check-type
synonyms, reducer family+OD-pair+line) exists as draft code in
`matching.py` but is intentionally not wired in — see "Known limitations"
below. Everything not elbow-specific (normalization, the diff/apply split,
the write logic) is category-agnostic and applies to any category once its
match key is validated.

## Built on prior work

The core normalization and categorization logic is ported, not
rewritten, from
[rustam-zarifov/mto-scsa-reconciliation](https://github.com/rustam-zarifov/mto-scsa-reconciliation) —
a 6-script toolkit built from real EPC piping reconciliation work, covering
all 7 major categories with a color-coded Excel report as output. That
toolkit's raw-file assumptions (a 26-column `master_mto.xlsm` with section
headers, feeding an intermediate `MTO_Lookup_Table`; a header-named SCSA
export) don't match the simpler raw exports this project was tested
against, so the I/O layer (`io_excel.py`) here is new. What's ported:

- `normalize.py`'s `classify_category()` — the keyword-based category
  rules, straight from that project's `categorize()` (now covering
  fasteners, insulation, and structural steel too, not just the 8 piping
  categories, since the keyword list came over wholesale).
- `normalize.py`'s Cyrillic х/Latin x unification, from that project's
  `norm()`.
- `domain_addons.py` — GOST year-format normalization, line-code recovery,
  OD→DN lookup, and pipe-segment splitting, ported in full from
  `4_normalization_addons.py`. **Not wired into matching yet** — elbows
  don't hit any of these cases; they're here for when gasket/pipe/flange
  matching gets built out.
- `apply.py`'s `_redistribute_group()` — proportional redistribution
  across multiple MTO rows sharing one match key, from that project's
  `5_apply_fixes.py`, replacing an earlier "dump into one row, zero the
  rest" approach.

One thing that did **not** port: that project's match key is
`(name, material)`, using a `Материал` column present on both sides of its
pipeline. This project's raw MTO export has no comparable material column
(only a line code, which turned out to be unreliable — see below), so the
match key here stays name-only until that gap is closed.

## The 3 scenarios

| Scenario | Condition | Action |
|---|---|---|
| Qty mismatch | item in both, quantities differ (either direction) | update MTO qty to match SCSA |
| Removed | item in MTO, no longer in SCSA | zero the MTO qty (gated, see above) |
| New | item in SCSA, not yet in MTO | insert into MTO with SCSA's qty |

Items with matching quantities in both files produce no diff entry (counted
in `summary.matched` only) — this is checked directly in the test suite, not
assumed.

## Install

```bash
pip install -e .
```

Requires `mcp>=1.9.0,<2.0.0`. Note: `pip install "mcp[cli]"` on its own
pulls the 2.x line, which drags in a much heavier dependency set
(opentelemetry, jsonschema, pyjwt>=2.10) that isn't needed for a local
stdio server. This project pins `<2.0.0` deliberately.

## Run

```bash
mto-mcp-server
```

or point a Claude Desktop / Claude Code MCP config at
`python -m mto_mcp_server.server`.

## Tools

### `diff_mto_scsa(mto_path, scsa_path, category=None)`

Read-only. Returns:

```json
{
  "summary": {"matched": 1, "qty_mismatch": 2, "removed": 2, "new": 2},
  "qty_mismatch": [{"name": "...", "line": "...", "mto_qty": 3, "scsa_qty": 4, ...}],
  "removed":      [{"name": "...", "mto_qty": 1, ...}],
  "new":          [{"name": "...", "scsa_qty": 1, ...}]
}
```

`category` optionally restricts to one of the categories `classify_category()`
produces — the 8 piping categories (`pipe`, `elbow`, `tee`, `reducer`,
`flange`, `valve`, `blind_flange`, `gasket`) plus the extra buckets that
came along with the ported keyword rules (`stud_bolt`, `bolt`, `nut`,
`washer`, `gate_valve`, `safety_valve`, `ball_valve`, `steam_trap`,
`pipe_support`, `insulation`, `structural_steel`). Omit it to diff
everything.

### `apply_mto_update(mto_path, scsa_path, category=None, include_removals=False, dry_run=False, output_path=None)`

Re-derives the diff internally from `mto_path`/`scsa_path` every call —
it does **not** accept a pre-computed diff object from the caller. That
keeps the tool safe against a stale or hand-edited diff being replayed,
and keeps `diff_mto_scsa` a true preview with no side effects to trust.

- `dry_run=True` → compute and report, write nothing.
- `dry_run=False, include_removals=False` (default) → applies qty fixes
  and inserts; removals are reported but not written.
- `dry_run=False, include_removals=True` → also zeroes removed items.
- `output_path` → write to a different file instead of overwriting
  `mto_path` in place.

## Matching design

- **Normalization**: strips `°`, a trailing `?`, collapses whitespace, and
  unifies Cyrillic "х" / Latin "x" (a real bug source in dimension strings
  like "160x5") before any comparison.
- **Default match key is name-only, not name+line.** In the real SCSA
  export, line-code columns are populated for some standards (GOST) and
  empty for others (ASME) — see `tests/fixtures/scsa_test.xlsx`. Requiring
  line in the key would silently drop real matches. Line is still carried
  through on every diff entry as display metadata.
- **Valves and reducers**: the spec calls for check-type valve synonym
  folding (`Обратный клапан` = `Обратный затвор`) and family+OD-pair+line
  matching for reducers, but there was no real valve or reducer data
  available to validate either against — only elbow data was available.
  Both key functions exist as drafts in `matching.py`
  (`valve_key`, `reducer_key`) but are **not wired in** — see the
  `_KEY_FUNCS` comment. Both categories currently fall through to the
  name-only default key. Wiring either back in is a one-line change once
  there's real data to check it against.
- **GOST/ASME cross-referencing** falls out of the name-only key for free —
  the standard field is read but deliberately excluded from the key.

## Testing

`tests/test_diff.py` runs against real (small) MTO/SCSA export pairs in
`tests/fixtures/`, not synthetic data. Expected values were derived by
hand-tracing the fixture files first, then asserted — not read off the
code's own output. Covers: exact-match (no false flag), qty mismatch in
both directions, removed items, new items, dry-run (no write), apply
without removals (removed items untouched), apply with removals (zeroed),
and new-item insertion (qty + next POZ number).

```bash
pip install pytest
pytest tests/ -v
```

## Known limitations / next steps

- Category-specific matching (valve check-type synonyms, reducer
  family+OD-pair+line) is drafted but not validated against real data —
  see above. Demo and tests currently cover elbow reconciliation only.
- The match key is name-only, not `(name, material)` like the ported
  toolkit's proven engine — this project's raw MTO export doesn't expose
  a comparable material field yet. See "Built on prior work" above.
- `domain_addons.py` is ported but not wired into any matching path yet.
- Column positions in `io_excel.py` (`MTO_COLUMNS`, `SCSA_COLUMNS`) are
  verified against the two fixture files only; a different SCSA export
  layout would need the indices adjusted.
