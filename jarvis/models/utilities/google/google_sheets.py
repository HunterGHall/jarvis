import urllib.parse

from google_auth import api
from google_common import approve, declined, extract_id, safe

BASE = "https://sheets.googleapis.com/v4/spreadsheets"
MAX_ROWS = 200


def _url(spreadsheet_id):
    return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"


def _range(text):
    return urllib.parse.quote(text, safe="")


def _first_tab(spreadsheet_id):
    info = api("GET", f"{BASE}/{spreadsheet_id}", params={"fields": "properties.title,sheets.properties(title,gridProperties)"})
    tabs = [
        {"name": sheet["properties"]["title"], "rows": sheet["properties"].get("gridProperties", {}).get("rowCount"), "columns": sheet["properties"].get("gridProperties", {}).get("columnCount")}
        for sheet in info.get("sheets", [])
    ]
    return info["properties"]["title"], tabs


def _quote_tab(name):
    return "'" + name.replace("'", "''") + "'"


@safe
def sheets_read(spreadsheet, range=None):
    """Reads cells from a Google Sheet. Without a range, lists the tabs and shows the top of the first one."""
    spreadsheet_id = extract_id(spreadsheet)
    result = {"id": spreadsheet_id, "link": _url(spreadsheet_id)}
    if not range:
        title, tabs = _first_tab(spreadsheet_id)
        result.update({"title": title, "tabs": tabs})
        range = f"{_quote_tab(tabs[0]['name'])}!A1:Z50" if tabs else "A1:Z50"
    reply = api("GET", f"{BASE}/{spreadsheet_id}/values/{_range(range)}", params={"valueRenderOption": "FORMATTED_VALUE"})
    rows = reply.get("values", [])
    result.update({"range": reply.get("range", range), "row_count": len(rows), "values": rows[:MAX_ROWS]})
    if len(rows) > MAX_ROWS:
        result["truncated"] = f"Showing the first {MAX_ROWS} of {len(rows)} rows. Ask for a narrower range to see the rest."
    return result


@safe
def sheets_create(title, rows=None):
    """Creates a new Google Sheet, optionally filled from `rows` (a list of rows, each a list of cells)."""
    created = api("POST", BASE, body={"properties": {"title": title}})
    spreadsheet_id = created["spreadsheetId"]
    if rows:
        api("PUT", f"{BASE}/{spreadsheet_id}/values/A1", params={"valueInputOption": "USER_ENTERED"}, body={"values": rows})
    return {"created": True, "title": title, "id": spreadsheet_id, "link": _url(spreadsheet_id)}


@safe
def sheets_append_rows(spreadsheet, rows, tab=None):
    """Adds rows under the existing data in a Google Sheet (in the first tab unless `tab` names one)."""
    spreadsheet_id = extract_id(spreadsheet)
    if not tab:
        _, tabs = _first_tab(spreadsheet_id)
        tab = tabs[0]["name"] if tabs else "Sheet1"
    reply = api(
        "POST", f"{BASE}/{spreadsheet_id}/values/{_range(_quote_tab(tab))}:append",
        params={"valueInputOption": "USER_ENTERED", "insertDataOption": "INSERT_ROWS"}, body={"values": rows},
    )
    return {"appended_rows": len(rows), "range": reply.get("updates", {}).get("updatedRange"), "link": _url(spreadsheet_id)}


@safe
def sheets_update_range(spreadsheet, range, values):
    """Overwrites a block of cells (like 'Sheet1!A1:C3') with `values`, after the user approves."""
    spreadsheet_id = extract_id(spreadsheet)
    cells = sum(len(row) for row in values)
    preview = "\n".join("    " + " | ".join(str(cell) for cell in row[:6]) for row in values[:4])
    if not approve(
        f"Overwrite {cells} cell{'s' if cells != 1 else ''} in {range}?\n\n{preview}\n",
        f"Shall I overwrite {cells} cell{'s' if cells != 1 else ''} in {range}?",
    ):
        return declined()
    reply = api("PUT", f"{BASE}/{spreadsheet_id}/values/{_range(range)}", params={"valueInputOption": "USER_ENTERED"}, body={"values": values})
    return {"updated_cells": reply.get("updatedCells"), "range": reply.get("updatedRange"), "link": _url(spreadsheet_id)}
