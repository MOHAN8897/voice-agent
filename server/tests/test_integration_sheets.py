import json

import httpx
import pytest

from server.services.integration_settings import clean_settings, spreadsheet_id
from server.services.integration_sheets import execute_sheets_action

SHEET = "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"
ROWS = [["Name", "Phone", "Order ID", "Status"],
        ["Asha", "+91 98765 43210", "A-1", "Shipped"],
        ["Ravi", "9123456789", "A-2", "Pending"]]


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_lookup_returns_only_the_callers_row_and_matches_phone_formats():
    def handler(request):
        return httpx.Response(200, json={"values": ROWS})

    params = {"spreadsheet_id": SHEET, "sheet_name": "Orders", "lookup_column": "phone", "value": "09876543210"}
    async with _client(handler) as client:
        result = await execute_sheets_action(client, "http://nango", {}, "GOOGLESHEETS_FIND_ROWS", params)
    assert result["status"] == "success" and result["matches"] == 1
    assert result["rows"] == [{"Name": "Asha", "Phone": "+91 98765 43210", "Order ID": "A-1", "Status": "Shipped"}]


@pytest.mark.asyncio
async def test_lookup_reports_a_missing_heading_and_no_match():
    async with _client(lambda r: httpx.Response(200, json={"values": ROWS})) as client:
        missing = await execute_sheets_action(client, "http://nango", {}, "GOOGLESHEETS_FIND_ROWS",
                                              {"spreadsheet_id": SHEET, "sheet_name": "Orders", "lookup_column": "Email", "value": "x"})
        none = await execute_sheets_action(client, "http://nango", {}, "GOOGLESHEETS_FIND_ROWS",
                                           {"spreadsheet_id": SHEET, "sheet_name": "Orders", "lookup_column": "Order ID", "value": "A-9"})
    assert missing["status"] == "error"
    assert none["status"] == "not_found" and none["rows"] == []


@pytest.mark.asyncio
async def test_add_row_follows_the_headings_and_never_writes_formulas():
    sent = {}

    def handler(request):
        if request.method == "GET":
            assert "%27Orders%27%211%3A1" in str(request.url)
            return httpx.Response(200, json={"values": [ROWS[0]]})
        sent.update(params=dict(request.url.params), body=json.loads(request.content))
        return httpx.Response(200, json={"updates": {"updatedRange": "Orders!A4:D4"}})

    values = {"name": "Neha", "PHONE": "9000000000", "Status": "=IMPORTXML(\"http://x\")", "Unknown": "dropped"}
    async with _client(handler) as client:
        result = await execute_sheets_action(client, "http://nango", {}, "GOOGLESHEETS_ADD_ROW",
                                             {"spreadsheet_id": SHEET, "sheet_name": "Orders", "values": values})
    assert result == {"status": "success", "row_number": 4, "summary": "Row added to the Google Sheet."}
    assert sent["params"]["valueInputOption"] == "RAW"
    assert sent["body"]["values"] == [["Neha", "9000000000", "", "=IMPORTXML(\"http://x\")"]]


@pytest.mark.asyncio
async def test_add_row_with_no_matching_heading_adds_nothing():
    calls = []

    def handler(request):
        calls.append(request.method)
        return httpx.Response(200, json={"values": [ROWS[0]]})

    async with _client(handler) as client:
        result = await execute_sheets_action(client, "http://nango", {}, "GOOGLESHEETS_ADD_ROW",
                                             {"spreadsheet_id": SHEET, "sheet_name": "Orders", "values": {"Colour": "red"}})
    assert result["status"] == "error" and calls == ["GET"]


def test_spreadsheet_link_is_reduced_to_its_id():
    link = f"https://docs.google.com/spreadsheets/d/{SHEET}/edit#gid=0"
    assert spreadsheet_id(link) == SHEET
    assert clean_settings("GOOGLESHEETS", {"spreadsheet_id": link, "sheet_name": "Orders"})["spreadsheet_id"] == SHEET
    with pytest.raises(ValueError):
        clean_settings("GOOGLESHEETS", {"spreadsheet_id": "https://example.com/not-a-sheet"})
