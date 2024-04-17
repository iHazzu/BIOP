# -*- coding: utf-8 -*-
import discord
from discord .ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta, UTC
from asyncio import create_task, gather
from typing import List
from . import Stop, Start, Bookies, Script, Order, Orderscount, History
from core import Bot, Arb, BOT_GUILD
from core.utils import check_if_is_owner, execute_suppress, discord_timer


class BetCog(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot
        self.arbs: List[Arb] = []
        self.last_update_orders_time = datetime.now(UTC)
        self.last_update_arbs_time = datetime.now(UTC) - timedelta(seconds=5)
        self.update_arbs_loop.start()
        self.update_orders_loop.start()

    @tasks.loop(seconds=1)
    async def update_arbs_loop(self):
        now = datetime.now(UTC)
        oddsmarket = await execute_suppress(self.bot.oclient.get_arbs()) or []
        analyzes = await execute_suppress(self.bot.tclient.get_email_analyzes()) or []
        now_arbs = oddsmarket + analyzes
        new, updated, sportbreak = [], [], []
        for j, a in enumerate(now_arbs):
            try:
                i = self.arbs.index(a)
                if self.arbs[i].disappeared_at:
                    # cooldown for bets that are disappearing/appearing too fast
                    if int(now.timestamp()) - self.arbs[i].disappeared_at > 60:
                        updated.append(a)
                    else:
                        now_arbs[j].disappeared_at = self.arbs[i].disappeared_at
                if (self.arbs[i].value, self.arbs[i].market) != (a.value, a.market):
                    if self.arbs[i].market != a.market:
                        a.market_updated_at = now
                    else:
                        a.market_updated_at = self.arbs[i].market_updated_at
                    updated.append(a)
                    if self.arbs[i].value < 2 <= a.value:
                        sportbreak.append(a)
            except ValueError:
                new.append(a)
        disappeared = [a for a in self.arbs if a not in now_arbs]
        self.arbs = now_arbs + disappeared
        if new and self.update_arbs_loop.current_loop + 1:
            await execute_suppress(self.send_arbs(new))
        if updated:
            await execute_suppress(self.update_arbs(updated))
        if disappeared:
            await execute_suppress(self.delete_arbs(disappeared))
        sportbreak += [a for a in new if a.value >= 2]
        if sportbreak:
            await execute_suppress(self.sportbreak_publish(sportbreak))

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

    @tasks.loop(seconds=30)
    async def update_orders_loop(self):
        await execute_suppress(Order.update_orders(self.bot))

    @update_orders_loop.before_loop
    async def before_update_orders(self):
        week_ago = datetime.now(UTC) - timedelta(days=7)
        await self.bot.db.set("DELETE FROM orders WHERE match_time<%s", week_ago)
        await self.bot.db.set("DELETE FROM history WHERE found<%s", week_ago)
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
        await gather(*send_tasks)

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

    async def update_arbs(self, arbs: List[Arb]):
        update_tasks = []
        for arb in arbs:
            data = await self.bot.db.get("SELECT channel_id, message_id FROM messages WHERE event_slug=%s", arb.slug)
            for channel_id, message_id in data:
                update_tasks.append(self.update_arb(channel_id, message_id, arb))
        await gather(*update_tasks)

    async def update_arb(self, channel_id: int, message_id: int, arb: Arb):
        msg = await self.bot.fetch_message(channel_id, message_id)
        now = discord.utils.utcnow()
        if not msg:
            return
        edited_age = now - (msg.edited_at or msg.created_at)
        msg_age = now - msg.created_at
        if "EVENT WILL DISAPPEAR" not in msg.embeds[0].title:
            if msg_age < timedelta(minutes=10):
                if edited_age < timedelta(seconds=20):
                    return
            else:
                if edited_age < timedelta(minutes=2):
                    return
        new_emb = arb.to_embed()
        view = Order.PlaceOrder(arb)
        if msg.embeds[0].title == Order.PLACED_ORDER_TITLE:
            new_emb.title = Order.PLACED_ORDER_TITLE
            view.children[0].disabled = True
        self.bot.messages[msg.id] = await msg.edit(embed=new_emb, view=view)

    async def delete_arbs(self, arbs: List[Arb]):
        delete_tasks = []
        now_timestamp = int(datetime.now(UTC).timestamp())
        for arb in arbs:
            data = await self.bot.db.get("SELECT channel_id, message_id FROM messages WHERE event_slug=%s", arb.slug)
            msgs = []
            for channel_id, message_id in data:
                msg = await self.bot.fetch_message(channel_id, message_id)
                if msg is not None:
                    msgs.append(msg)
            if arb.disappeared_at is None:
                arb.disappeared_at = now_timestamp
                for msg in msgs:
                    delete_tasks.append(self.warn_delete_arb(msg, arb))
            elif (now_timestamp - arb.disappeared_at) > 5*60:
                self.arbs.remove(arb)
                await self.bot.db.set("DELETE FROM messages WHERE event_slug=%s", arb.slug)
                for msg in msgs:
                    delete_tasks.append(self.delete_message(msg))
        await gather(*delete_tasks)

    async def warn_delete_arb(self, msg: discord.Message, arb: Arb):
        emb = msg.embeds[0]
        if emb.title != Order.PLACED_ORDER_TITLE:
            emb.title = f":alarm_clock: EVENT WILL DISAPPEAR {discord_timer(5*60)}"
            self.bot.messages[msg.id] = await msg.edit(embed=emb, view=Order.PlaceOrder(arb))

    async def delete_message(self, msg: discord.Message):
        self.bot.messages.pop(msg.id, None)
        if msg.embeds[0].title != Order.PLACED_ORDER_TITLE:
            await msg.delete()

    async def sportbreak_publish(self, arbs: List[Arb]):
        for arb in arbs:
            if not arb.bookmaker['servis']:
                continue
            data = await self.bot.db.get('''
                SELECT 
                    EXISTS(SELECT True FROM history WHERE event_name=%s AND bookmaker_id=%s AND sportbreak_post),
                    (SELECT COUNT(*) FROM history WHERE bookmaker_id=%s AND sportbreak_post AND DATE(found)=CURDATE())
            ''', arb.event_name, arb.bookmaker['id'], arb.bookmaker['id'])
            if data[0][1] >= 10:
                # daily rate limit
                return
            if not data[0][0] and self.bot.sclient.is_allowed_sport(arb.sport):
                await self.bot.db.set('''
                    UPDATE history
                    SET sportbreak_post = True
                    WHERE event_name=%s AND bookmaker_id=%s
                    ORDER BY found DESC LIMIT 1
                ''', arb.event_name, arb.bookmaker['id'])
                create_task(self.bot.sclient.publish(arb))

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