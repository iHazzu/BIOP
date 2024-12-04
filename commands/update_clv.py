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
        logging.info(f"+ Updating clv odds of {link}...")
        logging.info(f"+ Getting cells to update in GoogleSheet...")
        cells = await bot.loop.run_in_executor(None, bot.orders_sheet.findall, link, None, 32)
        origin, clv_odds, pinn_odds, status = 0, 0, 0, "ERROR"
        try:
            if bet_id.startswith("analyzy-"):
                analyze_id = int(bet_id.split("-")[-1])
                logging.info(f"+ Getting clv odds in tipsportapi...")
                origin, clv_odds, status = await get_analyze_clv(analyze_id, bot)
            else:
                logging.info(f"+ Getting clv odds in BetBurger...")
                bets = await bot.bclient.same_bets(bet_id)
                clv_odds, pinn_odds = 0, 0
                for bet in bets:
                    if bet['bookmaker_id'] == bookmaker_id:
                        clv_odds = bet['koef']
                    if bet['bookmaker_id'] == bot.bclient.oposition_bookmaker_id:
                        pinn_odds = bet['koef']
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
            logging.info(f"+ Updating cells in Google Sheet...")
            await bot.loop.run_in_executor(None, bot.orders_sheet.update_cells, to_update)
        await bot.db.set("UPDATE orders SET clv_checked=True WHERE bet_id=%s", bet_id)
        logging.info(f"- Clv odds of {link} updated!")


async def analyzes(bot: Bot):
    data = await bot.db.get('''
        SELECT analyze_id, link
        FROM analyzes
        WHERE match_time < NOW() - INTERVAL 1 day AND NOT clv_checked
    ''')
    for analyze_id, link in data:
        logging.info(f"- Updating clv odds of {link}...")
        try:
            origin, clv_odds, status = await get_analyze_clv(analyze_id, bot)
        except NotFound as error:
            origin, clv_odds, status = 0, 0, "NOT_FOUND"
            logging.error(error)
        to_update = []
        cells = await bot.loop.run_in_executor(None, bot.tclient.analyzes_sheet.findall, link, None, 21)
        for cell in cells:
            to_update.append(Cell(cell.row, 10, origin))
            to_update.append(Cell(cell.row, 13, clv_odds))
            to_update.append(Cell(cell.row, 17, status))
        if to_update:
            await bot.loop.run_in_executor(None,  bot.tclient.analyzes_sheet.update_cells, to_update)
        await bot.db.set("UPDATE analyzes SET clv_checked=True WHERE analyze_id=%s", analyze_id)
        logging.info(f"- Clv odds of {link} updated!")


async def get_analyze_clv(analyze_id: int, bot: Bot) -> Tuple:
    analyze = await bot.tclient.get_analyze(analyze_id)
    origin = analyze["analyze"]["rate"]
    clv_odds = analyze["analyze"]["currentOpportunityRate"]
    status = analyze["ticketsWithAnalyzedOpportunity"][0]["key"]["status"]
    return origin, clv_odds, status