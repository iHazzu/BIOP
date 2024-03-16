import discord
from core import Arb, Interaction, Bot, HTTPException
from core.Utils import show_odd, prague_time
from typing import Optional
from datetime import datetime
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
        match_time = datetime.utcfromtimestamp(self.arb.start_at)
        updated_timedelta = (datetime.utcnow() - datetime.utcfromtimestamp(self.arb.upated_at))
        market = self.arb.market
        if self.arb.market_updated_at is not None:
            seconds = (datetime.utcnow() - self.arb.market_updated_at).seconds
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
            self.arb.oposition_odds,
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
            self.arb.link
        ]
        bot.worksheet.insert_row(values, 2)
        chance_odds = None
        if form.chance_odds.value:
            chance_odds = round(float(form.chance_odds.value), 2)
            value = 1 / (1 / chance_odds + 1 / self.arb.oposition_odds) - 1
            acceptance = format_acceptance(form.chance_acceptance.value)
            values[18], values[12], values[20], values[25] = value, chance_odds, "Chance", acceptance
            bot.worksheet.insert_row(values, 3)

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
        
        
async def update_orders(bot: Bot, start_time: datetime, end_time: datetime):
    data = await bot.db.get('''
        SELECT DISTINCT bet_id, bookmaker_id
        FROM orders
        WHERE match_time>=%s AND match_time<%s
    ''', start_time, end_time)
    for bet_id, bookmaker_id in data:
        cells = bot.worksheet.findall(f"{bet_id}/{bookmaker_id}", in_column=27)
        try:
            if bet_id.startswith("/analyzy/"):
                analyze_id = int(bet_id.split("/")[-1])
                bet = await bot.bclient.get_tipsport_analyze(analyze_id)
                clv_odds = bet["analyze"]["currentOpportunityRate"]
                status = bet["ticketsWithAnalyzedOpportunity"][0]["key"]["status"]
            else:
                bet = await bot.bclient.get_bet(bet_id)
                clv_odds = bet['odds']
                status = ""
        except HTTPException:
            clv_odds, status = "?", ""
        to_update = []
        for cell in cells:
            to_update.append(Cell(cell.row, 15, clv_odds))
            to_update.append(Cell(cell.row, 20, status))
        bot.worksheet.update_cells(to_update)


def format_acceptance(value: Optional[str]) -> Optional[str]:
    if value:
        acron = value.lower()
        for a in ACCEPTANCES:
            if a.startswith(acron):
                return a
    return value