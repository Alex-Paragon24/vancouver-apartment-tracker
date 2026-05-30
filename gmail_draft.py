import base64
import logging
import requests as http_requests
from email.mime.text import MIMEText
from google.auth.transport.requests import Request

from sheets import get_creds

logger = logging.getLogger(__name__)

TEMPLATE = """\
Hi,

I came across your listing on Craigslist and I'm very interested in the apartment.

About us: we are a young professional couple, non-smokers, no pets. I work in \
hospitality and my partner works in marketing. We are looking to move in as soon \
as possible — our current unit was damaged by flooding through no fault of our own \
— and are planning a long-term stay.

We would love to schedule a viewing at your convenience. Please let us know what \
works for you.

Thank you,
Alex & Karen

---
Listing: {link}
"""


def create_draft(listing):
    try:
        creds = get_creds()
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())

        link = listing.get("link", "")
        neighborhood = listing.get("neighborhood", "Downtown Vancouver")
        price = listing.get("price")
        price_str = f"${price:,}" if isinstance(price, int) else ""

        subject = f"Interested in your {price_str} 2BR listing — {neighborhood}"
        body = TEMPLATE.format(link=link)
        to = listing.get("reply_email", "")

        msg = MIMEText(body)
        msg["to"] = to
        msg["subject"] = subject
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

        resp = http_requests.post(
            "https://gmail.googleapis.com/gmail/v1/users/me/drafts",
            headers={"Authorization": f"Bearer {creds.token}"},
            json={"message": {"raw": raw}},
            timeout=15,
        )
        resp.raise_for_status()
        logger.info(f"Gmail draft created for: {link[:60]}")
    except Exception as e:
        logger.error(f"Gmail draft error for {listing.get('link', '')}: {e}")
