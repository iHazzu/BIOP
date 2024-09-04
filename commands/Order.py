import discord
from core import Arb, Interaction, PRAGUE
from core.utils import show_odd
from typing import Optional
from datetime import datetime, UTC
from contextlib import suppress
from os import environ as env
import logging


PLACED_ORDER_TITLE = ":large_orange_diamond: BET PLACED"
ACCEPTANCES = ["instantly accepted", "accepted after a delay", "rejected", "unknown", "odds already dropped"]
NET_RESULTS = '=SWITCH(X2, "WON", 100*({0}-1), "LOST", -100, "VOID", 0, "HALF_WON", 50*({0}-1), "HALF_LOST", -50, "∄")'
BOOKIE_DROP = '=IF(Q2<>0, (Q2-{0})/{0}, "∄")'
PINN_DROP = '=IF(T2<>0, (T2-{0})/{0}, "∄")'
ODDS_BOOKMAKERS = [int(bk) for bk in env["CORRECT_ODDS_BOOKMAKERS"].split(",")]


class PlaceOrder(discord.ui.View):
    def __init__(self, arb: Arb):
        super().__init__(timeout=None)
        self.arb = arb

    @discord.ui.button(emoji="💶", label="Place Order", style=discord.ButtonStyle.blurple)
    async def place_order(self, interaction: Interaction, button: discord.ui.Button):
        bot = interaction.client
        user = interaction.user
        logging.info(f"Placing order of {user} in event {self.arb.slug}...")
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
        updated_timedelta = (datetime.now(UTC) - self.arb.updated_at)
        market = self.arb.market
        values = [
            str(user),  # username
            self.arb.analysis_author or "",
            interaction.created_at.astimezone(PRAGUE).strftime("%d/%m/%Y %H:%M:%S"),
            self.arb.start_at.astimezone(PRAGUE).strftime("%d/%m/%Y %H:%M:%S"),
            "=D2-C2",  # time to event (empty)
            self.arb.sport,
            self.arb.league,
            self.arb.event_name,
            market,
            self.arb.period,
            self.arb.current_odds,
            self.arb.origin_odds,
            self.arb.oposition_odds,
            self.arb.last_acceptable_odds,
            placed_odds,
            stake_amount,
            0,  # bookie clv
            BOOKIE_DROP.format("O2"),
            BOOKIE_DROP.format("N2"),
            0,  # pinacle clv,
            PINN_DROP.format("O2"),
            PINN_DROP.format("N2"),
            value,
            "",  # status
            NET_RESULTS.format("O2"),
            NET_RESULTS.format("N2"),
            self.arb.bookmaker['name'],
            self.arb.arrow,
            self.arb.oposition_arrow,
            updated_timedelta.seconds,
            acceptance,
            self.arb.event_link
        ]
        if self.arb.analysis_author:
            values.extend([" " for _ in ODDS_BOOKMAKERS])
        else:
            logging.info(f"Getting correct bookmakers odds...")
            other_odds = await bot.oclient.same_bets(self.arb.oposition_bet_id, ODDS_BOOKMAKERS)
            for bk in ODDS_BOOKMAKERS:
                if other_odds:
                    values.append(other_odds.get(str(bk), {}).get("odds", " "))
                else:
                    values.append(" ")
        logging.info(f"Saving {self.arb.bookmaker['name']} order into ReportsSheet...")
        await bot.loop.run_in_executor(
            None,
            bot.orders_sheet.insert_row,
            values, 2, "USER_ENTERED"
        )

        chance_odds = None
        if form.chance_odds.value:
            chance_odds = round(float(form.chance_odds.value), 2)
            value = 1 / (1 / chance_odds + 1 / self.arb.oposition_odds) - 1
            acceptance = format_acceptance(form.chance_acceptance.value)
            values[14], values[22], values[26], values[30] = chance_odds, value, "Chance", acceptance
            print(f"Saving Chance order into ReportsSheet...")
            await bot.loop.run_in_executor(
                None,
                bot.orders_sheet.insert_row,
                values, 3, "USER_ENTERED"
            )

        await bot.db.set('''
            INSERT INTO orders(user_id, bet_id, bookmaker_id, match_time, slug, link)
            VALUES (%s, %s, %s, %s, %s, %s)
        ''', user.id, self.arb.bet_id, self.arb.bookmaker['id'], self.arb.start_at, self.arb.slug, self.arb.event_link)
        if stake_amount != last_stake_amount:
            method = "JSON_INSERT" if last_stake_amount is None else "JSON_SET"
            await bot.db.set(f'''
                UPDATE users
                SET stake_amount={method}(stake_amount, '$.{self.arb.bookmaker["name"]}', %s)
                WHERE user_id=%s
            ''', stake_amount, user.id)

        logging.info("Editing bet message...")
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
        logging.info(f"Order sucessfully placed.")
        await form.interaction.followup.send(embed=emb)

    @discord.ui.button(emoji="📑", label="Copy Text", style=discord.ButtonStyle.gray)
    async def copy_bet_text(self, interaction: Interaction, button: discord.ui.Button):
        text = f"- Zápas: {self.arb.event_name}"
        text += f"\n- Čas: {self.arb.start_at.astimezone(PRAGUE).strftime("%d.%m.%Y %H:%M")} (GMT+2)"
        text += f"\n- Sport: {self.arb.sport}"
        text += f"\n\nJakmile najdeš přímý odkaz, pokračuj následujícím způsobem:"
        text += f"\n\n1. Použij pouze data z této stránky pro následující úkol."
        text += f"\n2. Napiš krátkou analýzu, proč je výhodné vsadit na následující sázku:"
        text += f"\n- Zápas: {self.arb.event_name}"
        text += f"\n- Čas: {self.arb.start_at.strftime("%d.%m.%Y %H:%M")} (GMT+0)"
        text += f"\n- Sport: {self.arb.sport}"
        text += f"\n- Liga: {self.arb.league}"
        text += f"\n- Typ sázky: {self.arb.market} {self.arb.period}"
        text += f"\n- Kurz: {show_odd(self.arb.current_odds)}"
        await interaction.response.send_message(f"```\n{text}\n```", ephemeral=True)


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
        if arb.bookmaker['id'] == 39:
            self.chance_odds.default = show_odd(arb.current_odds)
        else:
            self.remove_item(self.chance_odds)
            self.remove_item(self.chance_acceptance)
        if default_stake:
            self.stake_amount.default = f"{default_stake:.2f}"
        self.interaction: Optional[Interaction] = None
        for i, item in enumerate(self.children):
            item.label = f"{i+1}. {item.label}"

    async def on_submit(self, interaction: Interaction):
        self.interaction = interaction


def format_acceptance(value: Optional[str]) -> Optional[str]:
    if value:
        acron = value.lower()
        for a in ACCEPTANCES:
            if a.startswith(acron):
                return a
    return value