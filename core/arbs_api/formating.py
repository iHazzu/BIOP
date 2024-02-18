import json
from typing import Optional, Dict


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


def bk_koefs_filter(bk_data: Optional[Dict]) -> Optional[str]:
    values = [0 if bk_data[k] is None else bk_data[k] for k in ['bookmaker_id', 'min_odds', 'max_odds', 'min_sum']]
    return "-".join(str(v) for v in values) if any(values[1:]) else None