import discord
from typing import Optional, Dict, List
from ..Utils import show_odd
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
            last_acceptable_odds: float,
            arrow: str,
            oposition_arrow: str,
            analysis_author: Optional[str] = None
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
        self.last_acceptable_odds = last_acceptable_odds
        self.arrow = arrow
        self.oposition_arrow = oposition_arrow
        self.market_updated_at: Optional[datetime] = None
        self.analysis_author = analysis_author

    def __eq__(self, other):
        return self.slug == other.slug

    @property
    def value(self) -> float:
        return self.arb_value(self.current_odds, self.oposition_odds)

    @property
    def slug(self) -> str:
        return f"{self.event_name}|{self.bookmaker['name']}"

    @property
    def link(self) -> str:
        return self.bookmaker['url'] + self.direct_link

    def show_market_p(self) -> str:
        if not self.period:
            return self.market
        return f"{self.market} + [{self.period}]"

    def to_embed(self) -> discord.Embed:
        emb = discord.Embed(title=f"🔔 {self.bookmaker['name']} | {show_odd(self.current_odds)} | {show_odd(self.value)}%")
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
        if self.analysis_author:
            emb.add_field(name="Analysis Author", value=self.analysis_author, inline=True)
            emb.set_thumbnail(url="https://i.imgur.com/dbjleQn.png")
            emb.colour = 0xffba24
        else:
            emb.add_field(name="Value (Edge)", value=f"{show_odd(self.value)}%", inline=True)
            emb.set_thumbnail(url="https://i.imgur.com/0aj5ycP.png")
            emb.colour = 0x2a2ac7
        emb.add_field(name="Bet Link", value=f"[Go to {self.bookmaker['name']}]({self.link})", inline=True)
        return emb
    
    def to_db_values(self) -> List:
        values = [
            self.event_name, self.sport, self.league, self.market, self.period, self.current_odds,
            self.oposition_odds, self.start_at, self.upated_at, self.arrow, self.oposition_arrow,
            self.bookmaker['id'], self.bookmaker['name'], self.link, self.bet_id
        ]
        return values

    @staticmethod
    def arb_value(current_odds: float, oposition_odds: float) -> float:
        if not (current_odds and oposition_odds):
            return 0
        inversion = 1/current_odds + 1/oposition_odds
        return 100/inversion - 100