import asyncio
import logging
from os import environ as env
from dotenv import load_dotenv
from core import Bot
from core.utils import setup_logging
import gspread

bot = Bot()


# Events
@bot.event
async def on_ready():
    print(f"\033[92m|=====| BOT ONLINE |=====|\n- Bot user: {bot.user}\033[00m")


# Running bot
async def main():

    # Loading config vars
    load_dotenv()

    # Default log config
    level = logging.INFO if env["INFO_LOGS"] == "yes" else logging.WARNING
    setup_logging(level)
    try:
        print(f"\033[94m STARTING BOT...\033[00m")
        gc = gspread.service_account(filename='worksheet_credentials.json')
        spreadsheet = gc.open_by_key(env['SPREADSHEET_KEY'])
        bot.orders_sheet = spreadsheet.worksheet('Orders')
        await bot.db.connect(env["DATABASE_DSN"])
        await bot.oclient.connect(env["ODDSMARKET_APIKEY"])
        await bot.tclient.connect(spreadsheet)
        await bot.rclient.connect(env["RESEARCH_APIKEY"], bot, spreadsheet)
        await bot.load_extension("commands")
        await bot.start(env["DISCORD_BOT_TOKEN"])
    finally:
        await bot.terminate()


asyncio.run(main())