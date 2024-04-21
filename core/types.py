import discord
from discord.utils import format_dt
from typing import Optional, Dict, List
from .utils import show_odd
from datetime import datetime


class HTTPException(Exception):
    def __init__(self, text: str):
        self.text = text
        super().__init__(text)


class Arb:
    def __init__(
            self,
            bet_id: str,
            event_name: str,
            sport: str,
            league: str,
            bookmaker: Dict,
            event_direct_link: str,
            start_at: datetime,
            updated_at: datetime,
            market: str,
            current_odds: float,
            oposition_odds: float = 0,
            origin_odds: float = 0,
            period: str = "",
            arrow: str = "",
            oposition_arrow: str = "",
            analysis_author: Optional[str] = None,
            bet_direct_link: Optional[str] = None
    ):
        self.bet_id = bet_id
        self.event_name = event_name
        self.sport = sport
        self.league = league
        self.bookmaker = bookmaker
        if event_direct_link[0] == "/":
            self.event_direct_link = event_direct_link[1:]
        else:
            self.event_direct_link = event_direct_link
        self.start_at = start_at
        self.updated_at = updated_at
        self.disappeared_at: Optional[datetime] = None
        self.market = market
        self.period = period
        self.current_odds = current_odds
        self.oposition_odds = oposition_odds
        self.arrow = arrow
        self.oposition_arrow = oposition_arrow
        self.origin_odds = origin_odds
        self.market_updated_at: Optional[datetime] = None
        self.analysis_author = analysis_author
        self.bet_direct_link = bet_direct_link
        self.lao_percent: float = -0.03

    def __eq__(self, other):
        if self.analysis_author:
            return self.event_direct_link == other.event_direct_link
        return self.slug == other.slug

    @property
    def value(self) -> float:
        return self.arb_value(self.current_odds, self.oposition_odds)

    @property
    def slug(self) -> str:
        return f"{self.event_name}|{self.bookmaker['name']}"

    @property
    def event_link(self) -> str:
        if self.bookmaker['id'] == 80:
            match_id = self.event_direct_link.split("MRO")[-1]
            return self.bookmaker['url'] + "sazeni/xxx/yyy/MCZ" + match_id
        elif self.bookmaker['id'] == 308:
            return self.bookmaker['url'] + "kurzove-sazky/sports/event/" + self.event_direct_link
        return self.bookmaker['url'] + self.event_direct_link

    @property
    def bet_link(self) -> str:
        if not self.bet_direct_link:
            return self.event_link
        if self.bookmaker['id'] == 39:
            match_id = self.event_direct_link.split("=")[-1]
            ticket = f"vytvorit-tiket?bets=AKU%200,{self.bet_direct_link}&amount=220&matchId={match_id}"
            return self.bookmaker['url'] + ticket
        elif self.bookmaker['id'] == 80:
            args = self.bet_direct_link.split("-")
            if len(args) == 2:
                ticket = f"ticket/M/createticket/100.0/{args[1]}/{args[0]}"
                return self.bookmaker['url'] + ticket
        return self.event_link

    @property
    def sportbreak_link(self) -> str:
        if self.bookmaker['id'] == 39:
            match_id = self.event_direct_link.split("=")[-1]
            return self.bookmaker['url'] + f"vysledky?matchesFilter={match_id}"
        elif self.bookmaker['id'] == 80:
            return self.event_link.replace("xxx/", "vysledky/xxx/")
        return self.event_link

    @property
    def last_acceptable_odds(self) -> float:
        if self.oposition_odds:
            return 1/(1/1.0001 - 1/self.oposition_odds)
        from_odds = self.origin_odds or self.current_odds
        return (1+self.lao_percent) * from_odds

    def show_market_p(self) -> str:
        if not self.period:
            return self.market
        return f"{self.market} + [{self.period}]"

    def to_embed(self) -> discord.Embed:
        emb = discord.Embed(
            title=f"🔔 {self.bookmaker['name']} | {show_odd(self.current_odds)} | {show_odd(self.value)}%")
        emb.add_field(name="Event Name", value=self.event_name, inline=True)
        emb.add_field(name="Sport", value=self.sport, inline=True)
        emb.add_field(name="Bookie", value=self.bookmaker['name'], inline=True)
        emb.add_field(name="Match Starts", value=format_dt(self.start_at, "R"), inline=True)
        if self.market_updated_at:
            t = format_dt(self.market_updated_at, "R")
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
        emb.add_field(name="Bet Link", value=f"[Go to {self.bookmaker['name']}]({self.bet_link})", inline=True)
        return emb

    def to_db_values(self) -> List:
        values = [
            self.event_name, self.sport, self.league, self.market, self.period, self.current_odds,
            self.oposition_odds, self.start_at, self.updated_at, self.arrow, self.oposition_arrow,
            self.bookmaker['id'], self.bookmaker['name'], self.event_link, self.bet_id
        ]
        return values

    @staticmethod
    def arb_value(current_odds: float, oposition_odds: float) -> float:
        if not (current_odds and oposition_odds):
            return 0
        inversion = 1 / current_odds + 1 / oposition_odds
        return 100 / inversion - 100