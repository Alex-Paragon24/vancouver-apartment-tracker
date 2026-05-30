import os
import logging
import gspread
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from config import GOOGLE_SHEET_ID

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]

SHEET_HEADERS = [
    "Date Found",
    "Price",
    "Address",
    "Neighborhood",
    "Walking Time to Bacchus",
    "Bedrooms",
    "Amenities",
    "Link",
    "Status",
]


def _get_client():
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

    return gspread.authorize(creds)


def _ensure_headers(worksheet):
    first_row = worksheet.row_values(1)
    if not first_row:
        worksheet.append_row(SHEET_HEADERS, value_input_option="RAW")
        logger.info("Wrote sheet headers")


def append_to_sheet(listing):
    gc = _get_client()
    sheet = gc.open_by_key(GOOGLE_SHEET_ID)
    worksheet = sheet.sheet1

    _ensure_headers(worksheet)

    price = listing.get("price")
    price_str = f"${price}" if price else "N/A"

    row = [
        listing.get("date_found", ""),
        price_str,
        listing.get("address", ""),
        listing.get("neighborhood", ""),
        listing.get("walking_time", "N/A"),
        listing.get("bedrooms", 2),
        listing.get("amenities", ""),
        listing.get("link", ""),
        "New",
    ]

    worksheet.append_row(row, value_input_option="USER_ENTERED")
    logger.info(f"Appended to sheet: {listing.get('link', '')[:60]}")
