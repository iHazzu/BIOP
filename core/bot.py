from discord.ext import commands
import discord
from .database import DataBase
from .oddsmarket_api import OddsmarketClient, ResearchClient
from .tipsport_api import TipsportClient
from typing import Optional, Dict
from gspread import Worksheet
from contextlib import suppress


class Bot(commands.Bot):
    def __init__(self):
        self.db = DataBase(5)
        self.oclient = OddsmarketClient()
        self.tclient = TipsportClient(self)
        self.rclient = ResearchClient()
        self.orders_sheet: Optional[Worksheet] = None
        self.messages: Dict[int, discord.Message] = {}
        super().__init__(
            command_prefix="!",
            intents=discord.Intents(messages=True, message_content=True, guilds=True),
            max_messages=None
        )

    async def fetch_message(self, channel_id: int, message_id: int) -> Optional[discord.Message]:
        msg = self.messages.get(message_id)
        if msg is None:
            channel = self.get_channel(channel_id)
            if channel:
                with suppress(discord.NotFound):
                    msg = await channel.fetch_message(message_id)
        return msg

    async def terminate(self) -> None:
        self.db.close()
        await self.oclient.close()
        await self.rclient.close()
        await self.close()