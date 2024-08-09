from core import Bot, HTTPException, NotFound
from typing import Tuple
from gspread import Cell
import logging


async def orders(bot: Bot):
    data = await bot.db.get('''
        SELECT DISTINCT bet_id, link, bookmaker_id
        FROM orders
        WHERE NOT clv_checked AND 
        match_time < CASE WHEN bet_id LIKE %s THEN NOW() - INTERVAL 1 day ELSE NOW() + INTERVAL 1 minute END
    ''', "analyzy-%")
    for bet_id, link, bookmaker_id in data:
        cells = bot.orders_sheet.findall(link, in_column=33)
        origin, clv_odds, pinn_odds, status = 0, 0, 0, "ERROR"
        try:
            if bet_id.startswith("analyzy-"):
                analyze_id = int(bet_id.split("-")[-1])
                origin, clv_odds, status = await get_analyze_clv(analyze_id, bot)
            else:
                bookies_odds = await bot.oclient.same_bets(bet_id, [bot.oclient.pinnacle_id, bookmaker_id])
                if not bookies_odds:
                    continue
                pinn_odds = bookies_odds[str(bot.oclient.pinnacle_id)].get("odds", 0)
                clv_odds = bookies_odds[str(bookmaker_id)].get("odds", 0)
        except (HTTPException, NotFound):
            pass
        to_update = []
        for cell in cells:
            to_update.append(Cell(cell.row, 17, clv_odds))
            if bet_id.startswith("analyzy-"):
                to_update.append(Cell(cell.row, 12, origin))
                to_update.append(Cell(cell.row, 24, status))
            else:
                to_update.append(Cell(cell.row, 20, pinn_odds))
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
        try:
            origin, clv_odds, status = await get_analyze_clv(analyze_id, bot)
        except NotFound as error:
            origin, clv_odds, status = 0, 0, "NOT_FOUND"
            logging.error(error)
        to_update = []
        cells = bot.tclient.analyzes_sheet.findall(link, in_column=21)
        for cell in cells:
            to_update.append(Cell(cell.row, 10, origin))
            to_update.append(Cell(cell.row, 13, clv_odds))
            to_update.append(Cell(cell.row, 17, status))
        if to_update:
            bot.tclient.analyzes_sheet.update_cells(to_update)
        await bot.db.set("UPDATE analyzes SET clv_checked=True WHERE analyze_id=%s", analyze_id)


async def research(bot: Bot):
    data = await bot.db.get('''
        SELECT DISTINCT bet_id
        FROM research
        WHERE NOT clv_checked AND match_time < NOW() + INTERVAL 1 minute
    ''')
    for bet_id, in data:
        cells = bot.rclient.worksheet.findall(bet_id, in_column=17)
        try:
            bet = await bot.rclient.get_bet(bet_id)
            clv_odds = bet['odds']
        except HTTPException:
            clv_odds = 0.00
        to_update = []
        for cell in cells:
            to_update.append(Cell(cell.row, 11, clv_odds))
        if to_update:
            bot.rclient.worksheet.update_cells(to_update)
        await bot.db.set("UPDATE research SET clv_checked=True WHERE bet_id=%s", bet_id)


async def get_analyze_clv(analyze_id: int, bot: Bot) -> Tuple:
    analyze = await bot.tclient.get_analyze(analyze_id)
    origin = analyze["analyze"]["rate"]
    clv_odds = analyze["analyze"]["currentOpportunityRate"]
    status = analyze["ticketsWithAnalyzedOpportunity"][0]["key"]["status"]
    return origin, clv_odds, status