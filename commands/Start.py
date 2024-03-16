from __future__ import annotations
import discord
from core import Interaction, Bot
from typing import TYPE_CHECKING
from asyncio import sleep

if TYPE_CHECKING:
    from commands import BetCog

CATEGORY_ID = 1157803933968900256


async def go(interaction: Interaction, bet_cog: BetCog):
    await interaction.response.defer()
    bot = interaction.client
    user = interaction.user
    data = await bot.db.get("SELECT active, channel_id FROM users WHERE user_id=%s", user.id)
    channel = bot.get_channel(data[0][1]) if data else None

    if not channel:
        category: discord.CategoryChannel = interaction.guild.get_channel(CATEGORY_ID)
        permissions = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True)
        }
        channel = await category.create_text_channel(name=str(user), overwrites=permissions)
        await bot.db.set('''
            DELETE FROM users WHERE user_id=%s;
            INSERT INTO users(user_id, username, channel_id)
            VALUES (%s, %s, %s)
        ''', user.id, user.id, str(user), channel.id)
        await channel.send(
            f"> 🔎 {user.mention} I will send you bets on this channel. "
            f"Use the `/bookies` command to filter the bookmakers you are interested in."
        )

    else:
        if not data[0][0]:
            await bot.db.set("UPDATE users SET active=True WHERE user_id=%s", user.id)
        else:
            emb = discord.Embed(
                description="⚠ You have already activated the bot.",
                colour=discord.Colour.red()
            )
            return await interaction.followup.send(embed=emb)

    emb = discord.Embed(
        title="✅ Connected Successfully",
        description="I will send you new messages whenever a new bet comes up!",
        colour=discord.Colour.green()
    )
    await interaction.followup.send(embed=emb)

    await sleep(3)
    for arb in bet_cog.arbs:
        data = await bot.db.get(f'''
            SELECT channel_id FROM users
            WHERE NOT EXISTS(SELECT True FROM orders WHERE user_id=%s AND slug=%s)
            AND bookies IS NULL OR bookies LIKE '%%{arb.bookmaker["name"]}%%'
            AND user_id=%s
        ''', user.id, arb.slug, user.id)
        if data:
            await bet_cog.send_arb(data[0][0], arb)


async def deleted_user_channel(channel_id: int, bot: Bot):
    await bot.db.set("DELETE FROM users WHERE channel_id=%s", channel_id)
