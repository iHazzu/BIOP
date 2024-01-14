from aiohttp import ClientSession
from typing import List, Optional, Dict, Union
from .types import HTTPException, Arb
import json
from discord.utils import find
from .formating import arrow_color, period_info
from datetime import datetime


class BetClient:
    def __init__(self):
        self.regular_api_key: Optional[str] = None
        self.premium_api_key: Optional[str] = None
        self.session: Optional[ClientSession] = None
        self.directories = {}
        self.filters: List[Dict] = []
        self.pinnacle_id: int = 1
        with open("core/bet_burger_api/headers.json") as f:
            self.headers = json.load(f)
        with open("core/bet_burger_api/bookmakers.json") as f:
            bookmakers = json.load(f)
            self.bookmakers = {int(b['id']): b for b in bookmakers}
        with open("core/bet_burger_api/market_acronyms.json") as f:
            self.market_acronyms = json.load(f)

    async def connect(self, regular_api_key: str, premium_api_key: str):
        self.regular_api_key = regular_api_key
        self.premium_api_key = premium_api_key
        self.session = ClientSession()
        self.directories = await self.bet_burger_request("directories")

    async def bet_burger_request(self, endpoint: str, params: Optional[Dict] = None) -> Union[Dict, List[Dict]]:
        url = "https://api-pr.betburger.com/api/v1/{}".format(endpoint)
        params = params or {}
        params['access_token'] = self.regular_api_key
        params['locale'] = "en"
        async with self.session.get(url=url, params=params, headers=self.headers) as resp:
            if resp.ok:
                return await resp.json()
            error = f"Unable to access BetBurger API. Please check if the api key {self.regular_api_key} is valid.\n"
            error += await resp.text()
            raise HTTPException(error)

    async def get_premium_arbs(self) -> List[Arb]:
        params = {
            'apiKey': self.premium_api_key,
            'requiredBookmakerIds': [self.pinnacle_id],
            'grouped': 'false',
            'minPercent': 0.5,
            'limit': 100
        }
        bk_ids = ','.join([str(b) for b in self.bookmakers]) + f",{self.pinnacle_id}"
        url = f"https://api-pr.oddsmarket.org/v4/bookmakers/{bk_ids}/arbs"
        async with self.session.get(url=url, params=params) as resp:
            data = await resp.json()
        current_timestamp = int(datetime.utcnow().timestamp() * 1000)
        arbs = []
        for arb in data["arbs"].values():
            bets = []
            for bet_id in arb["betIds"]:
                bet = data["bets"][bet_id]
                bet["id"] = bet_id
                bet["bookmakerEvent"] = data["bookmakerEvents"][str(bet["bookmakerEventId"])]
                bets.append(bet)
            if bets[0]["bookmakerEvent"]["bookmakerId"] == self.pinnacle_id:
                bets.reverse()
            market_dir = find(lambda m: m['id'] == bets[0]["marketAndBetTypeId"], self.directories['market_variations'])
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

    async def get_bets(self, bet_id: str) -> List[Dict]:
        return await self.bet_burger_request(f"bets/{bet_id}/pro-same")

    async def close(self):
        await self.session.close()