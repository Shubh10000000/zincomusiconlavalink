import os
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import wavelink

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")




LAVALINK_HOST = os.getenv("lavalink-2026-production-03ef.up.railway.app")
LAVALINK_PORT = int(os.getenv("443"))
LAVALINK_PASSWORD = os.getenv("MYMUSICBOT")

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():

    print(f"Logged in as {bot.user}")

    # CONNECT TO LAVALINK
    node = wavelink.Node(
        uri=f"https://{LAVALINK_HOST}:{LAVALINK_PORT}",
        password=LAVALINK_PASSWORD
    )

    await wavelink.Pool.connect(
        client=bot,
        nodes=[node]
    )

    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands")
    except Exception as e:
        print(e)

    print("Lavalink connected")


# PLAY COMMAND
@bot.tree.command(name="play", description="Play music")
async def play(interaction: discord.Interaction, query: str):

    if not interaction.user.voice:
        await interaction.response.send_message("Join VC first")
        return

    channel = interaction.user.voice.channel

    player: wavelink.Player

    if not interaction.guild.voice_client:
        player = await channel.connect(cls=wavelink.Player)
    else:
        player = interaction.guild.voice_client

    await interaction.response.send_message(f"Searching `{query}`")

    tracks = await wavelink.Playable.search(query)

    if not tracks:
        await interaction.followup.send("No song found")
        return

    track = tracks[0]

    await player.play(track)

    await interaction.followup.send(f"Now Playing: **{track.title}**")


# PAUSE
@bot.tree.command(name="pause", description="Pause music")
async def pause(interaction: discord.Interaction):

    vc: wavelink.Player = interaction.guild.voice_client

    if vc and vc.playing:
        await vc.pause(True)
        await interaction.response.send_message("Paused")


# RESUME
@bot.tree.command(name="resume", description="Resume music")
async def resume(interaction: discord.Interaction):

    vc: wavelink.Player = interaction.guild.voice_client

    if vc and vc.paused:
        await vc.pause(False)
        await interaction.response.send_message("Resumed")


# SKIP
@bot.tree.command(name="skip", description="Skip song")
async def skip(interaction: discord.Interaction):

    vc: wavelink.Player = interaction.guild.voice_client

    if vc and vc.playing:
        await vc.stop()
        await interaction.response.send_message("Skipped")


# LEAVE
@bot.tree.command(name="leave", description="Leave VC")
async def leave(interaction: discord.Interaction):

    vc: wavelink.Player = interaction.guild.voice_client

    if vc:
        await vc.disconnect()
        await interaction.response.send_message("Disconnected")


bot.run(TOKEN)
