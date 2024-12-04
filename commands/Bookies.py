import discord
from core import Interaction
from typing import List, Optional


async def go(interaction: Interaction):
    user = interaction.user
    bot = interaction.client
    data = await bot.db.get("SELECT bookies FROM users WHERE user_id=%s", user.id)
    if not data:
        emb = discord.Embed(
            description=":warning: You first need to start the bot using the `/start` command.",
            colour=discord.Colour.red()
        )
        return await interaction.response.send_message(embed=emb)
    available_bookies = [b['name'] for b in bot.bclient.bookmakers.values()]
    available_bookies.append(bot.tclient.bookmaker['name'])
    previous_bookies = data[0][0].split(",") if data[0][0] else available_bookies
    options = []
    for bookie in available_bookies:
        selected = bookie in previous_bookies
        options.append(discord.SelectOption(label=bookie, default=selected))
    view = BookieSelector(options)
    emb = discord.Embed(
        title="Bookies Filter",
        description="Please select the bookies you wish to receive betting alerts from:",
        colour=discord.Colour.green()
    )
    await interaction.response.send_message(embed=emb, view=view)
    await view.wait()
    if view.interaction:
        new_bookies = ",".join(view.values)
        await bot.db.set("UPDATE users SET bookies=%s WHERE user_id=%s", new_bookies, user.id)
        emb = discord.Embed(
            description=f"✅ I will send you alerts from bookies: `{', '.join(view.values)}`.",
            colour=discord.Colour.green()
        )
        await view.interaction.response.edit_message(embed=emb, view=None)


class BookieSelector(discord.ui.View):
    def __init__(self, options: List[discord.SelectOption]):
        self.interaction: Optional[discord.Interaction] = None
        self.values: Optional[List[str]] = None
        super().__init__(timeout=200)
        self.children[0].options = options
        self.children[0].max_values = len(options)

    @discord.ui.select(placeholder="Select the desired bookies")
    async def select_bookies(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.interaction = interaction
        self.values = select.values
        self.stop()