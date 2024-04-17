import json
from aiogoogle.models import Response
import base64
import re
from typing import Dict
from datetime import datetime
import pytz
from core.types import Arb


DIRECT_LINK_REGEX = re.compile(r'/analyzy/[^"]+')

with open("core/arbs_api/period_names.json") as file:
    period_names = json.load(file)


def arrow_color(diff: int, koef_last_modified_at: int, scanned_at: int) -> str:
    if not diff:
        return ""
    changed_timedelta = scanned_at - koef_last_modified_at
    if changed_timedelta > (10*60*1000):
        return "⇧Gray" if diff == 1 else "⇩Gray"
    elif diff == 1:
        return "⇧Green"
    else:
        return "⇩Red"


def period_info(sport_id: int, identifier: int) -> str:
    if identifier == -3:
        n = "match (doubles)"
    elif identifier == -2:
        n = "with overtime and shootouts" if sport_id in [6, 35] else "match"
    elif identifier == -1:
        n = "no_desc" if sport_id in [8, 13, 42] else "with overtime"
    elif identifier == 0:
        n = "no_desc" if sport_id in [1, 7, 8, 9, 11, 12, 13, 14, 21, 29] else "regular time"
    elif identifier == -100:
        n = "next round"
    elif sport_id == 11:
        n = f"{identifier} frame"
    elif sport_id == 32:
        n = f"{identifier} end"
    elif sport_id in [21, 46, 47, 48]:
        if identifier > 100:
            d, m = divmod(identifier, 100)
            if sport_id == 47 and m == 95:
                n = f"{d} map, regular time"
            else:
                n = f"{d} map, {m} round"
        else:
            n = f"{identifier} map"
    elif sport_id in [8, 9, 12, 13, 14, 29, 33, 38, 42]:
        if identifier > 100:
            d, m = divmod(identifier, 100)
            n = f"{d} set, {m} game"
        else:
            n = f"{identifier} set"
    elif sport_id in [6, 35, 36, 40]:
        n = f"{identifier} period"
    elif sport_id == 7:
        n = f"{identifier} time"
    elif sport_id in [1, 2, 10, 16, 19, 20, 34, 41]:
        if identifier in [10, 20]:
            n = f"{identifier/10} half"
        elif sport_id == 1:
            n = f"{identifier} inning"
        else:
            n = f"{identifier} quarter"
    elif sport_id == 22:
        n = f"{identifier} game"
    else:
        n = f"{identifier} half"
    return period_names.get(n, n)


def email_to_arb(email_data: Response, bookmaker: Dict) -> Arb:
    encoded_body = email_data["payload"]["parts"][0]["parts"][0]["parts"][0]["body"]["data"]
    email_body = base64.urlsafe_b64decode(encoded_body).decode('UTF8')
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
    league += to_separate[:i-1]
    event_name = to_separate[i:] + event_name
    start_prague = datetime.strptime(lines[6], "%d.%m.%Y %H:%M")
    start_utc = start_prague.replace(tzinfo=pytz.timezone("Europe/Prague")).astimezone(pytz.utc)
    start_at = int(start_utc.timestamp())
    updated_at = int(datetime.utcnow().timestamp())
    current_odds = float(lines[8].split(": ")[-1].replace(",", "."))
    lao = 0.97 * current_odds
    direct_link = DIRECT_LINK_REGEX.search(email_body).group()
    return Arb(
        direct_link, event_name, league, league, bookmaker, direct_link,
        start_at, updated_at, market, "", current_odds, 0, lao, "", "", author
    )
