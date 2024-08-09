from aiohttp import ClientSession
from typing import List, Optional, Dict
from core.types import HTTPException, Arb
from discord.utils import find
from .helper import arrow_color, period_info
from datetime import datetime, UTC, timedelta
import json

MIN_ARB_VALUE = 0.01


class OddsmarketClient:
    def __init__(self):
        self.api_key: Optional[str] = None
        self.session: Optional[ClientSession] = None
        self.market_and_bets: Dict = {}
        self.pinnacle_id: int = 1
        with open("core/oddsmarket_api/bookmakers.json") as f:
            bookmakers = json.load(f)
            self.bookmakers = {int(b['id']): b for b in bookmakers}
        with open("core/oddsmarket_api/market_acronyms.json") as f:
            self.market_acronyms = json.load(f)

    async def connect(self, api_key: str):
        self.api_key = api_key
        self.session = ClientSession()
        self.market_and_bets = await self.make_request("https://api-mst.oddsmarket.org/v4/market_and_bet_types")

    async def make_request(self, url: str, params: Dict = None) -> Dict:
        params = params or {}
        params['apiKey'] = self.api_key
        async with self.session.get(url, params=params) as resp:
            if not resp.ok:
                raise HTTPException(await resp.text())
            return await resp.json()

    async def get_arbs(self) -> List[Arb]:
        params = {
            'requiredBookmakerIds': [self.pinnacle_id],
            'grouped': 'false',
            'minPercent': MIN_ARB_VALUE,
            'limit': 100
        }
        bk_ids = ','.join([str(b) for b in self.bookmakers]) + f",{self.pinnacle_id}"
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
            if bets[0]["bookmakerEvent"]["bookmakerId"] == self.pinnacle_id:
                bets.reverse()
            market_dir = find(lambda m: m['id'] == bets[0]["marketAndBetTypeId"], self.market_and_bets)
            market_text_model = self.market_acronyms[market_dir["title"]]
            market = market_text_model.replace("%s", str(bets[0]["marketAndBetTypeParam"]))
            event = data["events"][str(arb["eventId"])]
            league = data["leagues"][str(event["leagueId"])]
            sport = data["sports"][str(league["sportId"])]
            bookmaker = self.bookmakers[bets[0]["bookmakerEvent"]["bookmakerId"]]
            start_at = datetime.fromtimestamp(event["startDatetime"] / 1000, UTC)
            updated_at = datetime.fromtimestamp(bets[0]["updatedAt"] / 1000, UTC)
            if bets[0]["odds"] > 2.50:
                # Only show bets with odds less than 3.5
                continue
            if start_at - datetime.now(UTC) > timedelta(days=3):
                # Only events that will start in 3 days
                continue
            arb = Arb(
                bet_id=bets[0]["id"],
                oposition_bet_id=bets[1]["id"],
                event_name=event["name"],
                sport=sport['name'],
                league=league["name"],
                bookmaker=bookmaker,
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

    async def same_bets(self, bet_id: str, bookmaker_ids: List[int]) -> Optional[Dict]:
        params = {'betId': bet_id, 'bookmakerIds': bookmaker_ids}
        url = "https://api-pr.oddsmarket.org/v4/same_bets_by_betid"
        data = await self.make_request(url, params)
        return data.get("responseData")



    async def close(self):
        await self.session.close()