"""Google Sheets actions through the tenant's own connection.

Row 1 of the tab holds the headings. A lookup returns only the rows whose
lookup column matches what the caller gave, never the rest of the sheet. Rows
are written as plain values (RAW), so caller text such as "=IMPORTXML(...)"
stays text instead of becoming a formula.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

import httpx

from server.services.integration_settings import spreadsheet_id

_MAX_ROWS = 2000
_MAX_MATCHES = 5


def _comparable(value: Any) -> str:
    text = str(value or "").strip().casefold()
    bare = re.sub(r"[\s().+-]", "", text)
    # Phone numbers are written many ways (+91 98..., 098..., 98...): compare the last 10 digits.
    if bare.isdigit() and len(bare) >= 10:
        return bare[-10:]
    return re.sub(r"\s+", " ", text)


def _range(sheet_name: str, cells: str) -> str:
    return quote("'" + sheet_name.replace("'", "''") + "'!" + cells, safe="")


async def execute_sheets_action(client: httpx.AsyncClient, base: str, headers: dict, action: str, params: dict) -> dict:
    sheet = spreadsheet_id(str(params.get("spreadsheet_id") or ""))
    tab = str(params.get("sheet_name") or "").strip()
    if not sheet or not tab:
        return {"status": "error", "message": "The Google Sheet is not set up for this workspace."}
    root = f"{base}/proxy/v4/spreadsheets/{sheet}/values"
    if action == "GOOGLESHEETS_FIND_ROWS":
        response = await client.get(f"{root}/{_range(tab, f'A1:ZZ{_MAX_ROWS}')}", headers=headers)
        response.raise_for_status()
        rows = response.json().get("values") or []
        if not rows:
            return {"status": "not_found", "matches": 0, "rows": [], "summary": "The sheet is empty."}
        headings = [str(h).strip() for h in rows[0]]
        column = str(params.get("lookup_column") or "").strip().casefold()
        index = next((i for i, h in enumerate(headings) if h.casefold() == column), None)
        if index is None:
            return {"status": "error", "message": "The lookup column is not in the sheet's first row. Check the setup."}
        wanted = _comparable(params.get("value"))
        if not wanted:
            return {"status": "error", "message": "Ask the caller for the value to look up."}
        found = [{h: (row[i] if i < len(row) else "") for i, h in enumerate(headings) if h}
                 for row in rows[1:] if index < len(row) and _comparable(row[index]) == wanted]
        return {"status": "success" if found else "not_found", "matches": len(found), "rows": found[:_MAX_MATCHES],
                "summary": f"Found {len(found)} matching row(s)." if found else "No row matches that value."}
    if action == "GOOGLESHEETS_ADD_ROW":
        values = params.get("values") if isinstance(params.get("values"), dict) else {}
        response = await client.get(f"{root}/{_range(tab, '1:1')}", headers=headers)
        response.raise_for_status()
        headings = [str(h).strip() for h in ((response.json().get("values") or [[]])[0])]
        given = {str(k).strip().casefold(): str(v) for k, v in values.items() if str(v).strip()}
        row = [given.get(h.casefold(), "") for h in headings]
        if not any(row):
            return {"status": "error", "message": "None of those details match the sheet's column headings. Nothing was added."}
        response = await client.post(
            f"{root}/{_range(tab, 'A1')}:append", headers=headers,
            params={"valueInputOption": "RAW", "insertDataOption": "INSERT_ROWS"},
            json={"majorDimension": "ROWS", "values": [row]},
        )
        response.raise_for_status()
        updated = (response.json().get("updates") or {}).get("updatedRange") or ""
        if not updated:
            return {"status": "unknown", "message": "The sheet did not confirm the new row. Check it before adding again."}
        number = re.search(r"(\d+)(?::[A-Z]+\d+)?$", updated)
        return {"status": "success", "row_number": int(number.group(1)) if number else None,
                "summary": "Row added to the Google Sheet."}
    return {"status": "error", "message": "This Google Sheets action is not supported."}
