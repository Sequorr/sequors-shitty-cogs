import discord 
import aiohttp
import time
from redbot.core import commands, Config, checks
from discord.ext.tasks import loop

STORE_NAMES = {
    "1": "Steam",
    "7": "GOG",
    "15": "Fanatical",
    "25": "Epic Games",
    "30": "IndieGala"
}

class FreeGames(commands.Cog):
    """Get free game deals from CheapShark."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        self.config.register_guild(
            post_channel=None, # Channel ID for posting free game deals
            enabled=True, # Whether or not the command is enabled
            steam_enabled=True, # Whether or not to include Steam deals
            epic_enabled=True, # Whether or not to include Epic Games deals
            gog_enabled=True, # Whether or not to include GOG deals
            indiegala_enabled=True, # Whether or not to include IndieGala deals
            fanatical_enabled=True, # Whether or not to include Fanatical deals
            last_check=0, # Timestamp of the last check
            last_deal=None, # Store the last deal ID to avoid duplicates
            ping_role=None # Optional role to ping when a new deal is found
        )

        self.auto_check_task.start()  # Start background loop here

    @loop(minutes=10)
    async def auto_check_task(self):
        for guild in self.bot.guilds:
            config = self.config.guild(guild)
            enabled = await config.enabled()
            channel_id = await config.post_channel()

            if not enabled or channel_id is None:
                continue

            now = int(time.time())
            last_check = await config.last_check()

            # Only run if it's been at least 3 hours (10800 seconds)
            if now - last_check < 10800:
                continue

            # Get enabled store IDs
            store_ids = []
            if await config.steam_enabled(): store_ids.append("1")
            if await config.gog_enabled(): store_ids.append("7")
            if await config.fanatical_enabled(): store_ids.append("15")
            if await config.epic_enabled(): store_ids.append("25")
            if await config.indiegala_enabled(): store_ids.append("30")

            if not store_ids:
                continue

            api_url = f"https://www.cheapshark.com/api/1.0/deals?storeID={','.join(store_ids)}&upperPrice=0"

            async with aiohttp.ClientSession() as session:
                async with session.get(api_url) as response:
                    if response.status != 200:
                        continue
                    deals = await response.json()

            if not deals:
                continue

            # Skip if it's a repeat of the last deal
            game = deals[0]
            last_posted = await config.last_deal()
            if game["dealID"] == last_posted:
                continue  # We've already posted this one

            # Post in the configured channel
            channel = guild.get_channel(channel_id)
            if channel is None:
                continue

            store_name = STORE_NAMES.get(game["storeID"], "Unknown Store")
            embed = discord.Embed(
                title="🎮 Free Game Alert!",
                description=f"[{game['title']}](https://www.cheapshark.com/redirect?dealID={game['dealID']}) is free right now on **{store_name}**!",
                color=discord.Color.green()
            )
            embed.set_thumbnail(url=game["thumb"])
            embed.set_footer(text="Next check in 3 hours.")

            ping_id = await config.ping_role()
            ping_text = f"<@&{ping_id}>" if ping_id else None
            if ping_text:
                await channel.send(
                    content=ping_text,
                    embed=embed,
                    allowed_mentions=discord.AllowedMentions(roles=True)
                )
            else:
                await channel.send(embed=embed)
            await config.last_check.set(now)
            await config.last_deal.set(game["dealID"])  # Save dealID to avoid duplicates


    @commands.group(invoke_without_command=True)
    async def freegames(self, ctx):
        """Get free game deals from CheapShark."""
        await ctx.send("Use `[p]help freegames` to get started.")
    
    @freegames.command(name="toggle")
    async def toggle_check(self, ctx):
        """Enable or disable deal checking. When enabled, fetches and posts current free games."""
        config = self.config.guild(ctx.guild)
        currently_enabled = await config.enabled()
        new_state = not currently_enabled
        await config.enabled.set(new_state)

        if new_state:
            # Check which stores are enabled
            store_ids = []
            if await config.steam_enabled(): store_ids.append("1")
            if await config.gog_enabled(): store_ids.append("7")
            if await config.fanatical_enabled(): store_ids.append("15")
            if await config.epic_enabled(): store_ids.append("25")
            if await config.indiegala_enabled(): store_ids.append("30")

            if not store_ids:
                await ctx.send("⚠ No stores are currently enabled. Use `[p]freegames <store>` to enable some.")
                return

            # Make the API call
            api_url = f"https://www.cheapshark.com/api/1.0/deals?storeID={','.join(store_ids)}&upperPrice=0"

            async with aiohttp.ClientSession() as session:
                async with session.get(api_url) as response:
                    if response.status != 200:
                        await ctx.send("⚠ Failed to fetch game deals from CheapShark.")
                        return
                    deals = await response.json()

            if not deals:
                await ctx.send("✅ Enabled free game checks, but no free games were found at the moment.")
                return

            # Post the top result
            embed = discord.Embed(
                title="🎮 Free Game Found!",
                description="Here’s a currently free game from your enabled stores.",
                color=discord.Color.green()
            )
            game = deals[0]
            store_name = STORE_NAMES.get(game["storeID"], "Unknown Store")
            embed.add_field(
                name=f"{game['title']} [{store_name}]",
                value=f"[View Deal](https://www.cheapshark.com/redirect?dealID={game['dealID']})"
            )
            embed.set_thumbnail(url=game["thumb"])
            embed.set_footer(text="Use [p]freegames again to toggle off.")

            await ctx.send("✅ Free game checks are now **enabled**.")
            await ctx.send(embed=embed)

        else:
            await ctx.send("🛑 Free game checks are now **disabled**.")

    @freegames.command(name="channel")
    async def set_or_view_channel(self, ctx, channel: discord.TextChannel = None):
        """Set or view the current channel for free game posts."""
        current = await self.config.guild(ctx.guild).post_channel()

        if channel is None:
            if current is None:
                await ctx.send("⚠ No channel has been set yet. Use `[p]freegames channel #channel` to set one.")
            else:
                channel_obj = ctx.guild.get_channel(current)
                if channel_obj:
                    await ctx.send(f"📌 Free game deals will be posted in: {channel_obj.mention}")
                else:
                    await ctx.send("⚠ A channel was set previously, but I can't find it. Please set a new one.")
        else:
            await self.config.guild(ctx.guild).post_channel.set(channel.id)
            if current is None:
                await ctx.send(f"✅ Free game posts will now go to {channel.mention}.")
            else:
                await ctx.send(f"🔄 Updated! Free game posts will now go to {channel.mention} (was <#{current}>).")

    @freegames.command()
    async def steam(self, ctx):
        """Toggle whether Steam deals are included."""
        current = await self.config.guild(ctx.guild).steam_enabled()
        new_state = not current
        await self.config.guild(ctx.guild).steam_enabled.set(new_state)
        await ctx.send("✅ Steam: Enabled" if new_state else "❌ Steam: Disabled")

    @freegames.command()
    async def epic(self, ctx):
        """Toggle whether Epic Games deals are included."""
        current = await self.config.guild(ctx.guild).epic_enabled()
        new_state = not current
        await self.config.guild(ctx.guild).epic_enabled.set(new_state)
        await ctx.send("✅ Epic Games: Enabled" if new_state else "❌ Epic Games: Disabled")

    @freegames.command()
    async def gog(self, ctx):
        """Toggle whether GOG deals are included."""
        current = await self.config.guild(ctx.guild).gog_enabled()
        new_state = not current
        await self.config.guild(ctx.guild).gog_enabled.set(new_state)
        await ctx.send("✅ GOG: Enabled" if new_state else "❌ GOG: Disabled")

    @freegames.command()
    async def indiegala(self, ctx):
        """Toggle whether IndieGala deals are included."""
        current = await self.config.guild(ctx.guild).indiegala_enabled()
        new_state = not current
        await self.config.guild(ctx.guild).indiegala_enabled.set(new_state)
        await ctx.send("✅ IndieGala: Enabled" if new_state else "❌ IndieGala: Disabled")

    @freegames.command()
    async def fanatical(self, ctx):
        """Toggle whether Fanatical deals are included."""
        current = await self.config.guild(ctx.guild).fanatical_enabled()
        new_state = not current
        await self.config.guild(ctx.guild).fanatical_enabled.set(new_state)
        await ctx.send("✅ Fanatical: Enabled" if new_state else "❌ Fanatical: Disabled")
    
    @freegames.command()
    @checks.is_owner()
    async def ping_role(self, ctx, role: discord.Role = None):
        """Set or clear the role to ping when free games are posted (bot owner only)."""
        config = self.config.guild(ctx.guild)
        if role is None:
            current = await config.ping_role()
            if current:
                role_obj = ctx.guild.get_role(current)
                if role_obj:
                    await ctx.send(f"📎 Current ping role: {role_obj.mention}")
                else:
                    await ctx.send("⚠ Ping role is set but I can't find it. You may want to set a new one.")
            else:
                await ctx.send("ℹ No ping role is currently set.")
            return
        
        await config.ping_role.set(role.id)
        await ctx.send(f"✅ Ping role set to {role.mention}. This role will be pinged when new free games are posted.")


    @freegames.command(name="check")
    @commands.admin_or_permissions(administrator=True)
    async def manual_check(self, ctx):
        """(Admin only) Immediately fetch and post current free games."""
        config = self.config.guild(ctx.guild)
        channel_id = await config.post_channel()
        channel = ctx.guild.get_channel(channel_id) if channel_id else ctx.channel

        store_ids = []
        if await config.steam_enabled(): store_ids.append("1")
        if await config.gog_enabled(): store_ids.append("7")
        if await config.fanatical_enabled(): store_ids.append("15")
        if await config.epic_enabled(): store_ids.append("25")
        if await config.indiegala_enabled(): store_ids.append("30")

        if not store_ids:
            await ctx.send("⚠ No stores are currently enabled. Use `[p]freegames <store>` to enable them.")
            return

        api_url = f"https://www.cheapshark.com/api/1.0/deals?storeID={','.join(store_ids)}&upperPrice=0"

        async with aiohttp.ClientSession() as session:
            async with session.get(api_url) as response:
                if response.status != 200:
                    await ctx.send("⚠ Failed to fetch game deals from CheapShark.")
                    return
                deals = await response.json()

        if not deals:
            await ctx.send("No free games found at the moment.")
            return

        game = deals[0]
        last_posted = await config.last_deal()
        if game["dealID"] == last_posted:
            await ctx.send("📌 No new free games since the last check.")
            return
        
        store_name = STORE_NAMES.get(game["storeID"], "Unknown Store")

        embed = discord.Embed(
            title="🎮 Free Game Check",
            description=f"[{game['title']}](https://www.cheapshark.com/redirect?dealID={game['dealID']}) is currently free on **{store_name}**!",
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=game["thumb"])
        embed.set_footer(text="Use [p]freegames <store> to manage sources.")

        await channel.send(embed=embed)
        await config.last_deal.set(game["dealID"])  # Store this one to prevent future repeats
