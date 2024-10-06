# -*- coding: utf-8 -*-
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Coroutine, Any
from aiohttp import ClientError, ClientOSError
import discord
from discord.ext import commands
from datetime import timedelta
from asyncio import TimeoutError
from aiogoogle.models import HTTPError


async def execute_suppress(coro: Coroutine) -> Any:
    try:
        return await coro
    except KeyboardInterrupt:
        raise
    except (ClientError, ClientOSError, discord.DiscordServerError, TimeoutError, HTTPError) as error:
        logging.warning(error)
    except Exception as error:
        logging.exception(error)


def show_odd(odd: float) -> str:
    if not odd:
        return "?"
    return f"{round(odd, 2):.2f}"


def discord_timer(extra_seconds: float) -> str:
    end_time = discord.utils.utcnow() + timedelta(seconds=extra_seconds)
    return discord.utils.format_dt(end_time, "R")


def check_if_is_owner():
    def predicate(ctx: commands.Context):
        # hazzu or bot owner
        return ctx.author.id == 535159866717896726 or ctx.bot.is_owner(ctx.author)
    return commands.check(predicate)


def setup_logging(level: int):
    """Configurar logging para exibir logs no terminal e também salvar em um arquivo"""
    logs_path = Path("logs")
    if not logs_path.exists():
        logs_path.mkdir()
    logs_path = logs_path.joinpath("logs.log")
    terminal = logging.StreamHandler()
    terminal.setFormatter(discord.utils._ColourFormatter())
    file = TimedRotatingFileHandler(filename=logs_path, when='midnight', backupCount=10)
    file.setLevel(logging.WARNING)
    file.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s]: %(message)s\n"))
    logging.basicConfig(level=level, handlers=[terminal, file])
    logging.warning("STARTING BOT...")