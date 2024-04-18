from typing import List, Optional, Dict
from aiohttp import ClientSession
from core.types import HTTPException, Arb
from core.database import DataBase
from datetime import datetime, UTC
import json
from aiogoogle import Aiogoogle, GoogleAPI
from aiohttp_socks import ProxyConnector
import logging
from aiogoogle.models import Response
import base64
import re
import pytz

DIRECT_LINK_REGEX = re.compile(r'/analyzy/[^"]+')


class TipsportClient:
    def __init__(self):
        self.email_analyzes: List[Arb] = []
        self.google: Optional[Aiogoogle] = None
        self.gmail: Optional[GoogleAPI] = None
        self.last_seen_message: Optional[str] = None
        self.db: Optional[DataBase] = None
        with open("core/oddsmarket_api/bookmakers.json") as f:
            bookmakers = json.load(f)
            self.bookmaker: Dict = next(b for b in bookmakers if b["id"] == 39)
        with open("core/tipsport_api/headers.json") as f:
            self.headers = json.load(f)

    async def connect(self, db: DataBase):
        self.db = db
        with open("core/tipsport_api/gmail_credentials.json", "r") as file:
            creds = json.load(file)
        async with Aiogoogle(user_creds=creds['user'], client_creds=creds['client']) as self.google:
            self.gmail = await self.google.discover("gmail", "v1")
        last_messages = await self.get_last_mail_messages()
        self.last_seen_message = last_messages[0]["id"]

    async def get_email_analyzes(self) -> List[Arb]:
        current_timestamp = int(datetime.now(UTC).timestamp())
        for analyze in self.email_analyzes[::]:
            if (current_timestamp - analyze.upated_at) > 10 * 60:
                self.email_analyzes.remove(analyze)
        messages = await self.get_last_mail_messages()
        stop_message = self.last_seen_message
        self.last_seen_message = messages[0]["id"]
        for message in messages:
            if message["id"] == stop_message:
                break
            email_data = await self.google.as_user(self.gmail.users.messages.get(userId="me", id=message["id"]))
            arb = await self.load_analyze_data(email_data, current_timestamp)
            if arb not in self.email_analyzes:
                self.email_analyzes.append(arb)
        return self.email_analyzes

    async def load_analyze_data(self, email_data: Response, updated_at: int) -> Arb:
        encoded_body = email_data["payload"]["parts"][0]["parts"][0]["parts"][0]["body"]["data"]
        email_body = base64.urlsafe_b64decode(encoded_body).decode('UTF8')
        direct_link = DIRECT_LINK_REGEX.search(email_body).group()
        analyze_id = int(direct_link.split("/")[-1])
        try:
            analyze = (await self.get_analyze(analyze_id))["analyze"]
        except HTTPException as error:
            logging.warning(f"{error.text}. Loading analyze data from email.")
            lines = email_body.split("<br/>")
            author = lines[4].split(": ")[-1]
            s = " - "  # separator
            parts = lines[5].split(s)
            i = next(i for i, w in enumerate(parts) if i > 0 and w[0].isupper()) + 1
            parts, market = parts[:i], s.join(parts[i:])
            if len(parts) == 1:
                league, event_name, to_separate = "", "", parts[0]
            elif len(parts) == 2:
                league, event_name, to_separate = "", s + parts[1], parts[0]
            else:
                league, event_name, to_separate = parts[0] + s, s + parts[2], parts[1]
            i = next(i for i, c in enumerate(to_separate) if i > 0 and c.isupper())
            event_name = to_separate[i:] + event_name
            league += to_separate[:i - 1]
            start_prague = datetime.strptime(lines[6], "%d.%m.%Y %H:%M")
            start_utc = start_prague.replace(tzinfo=pytz.timezone("Europe/Prague")).astimezone(pytz.utc)
            start_at = int(start_utc.timestamp())
            current_odds = float(lines[8].split(": ")[-1].replace(",", "."))
            return Arb(
                bet_id=direct_link, event_name=event_name,
                sport=league, league=league,
                bookmaker=self.bookmaker, event_direct_link=direct_link,
                start_timestamp=start_at, updated_timestamp=updated_at,
                market=market, current_odds=current_odds,
                analysis_author=author
            )
        else:
            start_time = datetime.strptime(analyze["dateClosedMillis"], "%Y-%m-%dT%H:%M:%S.%f%z")
            start_at = int(start_time.timestamp())
            market = analyze["eventName"] + " - " + analyze["opportunityName"]
            return Arb(
                bet_id=direct_link, event_name=analyze["matchNameFull"],
                sport=analyze["superSportName"], league=analyze["competitionName"],
                bookmaker=self.bookmaker, event_direct_link=direct_link,
                start_timestamp=start_at, updated_timestamp=updated_at,
                market=market, current_odds=analyze["currentOpportunityRate"],
                origin_odds=analyze["rate"], analysis_author=analyze["avatar"]["username"]
            )

    async def get_analyze(self, analyze_id: int) -> Dict:
        url = f"https://www.tipsport.cz/rest/analyses/v1/analysis/{analyze_id}"
        data = await self.db.get("SELECT session_id, proxy FROM browser WHERE id=1")
        cookies = {'JSESSIONID': data[0][0]}
        connector = ProxyConnector.from_url(data[0][1])
        async with ClientSession(headers=self.headers, cookies=cookies, connector=connector) as session:
            async with session.get(url) as resp:
                if resp.ok:
                    return await resp.json()
                elif resp.status == 401:
                    msg = "Tipsport JSESSIONID expired"
                elif resp.status == 403:
                    msg = "Cloudflare is blocking the bot from accessing the Tipsport API"
                else:
                    msg = await resp.text()
                raise HTTPException(msg)

    async def get_last_mail_messages(self) -> List:
        response = await self.google.as_user(
            self.gmail.users.messages.list(userId="me", q="from:(analyzy@tipsport.cz)", maxResults=5)
        )
        return response["messages"]