import discord
from core import Interaction
from core.Utils import prague_time
from io import StringIO, BytesIO
from datetime import datetime
import csv


async def go(itc: Interaction):
    bot = itc.client
    data = await bot.db.get('''
        SELECT event_name, sport, bookmaker_id, found
        FROM history
        WHERE TIMESTAMPADD(day, 7, found) > now()
        ORDER BY found DESC
    ''')
    out = StringIO()
    writer = csv.writer(out)
    writer.writerow(["row", "event", "sport", "bookmaker", "sent_at"])
    i = 1
    for event_name, sport, bookmaker_id, found in data:
        bookmaker = bot.bclient.bookmakers.get(bookmaker_id)
        bookmaker_name = bookmaker["name"] if bookmaker else f"Bookie_{bookmaker_id}"
        sent_at = prague_time(found).strftime("%d.%m.%Y %H:%M:%S")
        writer.writerow([i, event_name, sport, bookmaker_name, sent_at])
        i += 1
    now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    file = discord.File(
        fp=BytesIO(out.getvalue().encode()),
        filename=f"bets_history_{now_str}.csv"
    )
    await itc.response.send_message(content="> These were the bets sent in the last 7 days:", file=file)