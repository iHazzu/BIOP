from aiohttp import ClientSession
from typing import Optional
import json
from core.arbs_api import Arb
from core.Utils import prague_time, show_odd
from asyncio import sleep


class SportBreakClient:
    def __init__(self):
        self.session: Optional[ClientSession] = None
        with open("core/sportbreak_api/sports.json") as f:
            self.sports = json.load(f)
        with open("core/sportbreak_api/countries.json") as f:
            self.countries = json.load(f)

    async def connect(self, phpsessid: str):
        with open("core/sportbreak_api/headers.json") as f:
            headers = json.load(f)
        cookies = {'PHPSESSID': phpsessid, 'default-cookie-consent-sent': '1', 'nette-samesite': '1'}
        self.session = ClientSession(headers=headers, cookies=cookies)

    async def publish(self, arb: Arb) -> None:
        if arb.bookmaker[id] == 39:
            await sleep(90)
        country, _, league = arb.league.partition(". ")
        home, _, guest = arb.event_name.partition(" - ")
        data = {
            'deposit': 5000,
            'bettingShop': arb.bookmaker['bettingShop'],
            'servis': arb.bookmaker['servis'],
            'ticketComponents[0][id]': '',
            'ticketComponents[0][sport]': self.get_api_value(self.sports, arb.sport, "1"),
            'ticketComponents[0][date]': prague_time(arb.start_at).strftime("%d.%m.%Y %H:%M"),
            'ticketComponents[0][country]': self.get_api_value(self.countries, country, "wd"),
            'ticketComponents[0][league]': league,
            'ticketComponents[0][home]': home,
            'ticketComponents[0][guest]': guest,
            'ticketComponents[0][tip]': arb.show_market_p(),
            'ticketComponents[0][course]': show_odd(arb.current_odds),
            'ticketComponents[0][matchUrl]': arb.link,
            'saveAndGoBack': 'Save and go back',
            '_do': 'ticketForm-form-submit',
        }
        await self.session.post("https://sportbreak.cz/a/tickets/add-ticket", data=data)

    @staticmethod
    def get_api_value(data: dict, param: str, default: str) -> str:
        param = param.upper()
        for k, v in data.items():
            if (isinstance(v, str) and param == v) or (isinstance(v, list) and param in v):
                return k
        return default

    async def close(self):
        await self.session.close()