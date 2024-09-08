import logging
from aiohttp import ClientSession
from typing import List, Optional, Dict
from core.types import HTTPException, Arb
from discord.utils import find
from .helper import arrow_color, period_info
from datetime import datetime, UTC
import json


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
        with open("core/oddsmarket_api/filters.json") as f:
            self.filters = json.load(f)
            for qfilter in self.filters:
                qfilter["excluded_bet_ids"] = []
        with open(f"core/oddsmarket_api/feed_size.txt", "w") as file:
            file.write(f"BOT STARTED")

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

    async def get_arbs_per_filter(self, qfilter: dict) -> List[Arb]:
        params = {
            'requiredBookmakerIds': [self.pinnacle_id],
            'grouped': 'false',
            'minPercent': qfilter['min_value'],
            'maxEventStartOffsetTime': qfilter['hours_until_event_starts'] * 60 * 60 * 1000,
            'limit': 100
        }
        if qfilter['sport_ids']:
            params["sportIds"] = qfilter['sport_ids']
        bk_ids = f"{self.pinnacle_id}"
        for bk_id in qfilter['bookmaker_ids']:
            bk_ids += f",{bk_id}"
        if qfilter['excluded_bet_ids']:
            params['excludedBetIds'] = ",".join(qfilter["excluded_bet_ids"])
        url = f"https://api-pr.oddsmarket.org/v4/bookmakers/{bk_ids}/arbs"
        data = await self.make_request(url, params)
        if "arbs" not in data:
            return []
        arbs = []
        bet_ids = []
        for arb in data["arbs"].values():
            bets = []
            for bet_id in arb["betIds"]:
                bet = data["bets"][bet_id]
                bet["id"] = bet_id
                bet["bookmakerEvent"] = data["bookmakerEvents"][str(bet["bookmakerEventId"])]
                bets.append(bet)
            if bets[0]["bookmakerEvent"]["bookmakerId"] == self.pinnacle_id:
                bets.reverse()
            bet_ids.append(bets[0]["id"])
            if bets[0]["odds"] > qfilter["max_odds"]:
                continue
            market_dir = find(lambda m: m['id'] == bets[0]["marketAndBetTypeId"], self.market_and_bets)
            market_text_model = self.market_acronyms[market_dir["title"]]
            market = market_text_model.replace("%s", str(bets[0]["marketAndBetTypeParam"]))
            event = data["events"][str(arb["eventId"])]
            league = data["leagues"][str(event["leagueId"])]
            sport = data["sports"][str(league["sportId"])]
            bookmaker = self.bookmakers[bets[0]["bookmakerEvent"]["bookmakerId"]]
            start_at = datetime.fromtimestamp(event["startDatetime"] / 1000, UTC)
            updated_at = datetime.fromtimestamp(bets[0]["updatedAt"] / 1000, UTC)
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
            if arb not in arbs:
                arbs.append(arb)
        logging.info(f"-- {len(bet_ids)} arbs found in filter {qfilter['name']}.")
        if qfilter['exclude_bets'] and bet_ids:
            qfilter['excluded_bet_ids'] = (bet_ids + qfilter['excluded_bet_ids'])[:200]
        return arbs

    async def get_arbs(self) -> List[Arb]:
        arbs = []
        for qfilter in self.filters:
            arbs += await self.get_arbs_per_filter(qfilter)
        return arbs

    async def same_bets(self, bet_id: str, bookmaker_ids: List[int]) -> Optional[Dict]:
        params = {'betId': bet_id, 'bookmakerIds': bookmaker_ids}
        url = "https://api-pr.oddsmarket.org/v4/same_bets_by_betid"
        try:
            data = await self.make_request(url, params)
            return data.get("responseData")
        except HTTPException as error:
            logging.error(error)
            return None

    async def close(self):
        await self.session.close()