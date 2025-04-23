from .freegames import FreeGames

async def setup(bot):
    await bot.add_cog(FreeGames(bot))
