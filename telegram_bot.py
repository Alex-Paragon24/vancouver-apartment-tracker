import asyncio
import logging
from telegram import Bot
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)


def _format_message(listing):
    price = listing.get("price")
    price_str = f"${price:,}/mo" if isinstance(price, int) else "N/A"
    address = listing.get("address") or listing.get("neighborhood") or "Vancouver"
    neighborhood = listing.get("neighborhood", "")
    walking_time = listing.get("walking_time", "N/A")
    bedrooms = listing.get("bedrooms", 2)
    amenities = listing.get("amenities", "")
    link = listing.get("link", "")

    lines = [
        f"🏠 <b>New {bedrooms}BR listing — {neighborhood}</b>",
        "",
        f"💰 <b>Price:</b> {price_str}",
        f"📍 <b>Address:</b> {address}",
        f"🚶 <b>Walk to Bacchus:</b> {walking_time}",
    ]
    if amenities:
        lines.append(f"✨ <b>Amenities:</b> {amenities}")
    lines += ["", f'<a href="{link}">View listing →</a>']

    return "\n".join(lines)


def send_notification(listing):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram credentials not set — skipping notification")
        return

    async def _send():
        async with Bot(token=TELEGRAM_BOT_TOKEN) as bot:
            await bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=_format_message(listing),
                parse_mode="HTML",
                disable_web_page_preview=False,
            )

    asyncio.run(_send())
    logger.info(f"Telegram notification sent for: {listing.get('link', '')[:60]}")
