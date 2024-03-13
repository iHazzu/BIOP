import discord
import asyncio
import logging
from os import environ as env
from dotenv import load_dotenv
from core import Bot
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
    discord.utils.setup_logging(level=logging.WARNING)
    try:
        print(f"\033[94m STARTING BOT...\033[00m")
        gc = gspread.service_account(filename='google_credentials.json')
        spreadsheet = gc.open_by_key(env['SPREADSHEET_KEY'])
        bot.worksheet = spreadsheet.worksheet('Reportsheet')
        await bot.db.connect(env["DATABASE_DSN"])
        await bot.bclient.connect(env["ODDSMARKET_APIKEY"])
        await bot.sbclient.connect(env["SPORTBREAK_PHPSESSID"], env["SPORTBREAK_ALLOWED_SPORT_IDS"])
        await bot.load_extension("commands")
        await bot.start(env["DISCORD_BOT_TOKEN"])
    finally:
        await bot.terminate()


asyncio.run(main())