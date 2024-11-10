# libraries thing
import discord
from discord.ext import commands
from discord.utils import format_dt
import aiosqlite
import asyncio
import os
from dotenv import load_dotenv, dotenv_values
load_dotenv()

class MyBot(commands.Bot):
    async def setup_hook(self):
        await bot.tree.sync()

bot = MyBot(command_prefix='!', intents=discord.Intents.all())
# what bot says in output when it goes online 
@bot.event
async def on_ready():
    print("Bot is online.")
    setattr(bot, "db", await aiosqlite.connect('starboard.db'))
    await asyncio.sleep(2)
    async with bot.db.cursor() as cursor:
        await cursor.execute("""
            CREATE TABLE IF NOT EXISTS starSetup (
                starLimit INTEGER,
                channel INTEGER,
                guild INTEGER
            )
        """)
        await cursor.execute("""
            CREATE TABLE IF NOT EXISTS starboardMessages (
                original_message_id INTEGER PRIMARY KEY,
                starboard_message_id INTEGER,
                guild_id INTEGER
            )
        """)
    await bot.db.commit()
# id of emoji (change for the real dumb emoji when bot gets in server)
custom_emoji = "<:dumb:1304750621135474708>"
# if reaction added then bot adds it
@bot.event
async def on_raw_reaction_add(payload):
    await handle_reaction(payload, is_add=True)
# if reaction removed then bot removes
@bot.event
async def on_raw_reaction_remove(payload):
    await handle_reaction(payload, is_add=False)
# this section is for the message itself that gets added to #dumbboard
async def handle_reaction(payload, is_add):
    emoji = payload.emoji
    guild = bot.get_guild(payload.guild_id)
    channel = guild.get_channel(payload.channel_id)
    message = await channel.fetch_message(payload.message_id)

    if emoji.id == 1304750621135474708:
        async with bot.db.cursor() as cursor:
            await cursor.execute("SELECT starLimit, channel FROM starSetup WHERE guild = ?", (guild.id,))
            data = await cursor.fetchall()

            if data:
                starData = data[0][0]
                channel_ids = [entry[1] for entry in data]

                for channel_id in channel_ids:
                    starboard_channel = guild.get_channel(channel_id)

                    if starboard_channel is None:
                        await cursor.execute("DELETE FROM starSetup WHERE guild = ? AND channel = ?", (guild.id, channel_id))
                        await bot.db.commit()
                        continue

                    for reaction in message.reactions:
                        if reaction.emoji.id == 1304750621135474708:
                            await cursor.execute("SELECT starboard_message_id FROM starboardMessages WHERE guild_id = ? AND original_message_id = ?", 
                                                 (guild.id, message.id))
                            starboard_entry = await cursor.fetchone()

                            if reaction.count >= starData:
                                message_link = f"https://discord.com/channels/{guild.id}/{channel.id}/{message.id}"
                                message_time = message.created_at.strftime('%Y-%m-%d %H:%M:%S')

                                embed = discord.Embed(
                                    description=f"{message.content}\n\n**Source**\n[Jump]({message_link})",
                                    color=discord.Color.blurple()
                                )
                                if message.attachments:
                                    embed.set_image(url=message.attachments[0].url)
                                embed.set_author(name=message.author.display_name, icon_url=message.author.avatar.url)
                                embed.set_footer(text=f"{message.id}")

                                if starboard_entry:
                                    # this edits the msg if it already exists
                                    starboard_msg_id = starboard_entry[0]
                                    try:
                                        starboard_message = await starboard_channel.fetch_message(starboard_msg_id)
                                        await starboard_message.edit(content=f"{custom_emoji} **{reaction.count}** {message.channel.mention}", embed=embed)
                                    except discord.errors.NotFound:
                                        # if msg is deleted remove from database
                                        await cursor.execute("DELETE FROM starboardMessages WHERE original_message_id = ?", (message.id,))
                                        await bot.db.commit()
                                else:
                                    # create new message
                                    starboard_message = await starboard_channel.send(
                                        content=f"{custom_emoji} **{reaction.count}** {message.channel.mention}",
                                        embed=embed
                                    )
                                    await cursor.execute("INSERT INTO starboardMessages (original_message_id, starboard_message_id, guild_id) VALUES (?, ?, ?)", 
                                                         (message.id, starboard_message.id, guild.id))
                                    await bot.db.commit()

                            elif reaction.count < starData and starboard_entry:
                                # this deletes the msg if reactions are less than threshold
                                starboard_msg_id = starboard_entry[0]
                                try:
                                    starboard_message = await starboard_channel.fetch_message(starboard_msg_id)
                                    await starboard_message.delete()
                                except discord.errors.NotFound:
                                    pass
                                await cursor.execute("DELETE FROM starboardMessages WHERE original_message_id = ?", (message.id,))
                                await bot.db.commit()


# /setup-channel command (cant figure out how to add space without error why why why why)
@bot.tree.command(name="setup-channel", description="set up the dumbboard channel")
@discord.app_commands.checks.has_permissions(manage_guild=True)
async def setup_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    try:
        async with bot.db.cursor() as cursor:
            await cursor.execute("SELECT channel FROM starSetup WHERE guild = ?", (interaction.guild.id,))
            channelData = await cursor.fetchone()
            if channelData and channelData[0] == channel.id:
                await interaction.response.send_message("That channel is already set up!", ephemeral=True)
            else:
                await cursor.execute("REPLACE INTO starSetup (starLimit, channel, guild) VALUES (?, ?, ?)", 
                                     (2, channel.id, interaction.guild.id))
                await bot.db.commit()
                await interaction.response.send_message(f"{channel.mention} is now the dumbboard channel!")
    except discord.errors.Forbidden:
        await interaction.response.send_message(
            "I don't have permission to set up this channel. Please check my permissions.",
            ephemeral=True
        )
# /setup reaction count command
@bot.tree.command(name="setup-reaction-count", description="set threshold of reactions for dumbboard")
@discord.app_commands.checks.has_permissions(manage_guild=True)
async def setup_stars(interaction: discord.Interaction, star: int):
    try:
        async with bot.db.cursor() as cursor:
            await cursor.execute("SELECT channel FROM starSetup WHERE guild = ?", (interaction.guild.id,))
            data = await cursor.fetchone()

            if data is None:
                default_channel_id = 0
                await cursor.execute("INSERT INTO starSetup (starLimit, channel, guild) VALUES (?, ?, ?)", 
                                     (star, default_channel_id, interaction.guild.id))
            else:
                await cursor.execute("UPDATE starSetup SET starLimit = ? WHERE guild = ?", 
                                     (star, interaction.guild.id))

            await bot.db.commit()
            await interaction.response.send_message(f"{star} is now the reaction limit!")
    except discord.errors.Forbidden:
        await interaction.response.send_message(
            "I have missing permissions. please check my permissions.",
            ephemeral=True
        )
# /remove-channel commanad
@bot.tree.command(name="remove-channel", description="remove a dumbboard channel")
@discord.app_commands.checks.has_permissions(manage_guild=True)
async def remove_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    try:
        async with bot.db.cursor() as cursor:
            await cursor.execute("SELECT channel FROM starSetup WHERE guild = ? AND channel = ?", (interaction.guild.id, channel.id))
            channelData = await cursor.fetchone()

            if channelData:
                await cursor.execute("DELETE FROM starSetup WHERE guild = ? AND channel = ?", (interaction.guild.id, channel.id))
                await bot.db.commit()
                await interaction.response.send_message(f"{channel.mention} is no longer the dumbboard channel")
            else:
                await interaction.response.send_message("this channel isnt setup as the dumbboard channel", ephemeral=True)
    except discord.errors.Forbidden:
        await interaction.response.send_message(
            "i am missing the permissions to remove this channel from the dumbboard database",
            ephemeral=True
        )

# /list-channels command
@bot.tree.command(name="list-channels", description="list all dumbboard channels")
@discord.app_commands.checks.has_permissions(manage_guild=True)
async def list_channels(interaction: discord.Interaction):
    try:
        async with bot.db.cursor() as cursor:
            await cursor.execute("SELECT channel FROM starSetup WHERE guild = ?", (interaction.guild.id,))
            channels = await cursor.fetchall()

            if channels:
                channel_mentions = [interaction.guild.get_channel(channel[0]).mention for channel in channels if interaction.guild.get_channel(channel[0]) is not None]
                channels_list = "\n".join(channel_mentions)
                await interaction.response.send_message(f"**Dumbboard Channels:**\n{channels_list}")
            else:
                await interaction.response.send_message("no dumbboard channels have been set up", ephemeral=True)
    except discord.errors.Forbidden:
        await interaction.response.send_message(
            "i am missing the permissions to list the dumbboard channels",
            ephemeral=True
        )

# how the bot responds if an error occurs
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    if isinstance(error, discord.app_commands.MissingPermissions):
        await interaction.response.send_message(
            "you are NOT a real mod. (you don't have the required permissions)", ephemeral=True
        )
    elif isinstance(error, discord.app_commands.BotMissingPermissions):
        await interaction.response.send_message(
            "i dont have the required permissions for this action.",
            ephemeral=True
        )
    else:
        # generic error
        await interaction.response.send_message(
            "Something went wrong while processing this event",
            ephemeral=True
        )
        print(f"Unexpected error: {error}")  
# somethinng error i forgot
@bot.event
async def on_command_error(ctx, error):
    em = discord.Embed(title="Error", description=f"```{error}```")
    await ctx.send(embed=em, delete_after=10)
    return

# bot token
TOKEN = os.getenv("BOT_TOKEN")

bot.run(TOKEN)
