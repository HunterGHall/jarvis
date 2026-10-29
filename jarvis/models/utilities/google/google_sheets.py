import re
import urllib.parse

from google_auth import GoogleError, api
from google_common import approve, declined, extract_id, safe
from web_images import ImageError, check_image

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


def _cell_position(cell):
    """(tab or None, column index, row index) from a reference like 'B3' or 'Sheet1!B3'."""
    tab, _, reference = cell.rpartition("!")
    match = re.fullmatch(r"\$?([A-Za-z]{1,3})\$?(\d+)", reference.strip())
    if not match:
        raise GoogleError(f"'{cell}' isn't a single cell like B3 or Sheet1!B3.")
    column = 0
    for letter in match.group(1).upper():
        column = column * 26 + (ord(letter) - 64)
    return tab.strip("'").replace("''", "'") or None, column - 1, int(match.group(2)) - 1


def _column_letters(index):
    letters, number = "", index + 1
    while number:
        number, remainder = divmod(number - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _resize(sheet_id, dimension, index, pixels):
    return {
        "updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": dimension, "startIndex": index, "endIndex": index + 1},
            "properties": {"pixelSize": pixels},
            "fields": "pixelSize",
        }
    }


@safe
def sheets_insert_image(spreadsheet, cell, image_url, tab=None, size_px=150):
    """Shows a picture from the web inside one cell of a Google Sheet (with =IMAGE), and makes that cell big enough to see it."""
    try:
        check_image(image_url)
    except ImageError as error:
        return {"error": str(error)}
    spreadsheet_id = extract_id(spreadsheet)
    cell_tab, column, row = _cell_position(cell)
    info = api("GET", f"{BASE}/{spreadsheet_id}", params={"fields": "sheets.properties(sheetId,title)"})
    tabs = [sheet["properties"] for sheet in info.get("sheets", [])]
    wanted = cell_tab or tab or (tabs[0]["title"] if tabs else "")
    target = next((t for t in tabs if t["title"].lower() == wanted.lower()), None)
    if target is None:
        return {"error": f"There's no tab called '{wanted}'. Tabs: {', '.join(t['title'] for t in tabs)}."}

    where = f"{_column_letters(column)}{row + 1}"
    reference = f"{_quote_tab(target['title'])}!{where}"
    existing = api("GET", f"{BASE}/{spreadsheet_id}/values/{_range(reference)}").get("values", [[]])
    current = str(existing[0][0]) if existing and existing[0] else ""
    if current and not approve(
        f"Replace what's in {reference} with a picture?\n\n    Now: {current[:80]}\n",
        f"Shall I replace what's in cell {where} with a picture?",
    ):
        return declined()

    formula = '=IMAGE("' + image_url.replace('"', "%22") + '")'
    api("PUT", f"{BASE}/{spreadsheet_id}/values/{_range(reference)}", params={"valueInputOption": "USER_ENTERED"}, body={"values": [[formula]]})
    if size_px:
        pixels = max(20, min(int(size_px), 1000))
        requests = [_resize(target["sheetId"], "ROWS", row, pixels), _resize(target["sheetId"], "COLUMNS", column, pixels)]
        api("POST", f"{BASE}/{spreadsheet_id}:batchUpdate", body={"requests": requests})
    return {"inserted": True, "cell": reference, "resized_to_px": size_px or None, "link": _url(spreadsheet_id)}
