# -*- coding: utf-8 -*-
import discord
from discord .ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta, UTC
import asyncio
from typing import List
from . import Stop, Start, Bookies, Script, Order, Orderscount, History, update_clv
from core import Bot, Arb, BOT_GUILD
from core.utils import check_if_is_owner, execute_suppress, discord_timer


class BetCog(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot
        self.arbs: List[Arb] = []
        self.update_arbs_loop.start()
        self.update_clv_loop.start()
        # self.research_loop.start()

    @tasks.loop(seconds=1)
    async def update_arbs_loop(self):
        oddsmarket = await execute_suppress(self.bot.oclient.get_arbs()) or []
        analyzes = await execute_suppress(self.bot.tclient.get_email_analyzes()) or []
        now_arbs = oddsmarket + analyzes
        disappeared = [a for a in self.arbs if a not in now_arbs]
        new = [a for a in now_arbs if a not in self.arbs]
        self.arbs = now_arbs + disappeared
        if new and self.update_arbs_loop.current_loop:
            await execute_suppress(self.send_arbs(new))
        if disappeared:
            await execute_suppress(self.delete_arbs(disappeared))

    @update_arbs_loop.before_loop
    async def before_update_arbs(self):
        await self.bot.wait_until_ready()
        data = await self.bot.db.get("SELECT channel_id, GROUP_CONCAT(message_id) FROM messages GROUP BY channel_id")
        for channel_id, message_ids in data:
            channel = self.bot.get_channel(channel_id)
            if channel is not None:
                messages = [discord.Object(id=int(msg_id)) for msg_id in message_ids.split(",")]
                await channel.delete_messages(messages)
        await self.bot.db.set("DELETE FROM messages")

    @tasks.loop(seconds=3)
    async def research_loop(self):
        await execute_suppress(self.bot.rclient.update_arbs())

    @tasks.loop(seconds=30)
    async def update_clv_loop(self):
        await execute_suppress(update_clv.orders(self.bot))
        # await execute_suppress(update_clv.research(self.bot))
        if self.update_clv_loop.current_loop % 20 == 0:
            await execute_suppress(update_clv.analyzes(self.bot))

    @update_clv_loop.before_loop
    async def before_update_orders(self):
        week_ago = datetime.now(UTC) - timedelta(days=7)
        await self.bot.db.set("DELETE FROM orders WHERE match_time<%s", week_ago)
        await self.bot.db.set("DELETE FROM history WHERE found<%s", week_ago)
        await self.bot.db.set("DELETE FROM analyzes WHERE found<%s", week_ago)
        await self.bot.db.set("DELETE FROM research WHERE found<%s", week_ago)
        await self.bot.wait_until_ready()

    async def send_arbs(self, arbs: List[Arb]):
        send_tasks = []
        for arb in arbs:
            data = await self.bot.db.get('''
                SELECT u.channel_id, u.bookies
                FROM users u
                WHERE active AND
                NOT EXISTS(SELECT True FROM orders o WHERE o.user_id=u.user_id AND o.slug=%s);
                INSERT INTO history(event_name, sport, league, market, period, current_odds, oposition_odds,
                start_at, updated_at, arrow, oposition_arrow, bookmaker_id, bookmaker_name, link, bet_id)
                VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
            ''', arb.slug, *arb.to_db_values())
            for channel_id, bookies in data:
                if bookies is None or arb.bookmaker['name'] in bookies.split(","):
                    task = self.send_arb(channel_id, arb)
                    send_tasks.append(task)
        await asyncio.gather(*send_tasks)

    async def send_arb(self, channel_id: int, arb: Arb):
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            # channel was deleted -> delete user
            await self.bot.db.set("DELETE FROM users WHERE channel_id=%s", channel_id)
            return
        msg = await channel.send(embed=arb.to_embed(), view=Order.PlaceOrder(arb))
        self.bot.messages[msg.id] = msg
        await self.bot.db.set('''
            INSERT INTO messages (event_slug, channel_id, message_id)
            VALUES(%s, %s, %s)
        ''', arb.slug, channel_id, msg.id)

    async def delete_arbs(self, arbs: List[Arb]):
        delete_tasks = []
        for arb in arbs:
            data = await self.bot.db.get("SELECT channel_id, message_id FROM messages WHERE event_slug=%s", arb.slug)
            msgs = []
            for channel_id, message_id in data:
                msg = await self.bot.fetch_message(channel_id, message_id)
                if msg is not None:
                    msgs.append(msg)
            if arb.disappeared_at is None:
                arb.disappeared_at = datetime.now(UTC)
            elif (datetime.now(UTC) - arb.disappeared_at) > timedelta(minutes=6):
                self.arbs.remove(arb)
                await self.bot.db.set("DELETE FROM messages WHERE event_slug=%s", arb.slug)
                for msg in msgs:
                    delete_tasks.append(self.delete_message(msg))
            elif (datetime.now(UTC) - arb.disappeared_at) > timedelta(minutes=1):
                for msg in msgs:
                    delete_tasks.append(self.warn_delete_arb(msg, arb))
        await asyncio.gather(*delete_tasks)

    async def warn_delete_arb(self, msg: discord.Message, arb: Arb):
        emb = msg.embeds[0]
        if emb.title != Order.PLACED_ORDER_TITLE and "EVENT WILL DISAPPEAR" not in emb.title:
            emb.title = f":alarm_clock: EVENT WILL DISAPPEAR {discord_timer(5*60)}"
            self.bot.messages[msg.id] = await msg.edit(embed=emb, view=Order.PlaceOrder(arb))

    async def delete_message(self, msg: discord.Message):
        self.bot.messages.pop(msg.id, None)
        if msg.embeds[0].title != Order.PLACED_ORDER_TITLE:
            await msg.delete()

    @app_commands.command(name="start")
    @app_commands.guilds(BOT_GUILD)
    async def start_receive_bets(self, interaction: discord.Interaction):
        """Start receiving new bet notifications

        Args:
            interaction: the interaction associated with the command
        """
        await Start.go(interaction=interaction, bet_cog=self)

    @app_commands.command(name="stop")
    @app_commands.guilds(BOT_GUILD)
    async def stop_receive_bets(self, interaction: discord.Interaction):
        """Stop receiving new bet notifications

        Args:
            interaction: the interaction associated with the command
        """
        await Stop.go(interaction=interaction)

    @app_commands.command(name="bookies")
    @app_commands.guilds(BOT_GUILD)
    async def select_bookies(self, interaction: discord.Interaction):
        """Choose the bookies you want to receive notifications

        Args:
            interaction: the interaction associated with the command
        """

        await Bookies.go(interaction=interaction)

    @app_commands.command(name="history")
    @app_commands.guilds(BOT_GUILD)
    async def history(self, interaction: discord.Interaction):
        """Get the history of bets sent to users

        Args:
            interaction: the interaction associated with the command
        """
        await History.go(itc=interaction)

    @app_commands.command(name="orderscount")
    @app_commands.guilds(BOT_GUILD)
    async def orderscount(self, interaction: discord.Interaction):
        """Get the number of orders at each bookmaker

        Args:
            interaction: the interaction associated with the command
        """
        await Orderscount.go(itc=interaction)

    @commands.command(name="eval")
    @check_if_is_owner()
    async def script(self, ctx: commands.Context, *, code: str):
        """Run a script in the bot

        Args:
            ctx: the context associated with the command
            code: the code to run
        """
        await Script.go(ctx=ctx, code=code)


async def setup(bot: Bot):
    await bot.add_cog(BetCog(bot))