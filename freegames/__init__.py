from .freegames import FreeGames

async def setup(bot):
    bot.add_cog(FreeGames(bot))
