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
from gspread import Spreadsheet, Worksheet
from . import helper as h

DIRECT_LINK_REGEX = re.compile(r'/analyzy/[^"]+')


class TipsportClient:
    def __init__(self):
        self.email_analyzes: List[Arb] = []
        self.google: Optional[Aiogoogle] = None
        self.gmail: Optional[GoogleAPI] = None
        self.last_seen_message: Optional[str] = None
        self.db: Optional[DataBase] = None
        self.analyzes_sheet: Optional[Worksheet] = None
        self.calculation_sheet: Optional[Worksheet] = None
        with open("core/tipsport_api/bookmaker.json") as f:
            self.bookmaker = json.load(f)
        with open("core/tipsport_api/headers.json") as f:
            self.headers = json.load(f)

    async def connect(self, db: DataBase, spreadsheet: Spreadsheet):
        self.db = db
        self.analyzes_sheet = spreadsheet.worksheet('Analyzes')
        self.calculation_sheet = spreadsheet.worksheet('Calculation')
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
            arb = await self.load_analyze_data(email_data)
            if arb not in self.email_analyzes:
                self.save_analyze(arb)
                self.email_analyzes.append(arb)
        return self.email_analyzes

    async def load_analyze_data(self, email_data: Response) -> Arb:
        encoded_body = email_data["payload"]["parts"][0]["parts"][0]["parts"][0]["body"]["data"]
        email_body = base64.urlsafe_b64decode(encoded_body).decode('UTF8')
        direct_link = DIRECT_LINK_REGEX.search(email_body).group()
        analyze_id = int(direct_link.split("/")[-1])
        try:
            response = await self.get_analyze(analyze_id)
        except HTTPException as error:
            logging.warning(f"{error.text}. Loading analyze data from email.")
            return h.load_analyze_from_email(email_body, direct_link, self.bookmaker)
        else:
            return h.load_analyze_from_api(response, direct_link, self.bookmaker)

    def save_and_evaluate_analyze(self, arb: Arb) -> bool:
        cell = self.calculation_sheet.find(arb.analysis_author.upper(), in_column=1)
        values = h.arb_to_sheet_values(arb)
        self.analyzes_sheet.insert_row(values=values, index=2, value_input_option="USER_ENTERED")

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