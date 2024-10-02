from __future__ import annotations
from aiohttp import ClientSession
from typing import List, Optional, Dict, TYPE_CHECKING
from core.types import HTTPException, Arb
from discord.utils import find
from .helper import arrow_color, period_info
from datetime import datetime, UTC
import json
from gspread import Worksheet, Spreadsheet
from core.constants import PRAGUE

MIN_ARB_VALUE = 0.5
BOOKIE_DROP = '=IF(K2<>0, (K2-{0})/{0}, "∄")'

if TYPE_CHECKING:
    from core import Bot


class ResearchClient:
    def __init__(self):
        self.api_key: Optional[str] = None
        self.session: Optional[ClientSession] = None
        self.market_and_bets: Dict = {}
        self.tipsport_id: int = 39
        self.bk_ids: List[int] = [1, 3, 5, 10, 11, 12, 20, 56, 73, 78, 92, 119, 148, 169, 199, 200, 201, 202, 289, 307]
        with open("core/oddsmarket_api/market_acronyms.json") as f:
            self.market_acronyms = json.load(f)
        self.worksheet: Optional[Worksheet] = None
        self.bot: Optional[Bot] = None
        self.arbs: List[Arb] = []

    async def connect(self, api_key: str, bot: Bot, spreadsheet: Spreadsheet):
        self.api_key = api_key
        self.session = ClientSession()
        self.market_and_bets = await self.make_request("https://api-mst.oddsmarket.org/v4/market_and_bet_types")
        self.bot = bot
        self.worksheet = spreadsheet.worksheet("Research")

    async def make_request(self, url: str, params: Dict = None) -> Dict:
        params = params or {}
        params['apiKey'] = self.api_key
        async with self.session.get(url, params=params) as resp:
            if not resp.ok:
                raise HTTPException(await resp.text())
            return await resp.json()

    async def update_arbs(self):
        now_arbs = await self.get_arbs()
        for arb in now_arbs:
            if arb not in self.arbs:
                await self.post_arb(arb)
        self.arbs = now_arbs

    async def get_arbs(self) -> List[Arb]:
        params = {
            'requiredBookmakerIds': [self.tipsport_id],
            'grouped': 'false',
            'minPercent': MIN_ARB_VALUE,
            'limit': 100,
            'maxEventStartOffsetTime': 3 * 24 * 60 * 60 * 1000,
        }
        bk_ids = ','.join([str(b) for b in self.bk_ids]) + f",{self.tipsport_id}"
        url = f"https://api-pr.oddsmarket.org/v4/bookmakers/{bk_ids}/arbs"
        data = await self.make_request(url, params)
        arbs = []
        if "arbs" not in data:
            return arbs
        for arb in data["arbs"].values():
            bets = []
            for bet_id in arb["betIds"]:
                bet = data["bets"][bet_id]
                bet["id"] = bet_id
                bet["bookmakerEvent"] = data["bookmakerEvents"][str(bet["bookmakerEventId"])]
                bets.append(bet)
            if bets[0]["bookmakerEvent"]["bookmakerId"] != self.tipsport_id:
                bets.reverse()
            market_dir = find(lambda m: m['id'] == bets[0]["marketAndBetTypeId"], self.market_and_bets)
            market_text_model = self.market_acronyms[market_dir["title"]]
            market = market_text_model.replace("%s", str(bets[0]["marketAndBetTypeParam"]))
            event = data["events"][str(arb["eventId"])]
            league = data["leagues"][str(event["leagueId"])]
            sport = data["sports"][str(league["sportId"])]
            oposition_bookmaker_id = bets[1]["bookmakerEvent"]["bookmakerId"]
            oposition_bookmaker = data["bookmakers"][str(oposition_bookmaker_id)]
            oposition_bookmaker["id"] = oposition_bookmaker_id
            start_at = datetime.fromtimestamp(event["startDatetime"] / 1000, UTC)
            updated_at = datetime.fromtimestamp(bets[0]["updatedAt"] / 1000, UTC)
            if oposition_bookmaker_id == self.tipsport_id:
                # Ignore arbs with tipsport in both sides
                continue
            if bets[0]["odds"] > 2.50:
                # Only show bets with odds less than 2.5
                continue
            arb = Arb(
                bet_id=bets[0]["id"],
                event_name=event["name"],
                sport=sport['name'],
                league=league["name"],
                bookmaker=oposition_bookmaker,
                event_direct_link=bets[0]["bookmakerEvent"]["directLink"],
                start_at=start_at,
                updated_at=updated_at,
                market=market,
                period=period_info(league["sportId"], bets[0]["periodIdentifier"]),
                current_odds=bets[0]["odds"],
                oposition_odds=bets[1]["odds"],
                arrow=arrow_color(bets[0]['diff'], bets[0]["updatedAt"]),
                oposition_arrow=arrow_color(bets[1]['diff'], bets[1]["updatedAt"]),
                bet_direct_link=bets[0]["directLink"]
            )
            if arb not in arbs and arb.value >= MIN_ARB_VALUE:
                arbs.append(arb)
        return arbs

    async def post_arb(self, arb: Arb):
        data = await self.bot.db.get('''
            SELECT true
            FROM research
            WHERE bet_id=%s AND oposition_bookmaker_id=%s
        ''', arb.bet_id, arb.bookmaker["id"])
        if data:
            return
        values = [
            arb.updated_at.astimezone(PRAGUE).strftime("%d/%m/%Y %H:%M:%S"),
            arb.start_at.astimezone(PRAGUE).strftime("%d/%m/%Y %H:%M:%S"),
            "=B2-A2",  # Time To Event,
            arb.sport,
            arb.league,
            arb.event_name,
            arb.market,
            arb.period,
            arb.current_odds,
            arb.oposition_odds,
            0,  # Tipsport CLV,
            BOOKIE_DROP.format("I2"),
            arb.value/100,
            arb.bookmaker["name"],
            arb.arrow,
            arb.oposition_arrow,
            arb.bet_id
        ]
        await self.bot.loop.run_in_executor(
            None,
            self.worksheet.insert_row,
            values, 2, "USER_ENTERED"
        )
        await self.bot.db.set('''
            INSERT INTO research(bet_id, match_time, oposition_bookmaker_id)
            VALUES(%s, %s, %s)
        ''', arb.bet_id, arb.start_at, arb.bookmaker["id"])

    async def get_bet(self, bet_id: str) -> Dict:
        url = f"https://api-pr.oddsmarket.org/v4/bookmakers/arbs/bets/{bet_id}"
        return await self.make_request(url)

    async def close(self):
        await self.session.close()