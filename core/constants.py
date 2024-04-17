import discord


class Embeds:
    @classmethod
    def green(cls, description: str = "") -> discord.Embed:
        return discord.Embed(colour=3853362, description=description)

    @classmethod
    def yellow(cls, description: str = "") -> discord.Embed:
        return discord.Embed(colour=16627968, description=description)

    @classmethod
    def red(cls, description: str = "") -> discord.Embed:
        return discord.Embed(colour=16711680, description=description)

    @classmethod
    def blue(cls, description: str = "") -> discord.Embed:
        return discord.Embed(colour=52479, description=description)