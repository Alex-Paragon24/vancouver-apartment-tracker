import os
import re
import logging
import gspread
from datetime import datetime, timezone
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from config import GOOGLE_SHEET_ID

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/gmail.compose",
]

SHEET_HEADERS = [
    "Date Found",
    "Price",
    "Address",
    "Neighborhood",
    "Walking Time to Bacchus",
    "Posted",
    "Bedrooms",
    "Available From",
    "Link",
    "Status",
    "Draft ID",
]


def _age_str(posted_ts):
    if not posted_ts:
        return ""
    delta = datetime.now(timezone.utc).timestamp() - posted_ts
    hours = int(delta // 3600)
    if hours < 1:
        return "< 1 ч."
    if hours < 24:
        return f"{hours} ч. назад"
    return f"{hours // 24} дн. назад"


def get_creds():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as f:
            f.write(creds.to_json())
    return creds


def _get_client():
    return gspread.authorize(get_creds())


def setup_sheet_formatting(worksheet):
    from gspread_formatting import (
        format_cell_range, set_frozen, set_column_width,
        CellFormat, Color, TextFormat, NumberFormat,
        ConditionalFormatRule, GridRange, BooleanRule, BooleanCondition,
        get_conditional_format_rules,
    )

    set_frozen(worksheet, rows=1)

    # Dark header row
    format_cell_range(worksheet, "1:1", CellFormat(
        backgroundColor=Color(0.204, 0.286, 0.490),
        textFormat=TextFormat(bold=True, foregroundColor=Color(1, 1, 1), fontSize=10),
    ))

    # Column widths
    for col, width in [
        ("A", 140), ("B", 95),  ("C", 230), ("D", 125),
        ("E", 145), ("F", 110), ("G", 70),  ("H", 260),
        ("H", 120), ("I", 60),  ("J", 90),  ("K", 50),
    ]:
        set_column_width(worksheet, col, width)

    # Currency format for price column
    format_cell_range(worksheet, "B2:B1000", CellFormat(
        numberFormat=NumberFormat(type="CURRENCY", pattern="$#,##0")
    ))

    # Conditional formatting
    rules = get_conditional_format_rules(worksheet)
    rules.clear()

    # Price: green ≤ 2500, yellow 2501–3000, red > 3000
    rules.append(ConditionalFormatRule(
        ranges=[GridRange.from_a1_range("B2:B1000", worksheet)],
        booleanRule=BooleanRule(
            condition=BooleanCondition("NUMBER_LESS_THAN_EQ", ["2500"]),
            format=CellFormat(backgroundColor=Color(0.714, 0.843, 0.659)),
        ),
    ))
    rules.append(ConditionalFormatRule(
        ranges=[GridRange.from_a1_range("B2:B1000", worksheet)],
        booleanRule=BooleanRule(
            condition=BooleanCondition("NUMBER_BETWEEN", ["2501", "3000"]),
            format=CellFormat(backgroundColor=Color(1.0, 0.949, 0.800)),
        ),
    ))
    rules.append(ConditionalFormatRule(
        ranges=[GridRange.from_a1_range("B2:B1000", worksheet)],
        booleanRule=BooleanRule(
            condition=BooleanCondition("NUMBER_GREATER", ["3000"]),
            format=CellFormat(backgroundColor=Color(0.957, 0.800, 0.800)),
        ),
    ))

    # Status: blue=New, green=Drafted, orange=Sent
    for text, color in [
        ("New",     Color(0.788, 0.878, 0.980)),
        ("Drafted", Color(0.714, 0.843, 0.659)),
        ("Sent",    Color(1.000, 0.800, 0.400)),
    ]:
        rules.append(ConditionalFormatRule(
            ranges=[GridRange.from_a1_range("J2:J1000", worksheet)],
            booleanRule=BooleanRule(
                condition=BooleanCondition("TEXT_EQ", [text]),
                format=CellFormat(backgroundColor=color),
            ),
        ))

    rules.save()
    logger.info("Sheet formatting applied")


def _ensure_headers(worksheet):
    first_row = worksheet.row_values(1)
    if not first_row:
        worksheet.append_row(SHEET_HEADERS, value_input_option="RAW")
        setup_sheet_formatting(worksheet)
        logger.info("Wrote sheet headers")


def get_seen_ids_from_sheet():
    """Read posting IDs already in the sheet — used as persistent dedup store."""
    try:
        gc = _get_client()
        sheet = gc.open_by_key(GOOGLE_SHEET_ID)
        links = sheet.sheet1.col_values(9)[1:]  # col 9 = Link (after adding Posted col), skip header
        ids = set()
        for link in links:
            m = re.search(r'/(\d+)\.html', link)
            if m:
                ids.add(m.group(1))
        logger.info(f"Loaded {len(ids)} seen IDs from Google Sheet")
        return ids
    except Exception as e:
        logger.warning(f"Could not load seen IDs from sheet: {e}")
        return set()


def append_to_sheet(listing):
    gc = _get_client()
    sheet = gc.open_by_key(GOOGLE_SHEET_ID)
    worksheet = sheet.sheet1

    _ensure_headers(worksheet)

    row = [
        listing.get("date_found", ""),
        listing.get("price") or "",   # numeric — currency format applied to column
        listing.get("address", ""),
        listing.get("neighborhood", ""),
        listing.get("walking_time", "N/A"),
        _age_str(listing.get("posted_ts")),
        listing.get("bedrooms", 2),
        listing.get("available_from", ""),
        listing.get("link", ""),
        "New",
    ]

    row.append("")  # Draft ID — filled later by store_draft_id()
    worksheet.append_row(row, value_input_option="USER_ENTERED")
    row_idx = len(worksheet.get_all_values())
    logger.info(f"Appended row {row_idx}: {listing.get('link', '')[:60]}")
    return row_idx


def update_row_status(row_idx, status):
    gc = _get_client()
    sheet = gc.open_by_key(GOOGLE_SHEET_ID)
    sheet.sheet1.update_cell(row_idx, 10, status)  # col J = Status
    logger.info(f"Row {row_idx} status → {status}")


def store_draft_id(row_idx, draft_id):
    gc = _get_client()
    gc.open_by_key(GOOGLE_SHEET_ID).sheet1.update_cell(row_idx, 11, draft_id)  # col K
    logger.info(f"Stored draft ID for row {row_idx}")


def get_drafted_rows():
    """Returns [(row_idx, draft_id)] for rows with status Drafted and a stored draft ID."""
    try:
        gc = _get_client()
        all_rows = gc.open_by_key(GOOGLE_SHEET_ID).sheet1.get_all_values()
        result = []
        for i, row in enumerate(all_rows[1:], start=2):  # skip header, 1-indexed
            status   = row[9]  if len(row) > 9  else ""
            draft_id = row[10] if len(row) > 10 else ""
            if status == "Drafted" and draft_id:
                result.append((i, draft_id))
        return result
    except Exception as e:
        logger.warning(f"Could not get drafted rows: {e}")
        return []
