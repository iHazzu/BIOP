from aiohttp import ClientSession
from typing import List, Optional, Dict, Union
from .types import HTTPException, Arb
import json
from discord.utils import find
from random import choice
from .formating import arrow_color, period_info, bk_koefs_filter
from datetime import datetime


API_URL = "https://{}.betburger.com/api/v1/{}"
SAZKA = {'name': 'Sazka', 'id': 308, 'url': "https://www.sazka.cz/kurzove-sazky/sports/event/"}


class BetClient:
    def __init__(self):
        self.api_keys: List[str] = []
        self.premium_api_key: Optional[str] = None
        self.session: Optional[ClientSession] = None
        self.directories = {}
        self.filters: List[Dict] = []
        self.bookmakers = {}
        self.oposition_bookmaker_id: Optional[int] = None
        with open("core/bet_burger_api/headers.json") as f:
            self.headers = json.load(f)
        with open("core/bet_burger_api/market_acronyms.json") as f:
            self.market_acronyms = json.load(f)

    async def connect(self, api_keys: List[str], premium_api_key: str):
        self.api_keys = api_keys
        self.premium_api_key = premium_api_key
        self.session = ClientSession()
        self.directories = await self._make_request("directories", self.api_keys[0])
        for api_key in self.api_keys:
            account_filters = await self._make_request("search_filters", api_key)
            bk_configs = (await self._make_request("user_bookmakers", api_key))["bookmakers"]
            bot_filter = find(lambda f: f['title'].startswith("BOT"), account_filters)
            bot_filter['api_key'] = api_key
            bot_filter['bookmakers_koefs'] = []
            self.filters.append(bot_filter)
            self.oposition_bookmaker_id = int(bot_filter['bookmakers2'][0])
            for bookmaker_id in bot_filter["bookmakers1"]:
                bookmaker_id = int(bookmaker_id)
                if bookmaker_id == self.oposition_bookmaker_id:
                    continue
                bookmaker = find(lambda b: b['id'] == bookmaker_id, self.directories["bookmakers"]["arbs"])
                bk_config = find(lambda b: b['bookmaker_id'] == bookmaker_id, bk_configs)
                bookmaker_koefs = bk_koefs_filter(bk_config)
                if bookmaker_koefs:
                    bot_filter['bookmakers_koefs'].append(bookmaker_koefs)
                self.bookmakers[bookmaker_id] = bookmaker
        self.bookmakers[SAZKA['id']] = SAZKA

    async def _make_request(
            self, endpoint: str, api_key: str,
            params: Optional[Dict] = None, domain="api-pr"
    ) -> Union[Dict, List[Dict]]:
        url = API_URL.format(domain, endpoint)
        params = params or {}
        params['access_token'] = api_key
        params['locale'] = "en"
        async with self.session.get(url=url, params=params, headers=self.headers) as resp:
            if resp.ok:
                return await resp.json()
            error = f"Unable to access BetBurger API. Please check if the api key {api_key} is valid.\n"
            error += await resp.text()
            raise HTTPException(error)

    async def get_regular_arbs(self) -> List[Arb]:
        arbs = []
        for fil in self.filters:
            params = {'search_filter[]': [fil['id']], 'per_page': 20, 'grouped': 'True'}
            if fil['bookmakers_koefs']:
                params['bookmaker_koefs'] = ",".join(fil['bookmakers_koefs'])
            data = await self._make_request("arbs/pro_search", fil['api_key'], params, domain="rest-api-pr")
            for a in data["arbs"]:
                bet1 = find(lambda b: b['id'] == a['bet1_id'], data["bets"])
                bet2 = find(lambda b: b['id'] == a['bet2_id'], data["bets"])
                if bet1['bookmaker_id'] == self.oposition_bookmaker_id:
                    bet1, bet2 = bet2, bet1
                sport = find(lambda m: m['id'] == a['sport_id'], self.directories['sports'])
                market_dir = find(lambda m: m['id'] == bet1['market_and_bet_type'], self.directories['market_variations'])
                market_text_model = self.market_acronyms[market_dir['title']]
                market = market_text_model.replace("%s", str(bet1['market_and_bet_type_param']))
                period_dir = find(lambda m: m['id'] == bet1['period_id'], self.directories['periods'])
                arb = Arb(
                    bet_id=bet1['id'],
                    event_name=bet1['event_name'],
                    sport=sport['name'],
                    league=bet1['league_name'],
                    bookmaker=self.bookmakers[bet1['bookmaker_id']],
                    direct_link=bet1['bookmaker_event_direct_link'],
                    start_timestamp=a['started_at'],
                    updated_timestamp=a['updated_at'],
                    market=market,
                    period=period_info(sport['id'], int(period_dir['identifier'])),
                    current_odds=bet1['koef'],
                    oposition_odds=bet2['koef'],
                    arrow=arrow_color(bet1['diff'], bet1['koef_last_modified_at'], bet1['scanned_at']),
                    oposition_arrow=arrow_color(bet2['diff'], bet2['koef_last_modified_at'], bet2['scanned_at'])
                )
                if arb not in arbs:
                    arbs.append(arb)
        return arbs

    async def get_premium_arbs(self) -> List[Arb]:
        params = {
            'apiKey': self.premium_api_key,
            'requiredBookmakerIds': [self.oposition_bookmaker_id],
            'grouped': 'true',
            'minPercent': 0.5
        }
        bk_ids = f"{self.oposition_bookmaker_id},{SAZKA['id']}"
        url = f"https://api-lv.oddsmarket.org/v4/bookmakers/{bk_ids}/arbs"
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
            if bets[0]["bookmakerEvent"]["bookmakerId"] == self.oposition_bookmaker_id:
                bets.reverse()
            market_dir = find(lambda m: m['id'] == bets[0]["marketAndBetTypeId"], self.directories['market_variations'])
            market_text_model = self.market_acronyms[market_dir["title"]]
            market = market_text_model.replace("%s", str(bets[0]["marketAndBetTypeParam"]))
            event = data["events"][str(arb["eventId"])]
            league = data["leagues"][str(event["leagueId"])]
            sport = data["sports"][str(league["sportId"])]
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
                bookmaker=self.bookmakers[bets[0]["bookmakerEvent"]["bookmakerId"]],
                direct_link=bets[0]["bookmakerEvent"]["rawId"],
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
        return await self._make_request(f"bets/{bet_id}/pro-same", choice(self.api_keys))

    async def close(self):
        await self.session.close()