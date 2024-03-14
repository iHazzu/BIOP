from aiohttp import ClientSession
from typing import List, Optional, Dict
from .types import HTTPException, Arb
from discord.utils import find
from .formating import arrow_color, period_info, email_to_arb
from datetime import datetime
import json
from aiogoogle import Aiogoogle, GoogleAPI


class BetClient:
    def __init__(self):
        self.api_key: Optional[str] = None
        self.session: Optional[ClientSession] = None
        self.tipsport_session: Optional[ClientSession] = None
        self.market_and_bets: Dict = {}
        self.filters: List[Dict] = []
        self.pinnacle_id: int = 1
        self.email_arbs: List[Arb] = []
        self.google: Optional[Aiogoogle] = None
        self.gmail: Optional[GoogleAPI] = None
        self.last_seen_message: Optional[str] = None
        with open("core/arbs_api/bookmakers.json") as f:
            bookmakers = json.load(f)
            self.bookmakers = {int(b['id']): b for b in bookmakers}
        with open("core/arbs_api/market_acronyms.json") as f:
            self.market_acronyms = json.load(f)

    async def connect(self, api_key: str, jsession_id: str):
        self.api_key = api_key
        self.session = ClientSession()
        self.market_and_bets = await self.make_request("https://api-mst.oddsmarket.org/v4/market_and_bet_types")
        with open("gmail_credentials.json", "r") as file:
            creds = json.load(file)
        async with Aiogoogle(user_creds=creds['user'], client_creds=creds['client']) as self.google:
            self.gmail = await self.google.discover("gmail", "v1")
        response = await self.google.as_user(
            self.gmail.users.messages.list(userId="me", q="from:(analyzy@tipsport.cz)", maxResults=1)
        )
        self.last_seen_message = response["messages"][0]["id"]
        with open("core/arbs_api/tipsport_headers.json") as file:
            cookie = {'JSESSIONID': jsession_id}
            self.tipsport_session = ClientSession(headers=json.load(file), cookies=cookie)
        await self.ping_tipsport_session()

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
        await self.update_email_arbs()
        return arbs + self.email_arbs

    async def get_bet(self, bet_id: str) -> Dict:
        url = f"https://api-pr.oddsmarket.org/v4/bookmakers/arbs/bets/{bet_id}"
        return await self.make_request(url)

    async def update_email_arbs(self) -> None:
        current_timestamp = int(datetime.utcnow().timestamp())
        self.email_arbs = [a for a in self.email_arbs if (current_timestamp-a.upated_at) < 10*60]
        response = await self.google.as_user(
            self.gmail.users.messages.list(userId="me", q="from:(analyzy@tipsport.cz)", maxResults=10)
        )
        for message in response["messages"]:
            if message["id"] == self.last_seen_message:
                break
            email_data = await self.google.as_user(self.gmail.users.messages.get(userId="me", id=message["id"]))
            self.email_arbs.append(email_to_arb(email_data, self.bookmakers[39]))
        self.last_seen_message = response["messages"][0]["id"]

    async def ping_tipsport_session(self):
        params = {'key': 'ZEK_INFO_GENERIC'}
        url = 'https://www.tipsport.cz/rest/common/v1/texts'
        resp = await self.tipsport_session.get(url=url, params=params)
        if resp.status == 401:
            raise HTTPException("Tipsport JSESSIONID expired.")

    async def get_tipsport_analisys(self, analisys_id: int) -> Dict:
        url = f"https://www.tipsport.cz/rest/analyses/v1/analysis/{analisys_id}"
        async with self.tipsport_session.get(url) as resp:
            if resp.status == 401:
                raise HTTPException("Tipsport JSESSIONID expired.")
            return await resp.json()

    async def close(self):
        await self.session.close()