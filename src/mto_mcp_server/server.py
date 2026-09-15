"""MCP server entry point. Exposes exactly two tools:

  diff_mto_scsa   - read-only preview of the 3-way diff
  apply_mto_update - re-derives the diff and (optionally) writes it

Run with: mto-mcp-server   (after `pip install -e .`)
or:       python -m mto_mcp_server.server
"""
from typing import Optional

from mcp.server.fastmcp import FastMCP

from .apply import apply_mto_update as _apply_mto_update
from .diff import diff_mto_scsa as _diff_mto_scsa

mcp = FastMCP("mto-reconciliation")


@mcp.tool()
def diff_mto_scsa(mto_path: str, scsa_path: str, category: Optional[str] = None) -> dict:
    """Compare an MTO file against a Plant 3D SCSA export.

    Read-only - never writes anything. Returns counts and item lists for
    the 3 scenarios: qty_mismatch, removed (in MTO, not in SCSA anymore),
    new (in SCSA, not yet in MTO). Items with matching qty in both are
    counted in summary.matched but not listed individually.

    Args:
        mto_path: path to the MTO .xlsx file.
        scsa_path: path to the SCSA .xlsx export.
        category: optional filter - one of pipe/elbow/tee/reducer/flange/
            valve/blind_flange/gasket/stud_bolt/bolt/nut/washer/
            gate_valve/safety_valve/ball_valve/steam_trap/pipe_support/
            insulation/structural_steel. Omit to diff everything.
    """
    return _diff_mto_scsa(mto_path, scsa_path, category=category)


@mcp.tool()
def apply_mto_update(
    mto_path: str,
    scsa_path: str,
    category: Optional[str] = None,
    include_removals: bool = False,
    dry_run: bool = False,
    output_path: Optional[str] = None,
) -> dict:
    """Write the MTO/SCSA reconciliation into the MTO file.

    Always re-derives the diff from the two paths (never trust a
    caller-supplied diff blob). Quantity corrections and new items are
    applied whenever dry_run=False - they're additive/corrective, not
    destructive. Removals (zeroing a quantity because the item left the
    project) are ONLY written when include_removals=True as well.

    Recommended flow: call with dry_run=True first to preview writes,
    then call again with dry_run=False, and include_removals=True only
    once you've reviewed the removed list.

    Args:
        mto_path: path to the MTO .xlsx file to update.
        scsa_path: path to the SCSA .xlsx export (source of truth).
        category: optional category filter, same as diff_mto_scsa.
        include_removals: if True, zero out items no longer in SCSA.
        dry_run: if True, compute and report but write nothing.
        output_path: write to a different file instead of overwriting
            mto_path. Defaults to overwriting mto_path in place.
    """
    return _apply_mto_update(
        mto_path,
        scsa_path,
        category=category,
        include_removals=include_removals,
        dry_run=dry_run,
        output_path=output_path,
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
