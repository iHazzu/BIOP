from core.types import Arb
from core.constants import PRAGUE
from datetime import datetime, UTC
import pytz
from typing import Dict, List

NET_RESULTS = '=SWITCH(Q2, "WON", 100*({0}-1), "LOST", -100, "VOID", 0, "HALF_WON", 50*({0}-1), "HALF_LOST", -50, "∄")'
BOOKIE_DROP = '=IF(M2<>0, (M2-{0})/{0}, "∄")'

with open("core/tipsport_api/sports.txt") as f:
    sports = f.read().split("\n")


def load_analyze_from_email(email_body: str, direct_link: str, bookmaker: Dict) -> Arb:
    bet_id = f"analyzy-{int(direct_link.split("/")[-1])}"
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
    sport = extract_sport(direct_link)
    start_prague = datetime.strptime(lines[6], "%d.%m.%Y %H:%M")
    updated_at = datetime.now(UTC)
    start_utc = start_prague.replace(tzinfo=pytz.timezone("Europe/Prague")).astimezone(pytz.utc)
    current_odds = float(lines[8].split(": ")[-1].replace(",", "."))
    return Arb(
        bet_id=bet_id, event_name=event_name,
        sport=sport, league=league,
        bookmaker=bookmaker, event_direct_link=direct_link,
        start_at=start_utc, updated_at=updated_at,
        market=market, current_odds=current_odds,
        analysis_author=author
    )


def load_analyze_from_api(reponse: Dict, direct_link: str, bookmaker: Dict) -> Arb:
    analyze = reponse["analyze"]
    bet_id = f"analyzy-{analyze['id']}"
    start_time = datetime.strptime(analyze["dateClosedMillis"], "%Y-%m-%dT%H:%M:%S.%f%z")
    updated_at = datetime.now(UTC)
    market = analyze["eventName"] + " - " + analyze["opportunityName"]
    return Arb(
        bet_id=bet_id, event_name=analyze["matchNameFull"],
        sport=analyze["superSportName"], league=analyze["competitionName"],
        bookmaker=bookmaker, event_direct_link=direct_link,
        start_at=start_time, updated_at=updated_at,
        market=market, current_odds=analyze["currentOpportunityRate"],
        origin_odds=analyze["rate"], analysis_author=analyze["avatar"]["username"]
    )


def extract_sport(link: str) -> str:
    argument = link.split("/")[-2].replace("-", " ")
    matched = []
    for sport in sports:
        if argument.startswith(sport):
            matched.append(sport)
    if matched:
        matched = sorted(matched, key=lambda s: len(s), reverse=True)
        sport = matched[0]
    else:
        sport = argument.split(" ")[0]
    return sport.capitalize()


def arb_to_sheet_values(arb: Arb) -> List:
    return [
        arb.analysis_author,
        arb.updated_at.astimezone(PRAGUE).strftime("%d/%m/%Y %H:%M:%S"),
        arb.start_at.astimezone(PRAGUE).strftime("%d/%m/%Y %H:%M:%S"),
        "=C2-B2",  # Time To Event
        arb.sport,
        arb.league,
        arb.event_name,
        arb.market,
        arb.current_odds,
        arb.origin_odds,
        arb.lao_percent,
        arb.last_acceptable_odds,
        0,  # Bookie CLV
        BOOKIE_DROP.format("I2"),  # Bookie Drop Sent Odds
        BOOKIE_DROP.format("J2"),  # Bookie Drop Origin
        BOOKIE_DROP.format("L2"),  # Bookie Drop LAO
        "",  # Status
        NET_RESULTS.format("I2"),
        NET_RESULTS.format("J2"),
        NET_RESULTS.format("L2"),
        arb.event_link,
        "=ROUNDDOWN(TODAY() - B2)"
    ]
