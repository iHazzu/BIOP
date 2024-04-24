from .database import DataBase
from .bot import Bot
from .oddsmarket_api import OddsmarketClient
from .types import HTTPException, Arb, NotFound
import discord
from discord.ext import commands
from .constants import Embeds, PRAGUE


Context, Interaction = commands.Context[Bot], discord.Interaction[Bot]
BOT_GUILD = discord.Object(id=1153338183623385138)
BOT_DEVS = [535159866717896726, 1125367642232999987]