from curl_cffi.requests import AsyncSession
from typing import List, Optional, Dict, Union
from core.types import HTTPException, Arb
import json
from discord.utils import find
from . import helper as h
from datetime import datetime, UTC
import logging


API_URL = "https://{}.betburger.com/api/v1/{}"


class BetClient:
    def __init__(self):
        self.api_key: Optional[str] = None
        self.session: Optional[AsyncSession] = None
        self.directories = {}
        self.filters: List[Dict] = []
        self.oposition_bookmaker_id: int = 1
        self.bookmakers: Dict[int, Dict] = {}
        self.get_arbs_req_count = 0
        with open("core/betburger_api/headers.json") as f:
            self.headers = json.load(f)

    async def connect(self, api_key: str):
        self.api_key = api_key
        self.session = AsyncSession(headers=self.headers, impersonate="chrome120")
        logging.warning("Connecting to BetBurger API...")
        self.directories = await self._make_request("directories")
        account_filters = await self._make_request("search_filters")
        bk_configs = (await self._make_request("user_bookmakers"))["bookmakers"]
        for fil in account_filters:
            fil['bookmakers_koefs'] = []
            self.filters.append(fil)
            for bookmaker_id in fil["bookmakers1"]:
                bookmaker_id = int(bookmaker_id)
                if bookmaker_id == self.oposition_bookmaker_id:
                    continue
                bookmaker = find(lambda b: b['id'] == bookmaker_id, self.directories["bookmakers"]["arbs"])
                bk_config = find(lambda b: b['bookmaker_id'] == bookmaker_id, bk_configs)
                bookmaker_koefs = h.bk_koefs_filter(bk_config)
                if bookmaker_koefs:
                    fil['bookmakers_koefs'].append(bookmaker_koefs)
                self.bookmakers[bookmaker_id] = bookmaker
        h.fix_bookmakers(self.bookmakers)

    async def _make_request(self, endpoint: str, params: Optional[Dict] = None, domain="api-pr") -> Union[Dict, List[Dict]]:
        url = API_URL.format(domain, endpoint)
        params = params or {}
        params['access_token'] = self.api_key
        params['locale'] = 'en'
        resp = await self.session.get(url=url, params=params, headers=self.headers)
        if resp.ok:
            return resp.json()
        elif resp.status_code in [401, 422]:
            text = "Unable to access BetBurger. Please check that your BETBURGER_APIKEY is still valid."
            raise HTTPException(text)
        else:
            text = f"{resp.status_code} Response Error\n{resp.text}"
            text += f"\nUrl: {url}\nParams: {params}"
            raise HTTPException(text)

    async def get_arbs(self) -> List[Arb]:
        fil = self.filters[self.get_arbs_req_count % len(self.filters)]
        logging.info(f"- Getting arbs from filter {fil['title']}...")
        self.get_arbs_req_count += 1
        arbs = []
        params = {
            'search_filter[]': [fil['id']],
            'per_page': 20,
            'grouped': 'True',
            'auto_update': 'True',
            'notification_sound': 'False',
            'notification_popup': 'True',
            'show_event_arbs': 'True',
            'sort_by': 'percent',
            'koef_format': 'decimal',
        }
        if fil['bookmakers_koefs']:
            params['bookmaker_koefs'] = ",".join(fil['bookmakers_koefs'])
        data = await self._make_request("arbs/pro_search", params, domain="rest-api-pr")
        for a in data["arbs"]:
            bet1 = find(lambda b: b['id'] == a['bet1_id'], data["bets"])
            bet2 = find(lambda b: b['id'] == a['bet2_id'], data["bets"])
            if bet1['bookmaker_id'] == self.oposition_bookmaker_id:
                bet1, bet2 = bet2, bet1
            sport = find(lambda m: m['id'] == a['sport_id'], self.directories['sports'])
            market, period = h.format_market_period(bet1, self.directories, sport)
            start_at = datetime.fromtimestamp(a["started_at"], UTC)
            updated_at = datetime.fromtimestamp(a["updated_at"], UTC)
            arb = Arb(
                bet_id=bet1["id"],
                oposition_bet_id=bet2["id"],
                event_name=bet1['event_name'],
                sport=sport['name'],
                league=bet1['league_name'],
                bookmaker=self.bookmakers[bet1['bookmaker_id']],
                event_direct_link=bet1['raw_id'],
                start_at=start_at,
                updated_at=updated_at,
                market=market,
                period=period,
                current_odds=bet1["koef"],
                oposition_odds=bet2["koef"],
                arrow=h.arrow_color(bet1['diff'], bet1["koef_last_modified_at"], bet1['scanned_at']),
                oposition_arrow=h.arrow_color(bet2['diff'], bet2["koef_last_modified_at"], bet2['scanned_at']),
                bet_direct_link=None,
                bet_data=bet1
            )
            if arb not in arbs:
                arbs.append(arb)
        logging.info(f"-- {len(arbs)} arbs found in filter {fil['title']}.")
        return arbs

    async def same_bets(self, bet_id: str) -> List[Dict]:
        try:
            return await self._make_request(f"bets/{bet_id}/pro-same")
        except HTTPException:
            return []

    async def close(self):
        await self.session.close()