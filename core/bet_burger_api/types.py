import discord
from typing import Optional, Dict
from ..Utils import show_odd, discord_timer
from datetime import datetime


class HTTPException(Exception):
    def __init__(self, text: str):
        super().__init__(text)


class Arb:
    def __init__(
            self,
            bet_id: str,
            event_name: str,
            sport: str,
            league: str,
            bookmaker: Dict,
            direct_link: str,
            start_timestamp: int,
            updated_timestamp: int,
            market: str,
            period: str,
            current_odds: float,
            oposition_odds: float,
            arrow: str,
            oposition_arrow: str
    ):
        self.bet_id = bet_id
        self.event_name = event_name
        self.sport = sport
        self.league = league
        self.bookmaker = bookmaker
        if bookmaker['id'] == 80:
            self.direct_link = direct_link.split("MRO")[-1]
        else:
            self.direct_link = direct_link
        self.start_at = start_timestamp
        self.upated_at = updated_timestamp
        self.disappeared_at: Optional[int] = None
        self.market = market
        self.period = period
        self.current_odds = current_odds
        self.oposition_odds = oposition_odds
        self.arrow = arrow
        self.oposition_arrow = oposition_arrow
        self.market_updated_at: Optional[datetime] = None

    def __eq__(self, other):
        return self.slug == other.slug

    @property
    def value(self) -> float:
        inversion = 1/self.current_odds + 1/self.oposition_odds
        return 100/inversion - 100

    @property
    def last_acceptable_odds(self) -> float:
        inversion = 1/1.005 - 1/self.oposition_odds
        return 1/inversion

    @property
    def slug(self):
        return f"{self.event_name}|{self.bookmaker['name']}"

    @property
    def link(self):
        return self.bookmaker['url'] + self.direct_link

    def show_market_p(self) -> str:
        if not self.period:
            return self.market
        return f"{self.market} + [{self.period}]"

    def to_embed(self) -> discord.Embed:
        emb = discord.Embed(
            title=f"🔔 {self.bookmaker['name']} | {show_odd(self.current_odds)} | {show_odd(self.value)}%",
            colour=0x2a2ac7
        )
        emb.add_field(name="Event Name", value=self.event_name, inline=True)
        emb.add_field(name="Sport", value=self.sport, inline=True)
        emb.add_field(name="Bookie", value=self.bookmaker['name'], inline=True)
        emb.add_field(name="Match Starts", value=f"<t:{self.start_at}:R>", inline=True)
        if self.market_updated_at:
            t = discord.utils.format_dt(self.market_updated_at, "R")
        else:
            t = ""
        emb.add_field(name=f"Market {t}", value=self.show_market_p(), inline=True)
        emb.add_field(name="Current Odds", value=show_odd(self.current_odds), inline=True)
        emb.add_field(name="Last Acceptable Odds", value=show_odd(self.last_acceptable_odds), inline=True)
        emb.add_field(name="Value (Edge)", value=f"{show_odd(self.value)}%", inline=True)
        emb.add_field(name="Bet Link", value=f"[Go to {self.bookmaker['name']}]({self.link})", inline=True)
        emb.set_thumbnail(url="https://cdn.discordapp.com/attachments/1131671133419212840/1131672060528165066/bet_img.png")
        return emb