from aiohttp import ClientSession
from typing import Optional, List
import json
from core.arbs_api import Arb
from core.Utils import prague_time, show_odd, execute_suppress
from asyncio import sleep


class SportBreakClient:
    def __init__(self):
        self.session: Optional[ClientSession] = None
        with open("core/sportbreak_api/sports.json") as f:
            self.sports = json.load(f)
        with open("core/sportbreak_api/countries.json") as f:
            self.countries = json.load(f)
        self.allowed_sports: List[str] = []

    async def connect(self, phpsessid: str, allowed_sports: str):
        with open("core/sportbreak_api/headers.json") as f:
            headers = json.load(f)
        cookies = {'PHPSESSID': phpsessid, 'default-cookie-consent-sent': '1', 'nette-samesite': '1'}
        self.session = ClientSession(headers=headers, cookies=cookies)
        self.allowed_sports = allowed_sports.split(",")

    async def publish(self, arb: Arb) -> None:
        match_url = arb.link
        if arb.bookmaker['id'] == 39:
            match_url = "https://www.tipsport.cz/vysledky?matchesFilter=" + match_url.split("=")[-1]
            await sleep(90)
        country_name, _, league_name = arb.league.partition(". ")
        home, _, guest = arb.event_name.partition(" - ")
        data = {
            'deposit': 500,
            'bettingShop': arb.bookmaker['bettingShop'],
            'servis': arb.bookmaker['servis'],
            'ticketComponents[0][id]': '',
            'ticketComponents[0][sport]': self.get_sport_id(arb.sport) or "1",
            'ticketComponents[0][date]': prague_time(arb.start_at).strftime("%d.%m.%Y %H:%M"),
            'ticketComponents[0][country]': self.get_country_id(country_name) or "wd",
            'ticketComponents[0][league]': league_name,
            'ticketComponents[0][home]': home,
            'ticketComponents[0][guest]': guest,
            'ticketComponents[0][tip]': arb.show_market_p(),
            'ticketComponents[0][course]': show_odd(arb.current_odds),
            'ticketComponents[0][matchUrl]': match_url,
            'saveAndGoBack': 'Save and go back',
            '_do': 'ticketForm-form-submit',
        }
        await execute_suppress(self.session.post("https://sportbreak.cz/a/tickets/add-ticket", data=data))

    def get_sport_id(self, sport_name: str) -> Optional[str]:
        return get_api_value(self.sports, sport_name)

    def get_country_id(self, country_name: str) -> Optional[str]:
        return get_api_value(self.countries, country_name)

    def is_allowed_sport(self, sport_name: str) -> bool:
        return self.get_sport_id(sport_name) in self.allowed_sports

    async def close(self):
        await self.session.close()


def get_api_value(data: dict, param: str) -> Optional[str]:
    param = param.upper()
    for k, v in data.items():
        if (isinstance(v, str) and param == v) or (isinstance(v, list) and param in v):
            return k
    return None