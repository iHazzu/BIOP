from core import Bot, HTTPException
from typing import Tuple
from gspread import Cell


async def orders(bot: Bot):
    data = await bot.db.get('''
        SELECT DISTINCT bet_id, link
        FROM orders
        WHERE NOT clv_checked AND 
        match_time < CASE WHEN bet_id LIKE %s THEN NOW() - INTERVAL 1 day ELSE NOW() + INTERVAL 1 minute END
    ''', "analyzy-%")
    for bet_id, link in data:
        cells = bot.orders_sheet.findall(link, in_column=33)
        origin, clv_odds, status = 0, 0, ""
        try:
            if bet_id.startswith("analyzy-"):
                analyze_id = int(bet_id.split("-")[-1])
                origin, clv_odds, status = await get_analyze_clv(analyze_id, bot)
            else:
                bet = await bot.oclient.get_bet(bet_id)
                clv_odds = bet['odds']
        except HTTPException:
            pass
        to_update = []
        for cell in cells:
            to_update.append(Cell(cell.row, 17, clv_odds))
            if bet_id.startswith("analyzy-"):
                to_update.append(Cell(cell.row, 12, origin))
                to_update.append(Cell(cell.row, 24, status))
        if to_update:
            bot.orders_sheet.update_cells(to_update)
        await bot.db.set("UPDATE orders SET clv_checked=True WHERE bet_id=%s", bet_id)


async def analyzes(bot: Bot):
    data = await bot.db.get('''
        SELECT analyze_id, link
        FROM analyzes
        WHERE match_time < NOW() - INTERVAL 1 day AND NOT clv_checked
    ''')
    for analyze_id, link in data:
        origin, clv_odds, status = await get_analyze_clv(analyze_id, bot)
        to_update = []
        cells = bot.tclient.analyzes_sheet.findall(link, in_column=21)
        for cell in cells:
            to_update.append(Cell(cell.row, 10, origin))
            to_update.append(Cell(cell.row, 13, clv_odds))
            to_update.append(Cell(cell.row, 17, status))
        if to_update:
            bot.tclient.analyzes_sheet.update_cells(to_update)
        await bot.db.set("UPDATE analyzes SET clv_checked=True WHERE analyze_id=%s", analyze_id)


async def get_analyze_clv(analyze_id: int, bot: Bot) -> Tuple:
    analyze = await bot.tclient.get_analyze(analyze_id)
    origin = analyze["analyze"]["rate"]
    clv_odds = analyze["analyze"]["currentOpportunityRate"]
    status = analyze["ticketsWithAnalyzedOpportunity"][0]["key"]["status"]
    return origin, clv_odds, status