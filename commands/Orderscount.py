import discord
from core import Interaction


async def go(itc: Interaction):
    bot = itc.client
    data = await bot.db.get('''
        SELECT bookmaker_id, COUNT(*)
        FROM orders
        WHERE TIMESTAMPADD(day, 1, created) > now()
        GROUP BY bookmaker_id
        ORDER BY bookmaker_id
    ''')
    emb = discord.Embed(
        title="📊 Orders Count",
        description="See the number of orders at each bookmaker in the last 24 hours:",
        colour=52479
    )
    for bookmaker_id, orders_count in data:
        bookmaker = bot.oclient.bookmakers.get(bookmaker_id)
        bookmaker_name = bookmaker["name"] if bookmaker else f"Bookie_{bookmaker_id}"
        emb.add_field(name=bookmaker_name, value=f"{orders_count} orders", inline=True)
    await itc.response.send_message(embed=emb)