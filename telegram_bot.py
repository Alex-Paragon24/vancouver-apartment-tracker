import asyncio
import logging
from datetime import datetime, timezone
from telegram import Bot
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)


def _format_posted_age(posted_ts):
    if not posted_ts:
        return None
    delta = datetime.now(timezone.utc).timestamp() - posted_ts
    hours = int(delta // 3600)
    if hours < 1:
        return "только что"
    if hours < 24:
        return f"{hours} ч. назад"
    days = hours // 24
    return f"{days} дн. назад"


def _format_message(listing):
    price = listing.get("price")
    price_str = f"${price:,}/mo" if isinstance(price, int) else "N/A"
    address = listing.get("address") or listing.get("neighborhood") or "Vancouver"
    neighborhood = listing.get("neighborhood", "")
    walking_time = listing.get("walking_time", "N/A")
    bedrooms = listing.get("bedrooms", 2)
    amenities = listing.get("amenities", "")
    link = listing.get("link", "")

    posted_age = _format_posted_age(listing.get("posted_ts"))

    lines = [
        f"🏠 <b>New {bedrooms}BR listing — {neighborhood}</b>",
        "",
        f"💰 <b>Price:</b> {price_str}",
        f"📍 <b>Address:</b> {address}",
        f"🚶 <b>Walk to Bacchus:</b> {walking_time}",
    ]
    if posted_age:
        lines.append(f"🕐 <b>Posted:</b> {posted_age}")
    if amenities:
        lines.append(f"✨ <b>Amenities:</b> {amenities}")
    lines += ["", f'<a href="{link}">View listing →</a>']

    return "\n".join(lines)


def send_run_summary(new_cl, new_kj, skipped_seen, skipped_hood, skipped_furnished):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    total = new_cl + new_kj
    if total:
        status = f"🏠 <b>{total} new listing{'s' if total > 1 else ''}</b>"
        breakdown = f"Craigslist: {new_cl} · Kijiji: {new_kj}"
    else:
        status = "✅ <b>Run complete — nothing new</b>"
        breakdown = f"Craigslist: {new_cl} · Kijiji: {new_kj}"

    text = (
        f"{status}\n"
        f"{breakdown}\n"
        f"<i>skipped: {skipped_seen} seen · {skipped_hood} wrong area · {skipped_furnished} furnished</i>"
    )

    async def _send():
        async with Bot(token=TELEGRAM_BOT_TOKEN) as bot:
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text, parse_mode="HTML")

    asyncio.run(_send())


def send_error_notification(error_text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    async def _send():
        async with Bot(token=TELEGRAM_BOT_TOKEN) as bot:
            await bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=f"⚠️ <b>Scraper error</b>\n\n<code>{error_text[:1000]}</code>",
                parse_mode="HTML",
            )

    asyncio.run(_send())


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
