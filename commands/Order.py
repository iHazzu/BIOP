import discord
from core import Arb, Interaction, Bot, HTTPException
from core.utils import show_odd, prague_time
from typing import Optional, Tuple
from datetime import datetime, UTC, timedelta
from gspread import Cell
from contextlib import suppress

PLACED_ORDER_TITLE = ":large_orange_diamond: BET PLACED"
ACCEPTANCES = ["instantly accepted", "accepted after a delay", "rejected", "unknown", "odds already dropped"]


class PlaceOrder(discord.ui.View):
    def __init__(self, arb: Arb):
        super().__init__(timeout=None)
        self.arb = arb

    @discord.ui.button(emoji="💶", label="Place Order", style=discord.ButtonStyle.blurple)
    async def place_order(self, interaction: Interaction, button: discord.ui.Button):
        bot = interaction.client
        user = interaction.user
        data = await bot.db.get(f'''
            SELECT JSON_EXTRACT(stake_amount, '$.{self.arb.bookmaker["name"]}')
            FROM users
            WHERE user_id=%s
        ''', user.id)
        if not data:
            return

        last_stake_amount = data[0][0]
        if last_stake_amount:
            last_stake_amount = float(last_stake_amount)
        form = OrderForm(self.arb, last_stake_amount)
        try:
            await interaction.response.send_modal(form)
        except discord.NotFound:
            return
        await form.wait()
        if not form.interaction:
            return
        await form.interaction.response.defer()

        placed_odds = round(float(form.bookie_odds.value), 2)
        stake_amount = round(float(form.stake_amount.value), 2)
        acceptance = format_acceptance(form.bookie_acceptance.value)
        value = self.arb.arb_value(placed_odds, self.arb.oposition_odds)/100
        match_time = datetime.fromtimestamp(self.arb.start_at, UTC)
        updated_timedelta = (datetime.now(UTC) - datetime.fromtimestamp(self.arb.upated_at, UTC))
        market = self.arb.market
        if self.arb.market_updated_at is not None:
            seconds = (datetime.now(UTC) - self.arb.market_updated_at).seconds
            if seconds < 120:
                market += f" ◕{seconds}"
        values = [
            str(user),  # username
            prague_time(interaction.created_at).strftime("%d.%m.%Y %H:%M:%S"),
            prague_time(match_time).strftime("%d.%m.%Y %H:%M:%S"),
            "",  # time to event (empty)
            self.arb.sport,
            self.arb.league,
            self.arb.event_name,
            market,
            self.arb.analysis_author or self.arb.period,
            self.arb.current_odds,
            self.arb.origin_odds or "",
            self.arb.oposition_odds or "",
            self.arb.last_acceptable_odds,
            placed_odds,
            stake_amount,
            "",  # soft bookie clv (empty)
            "",  # soft bookie drop (empty)
            "",  # pinn clv (empty)
            "",  # pinn drop (empty)
            value,
            "",  # status (empty)
            self.arb.bookmaker['name'],
            self.arb.arrow,
            self.arb.oposition_arrow,
            updated_timedelta.seconds,
            "No" if self.arb.disappeared_at is None else "Yes",  # after deletion
            acceptance,
            f"{self.arb.bet_id}/{self.arb.bookmaker['id']}",
            self.arb.event_link
        ]
        bot.orders_sheet.insert_row(values=values, index=2)
        chance_odds = None
        if form.chance_odds.value:
            chance_odds = round(float(form.chance_odds.value), 2)
            value = 1 / (1 / chance_odds + 1 / self.arb.oposition_odds) - 1
            acceptance = format_acceptance(form.chance_acceptance.value)
            values[19], values[13], values[21], values[26] = value, chance_odds, "Chance", acceptance
            bot.orders_sheet.insert_row(values=values, index=3)

        await bot.db.set('''
            INSERT INTO orders(user_id, bet_id, bookmaker_id, match_time, slug)
            VALUES (%s, %s, %s, %s, %s)
        ''', user.id, self.arb.bet_id, self.arb.bookmaker['id'], match_time, self.arb.slug)
        if stake_amount != last_stake_amount:
            method = "JSON_INSERT" if last_stake_amount is None else "JSON_SET"
            await bot.db.set(f'''
                UPDATE users
                SET stake_amount={method}(stake_amount, '$.{self.arb.bookmaker["name"]}', %s)
                WHERE user_id=%s
            ''', stake_amount, user.id)

        bet_message = await bot.fetch_message(interaction.message.channel.id, interaction.message.id)
        bet_emb = bet_message.embeds[0]
        bet_emb.title = PLACED_ORDER_TITLE
        button.disabled = True
        with suppress(discord.NotFound):
            bot.messages[interaction.message.id] = await interaction.message.edit(embed=bet_emb, view=self)

        emb = discord.Embed(
            title=f"✅ Your bet was saved!",
            description=f"{self.arb.event_name} | {self.arb.bookmaker['name']}",
            colour=discord.Colour.green()
        )
        emb.add_field(name="Placed Odds", value=show_odd(placed_odds), inline=True)
        if chance_odds:
            emb.add_field(name="Chance Odds", value=show_odd(chance_odds), inline=True)
        emb.add_field(name="Amount", value=f"{stake_amount:.2f}", inline=True)
        emb.add_field(name="Value (Edge)", value=f"{show_odd(100*value)}%", inline=True)
        emb.add_field(name="Market", value=self.arb.show_market_p(), inline=True)
        await form.interaction.followup.send(embed=emb)


class OrderForm(discord.ui.Modal):
    bookie_odds = discord.ui.TextInput(
        label="Bookie placed odds",
        style=discord.TextStyle.short,
    )
    stake_amount = discord.ui.TextInput(
        label=f"Stake amount placed",
        style=discord.TextStyle.short,
    )
    bookie_acceptance = discord.ui.TextInput(
        label=f"Bookie acceptance",
        style=discord.TextStyle.short,
        required=False,
        placeholder="None"
    )
    chance_odds = discord.ui.TextInput(
        label=f"Chance placed odds",
        style=discord.TextStyle.short,
        required=False,
        placeholder="None"
    )
    chance_acceptance = discord.ui.TextInput(
        label=f"Chance acceptance",
        style=discord.TextStyle.short,
        required=False,
        placeholder="None"
    )

    def __init__(self, arb: Arb, default_stake: Optional[float]):
        super().__init__(title=f"PLACE ORDER", timeout=120)
        self.bookie_odds.label = self.bookie_odds.label.replace("Bookie", arb.bookmaker['name'])
        self.bookie_acceptance.label = self.bookie_acceptance.label.replace("Bookie", arb.bookmaker['name'])
        self.bookie_odds.default = show_odd(arb.current_odds)
        if arb.bookmaker['id'] != 39 or arb.analysis_author:
            self.remove_item(self.chance_odds)
            self.remove_item(self.chance_acceptance)
        if default_stake:
            self.stake_amount.default = f"{default_stake:.2f}"
        self.interaction: Optional[Interaction] = None
        for i, item in enumerate(self.children):
            item.label = f"{i+1}. {item.label}"

    async def on_submit(self, interaction: Interaction):
        self.interaction = interaction
        
        
async def orders_clv(bot: Bot):
    data = await bot.db.get('''
        SELECT DISTINCT bet_id, bookmaker_id
        FROM orders
        WHERE NOT clv_checked AND 
        match_time < CASE WHEN bet_id LIKE %s THEN NOW() - INTERVAL 12 hour ELSE NOW() + INTERVAL 1 minute END
    ''', "analyzy-%")
    for bet_id, bookmaker_id in data:
        cells = bot.orders_sheet.findall(f"{bet_id}/{bookmaker_id}", in_column=28)
        origin, status, clv_odds = "", "", "?"
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
            to_update.append(Cell(cell.row, 16, clv_odds))
            if bet_id.startswith("analyzy-"):
                to_update.append(Cell(cell.row, 11, origin))
                to_update.append(Cell(cell.row, 21, status))
        bot.orders_sheet.update_cells(to_update)
        await bot.db.set("UPDATE orders SET clv_checked=True WHERE bet_id=%s", bet_id)


async def analyzes_clv(bot: Bot):
    ago_time = datetime.now(UTC) - timedelta(hours=12)
    ago_time = int(ago_time.timestamp())
    data = await bot.db.get('''
        SELECT DISTINCT link
        FROM history
        WHERE link LIKE %s AND start_at BETWEEN %s AND %s
    ''', "%/analyzy/%", ago_time, ago_time + 30)
    for link in data:
        analyze_id = int(link.split("/")[-1])
        try:
            origin, clv_odds, status = await get_analyze_clv(analyze_id, bot)
        except HTTPException:
            origin, status, clv_odds = "", "", "?"
        to_update = []
        cells = bot.tclient.analyzes_sheet.findall(link, in_column=17)
        for cell in cells:
            to_update.append(Cell(cell.row, 10, origin))
            to_update.append(Cell(cell.row, 12, clv_odds))
            to_update.append(Cell(cell.row, 14, status))
        bot.tclient.analyzes_sheet.update_cells(to_update)


def format_acceptance(value: Optional[str]) -> Optional[str]:
    if value:
        acron = value.lower()
        for a in ACCEPTANCES:
            if a.startswith(acron):
                return a
    return value


async def get_analyze_clv(analyze_id: int, bot: Bot) -> Tuple:
    analyze = await bot.tclient.get_analyze(analyze_id)
    origin = analyze["analyze"]["rate"]
    clv_odds = analyze["analyze"]["currentOpportunityRate"]
    status = analyze["ticketsWithAnalyzedOpportunity"][0]["key"]["status"]
    return origin, clv_odds, status