# -*- coding: utf-8 -*-
import logging
from typing import Coroutine, Any
from aiohttp import ClientError, ClientOSError
import discord
from discord.ext import commands
from datetime import timedelta


async def execute_suppress(coro: Coroutine) -> Any:
    try:
        return await coro
    except KeyboardInterrupt:
        raise
    except (ClientError, ClientOSError, discord.DiscordServerError):
        return
    except Exception as error:
        logging.exception(error)


def show_odd(odd: float) -> str:
    return f"{round(odd, 2):.2f}"


def discord_timer(extra_seconds: float) -> str:
    end_time = discord.utils.utcnow() + timedelta(seconds=extra_seconds)
    return discord.utils.format_dt(end_time, "R")


def check_if_is_owner():
    def predicate(ctx: commands.Context):
        # hazzu or bot owner
        return ctx.author.id == 535159866717896726 or ctx.bot.is_owner(ctx.author)
    return commands.check(predicate)