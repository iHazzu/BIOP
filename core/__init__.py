from .database import DataBase
from .Bot import Bot
from .bet_burger_api import BetClient, HTTPException, Arb
import discord
from discord.ext import commands


Context, Interaction = commands.Context[Bot], discord.Interaction[Bot]
BOT_GUILD = discord.Object(id=1153338183623385138)
BOT_DEVS = [535159866717896726, 1125367642232999987]