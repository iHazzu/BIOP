from aiohttp import ClientSession
from typing import List, Optional, Dict
from .types import HTTPException, Arb
from discord.utils import find
from .formating import arrow_color, period_info
from datetime import datetime
import json


class BetClient:
    def __init__(self):
        self.api_key: Optional[str] = None
        self.session: Optional[ClientSession] = None
        self.market_and_bets: Dict = {}
        self.filters: List[Dict] = []
        self.pinnacle_id: int = 1
        with open("core/arbs_api/bookmakers.json") as f:
            bookmakers = json.load(f)
            self.bookmakers = {int(b['id']): b for b in bookmakers}
        with open("core/arbs_api/market_acronyms.json") as f:
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
            'minPercent': 0.5,
            'limit': 100
        }
        bk_ids = ','.join([str(b) for b in self.bookmakers]) + f",{self.pinnacle_id}"
        url = f"https://api-pr.oddsmarket.org/v4/bookmakers/{bk_ids}/arbs"
        data = await self.make_request(url, params)
        current_timestamp = int(datetime.utcnow().timestamp() * 1000)
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
            if bets[0]["odds"] > 2.50:
                # Only show bets with odds less than 2.5
                continue
            if (event["startDatetime"] - current_timestamp) > 3 * 24 * 60 * 60 * 1000:
                # Only events that will start in 3 days
                continue
            arb = Arb(
                bet_id=bets[0]["id"],
                event_name=event["name"],
                sport=sport['name'],
                league=league["name"],
                bookmaker=bookmaker,
                direct_link=bets[0]["bookmakerEvent"]["directLink"],
                start_timestamp=event["startDatetime"] // 1000,
                updated_timestamp=bets[0]["updatedAt"] // 1000,
                market=market,
                period=period_info(league["sportId"], bets[0]["periodIdentifier"]),
                current_odds=bets[0]["odds"],
                oposition_odds=bets[1]["odds"],
                arrow=arrow_color(bets[0]['diff'], bets[0]["updatedAt"], current_timestamp),
                oposition_arrow=arrow_color(bets[1]['diff'], bets[1]["updatedAt"], current_timestamp)
            )
            if arb not in arbs:
                arbs.append(arb)
        return arbs

    async def get_bet(self, bet_id: str) -> List[Dict]:
        pass

    async def close(self):
        await self.session.close()