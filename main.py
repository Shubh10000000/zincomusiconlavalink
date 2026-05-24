import os
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import wavelink

load_dotenv()

TOKEN         = os.getenv("DISCORD_TOKEN")
LAVALINK_HOST = os.getenv("LAVALINK_HOST", "127.0.0.1")
LAVALINK_PORT = int(os.getenv("LAVALINK_PORT", 2333))
LAVALINK_PASS = os.getenv("LAVALINK_PASSWORD", "youshallnotpass")

# ─────────────────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states    = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ── Helpers ───────────────────────────────────────────────────────────────────
def fmt_duration(ms: int | None) -> str:
    if not ms:
        return "Live"
    s = ms // 1000
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02}:{s:02}" if h else f"{m}:{s:02}"

def now_playing_embed(track: wavelink.Playable, player: wavelink.Player) -> discord.Embed:
    vol     = player.volume
    bar     = "█" * (vol // 10) + "░" * (10 - vol // 10)
    modes   = {
        wavelink.QueueMode.normal: "➡️ Off",
        wavelink.QueueMode.loop:   "🔂 Song",
        wavelink.QueueMode.loop_all: "🔁 Queue",
    }

    embed = discord.Embed(
        title="🎵 Now Playing",
        description=f"**[{track.title}]({track.uri})**",
        color=0x1DB954,
    )
    embed.add_field(name="⏱ Duration", value=fmt_duration(track.length), inline=True)
    embed.add_field(name="🎤 Artist",  value=track.author or "Unknown",  inline=True)
    embed.add_field(name="🔊 Volume",  value=f"`{bar}` {vol}%",          inline=True)
    embed.add_field(name="🔁 Loop",    value=modes.get(player.queue.mode, "➡️ Off"), inline=True)
    if track.artwork:
        embed.set_thumbnail(url=track.artwork)
    requester = getattr(track, "extras", None)
    if requester and hasattr(requester, "requester"):
        embed.set_footer(text=f"Requested by {requester.requester}")
    return embed

def queue_position(player: wavelink.Player) -> int:
    return len(player.queue)

# ── Player Controls View ──────────────────────────────────────────────────────
class PlayerView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    def _player(self, interaction: discord.Interaction) -> wavelink.Player | None:
        return interaction.guild.voice_client  # type: ignore

    @discord.ui.button(emoji="⏸", style=discord.ButtonStyle.secondary, custom_id="wl_pause")
    async def pause_btn(self, interaction: discord.Interaction, btn: discord.ui.Button):
        p = self._player(interaction)
        if not p:
            return await interaction.response.send_message("Not in VC.", ephemeral=True)
        await p.pause(not p.paused)
        btn.emoji = "▶️" if p.paused else "⏸"
        await interaction.response.edit_message(view=self)

    @discord.ui.button(emoji="⏭", style=discord.ButtonStyle.primary, custom_id="wl_skip")
    async def skip_btn(self, interaction: discord.Interaction, btn: discord.ui.Button):
        p = self._player(interaction)
        if not p or not p.playing:
            return await interaction.response.send_message("Nothing to skip.", ephemeral=True)
        await p.skip(force=True)
        await interaction.response.send_message("⏭ Skipped!", ephemeral=True)

    @discord.ui.button(emoji="🔂", style=discord.ButtonStyle.secondary, custom_id="wl_loop")
    async def loop_btn(self, interaction: discord.Interaction, btn: discord.ui.Button):
        p = self._player(interaction)
        if not p:
            return await interaction.response.send_message("Not in VC.", ephemeral=True)
        modes = [wavelink.QueueMode.normal, wavelink.QueueMode.loop, wavelink.QueueMode.loop_all]
        icons = ["➡️", "🔂", "🔁"]
        nxt   = (modes.index(p.queue.mode) + 1) % 3
        p.queue.mode = modes[nxt]
        btn.emoji    = icons[nxt]
        labels = ["Off", "Song", "Queue"]
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(f"Loop → **{labels[nxt]}**", ephemeral=True)

    @discord.ui.button(emoji="🔊", style=discord.ButtonStyle.secondary, custom_id="wl_vol_up")
    async def vol_up(self, interaction: discord.Interaction, btn: discord.ui.Button):
        p = self._player(interaction)
        if not p:
            return await interaction.response.send_message("Not in VC.", ephemeral=True)
        vol = min(100, p.volume + 10)
        await p.set_volume(vol)
        await interaction.response.send_message(f"🔊 Volume: **{vol}%**", ephemeral=True)

    @discord.ui.button(emoji="🔉", style=discord.ButtonStyle.secondary, custom_id="wl_vol_dn")
    async def vol_dn(self, interaction: discord.Interaction, btn: discord.ui.Button):
        p = self._player(interaction)
        if not p:
            return await interaction.response.send_message("Not in VC.", ephemeral=True)
        vol = max(0, p.volume - 10)
        await p.set_volume(vol)
        await interaction.response.send_message(f"🔉 Volume: **{vol}%**", ephemeral=True)

    @discord.ui.button(emoji="⏹", style=discord.ButtonStyle.danger, custom_id="wl_stop")
    async def stop_btn(self, interaction: discord.Interaction, btn: discord.ui.Button):
        p = self._player(interaction)
        if not p:
            return await interaction.response.send_message("Not in VC.", ephemeral=True)
        p.queue.clear()
        await p.stop()
        await p.disconnect()
        await interaction.response.send_message("⏹ Stopped and disconnected.", ephemeral=True)

# ── on_ready → connect to Lavalink ────────────────────────────────────────────
@bot.event
async def on_ready():
    node = wavelink.Node(
        uri=f"http://{LAVALINK_HOST}:{LAVALINK_PORT}",
        password=LAVALINK_PASS,
    )
    await wavelink.Pool.connect(nodes=[node], client=bot)
    try:
        synced = await bot.tree.sync()
        print(f"[Bot] Synced {len(synced)} slash commands")
    except Exception as e:
        print(f"[Sync error] {e}")
    print(f"[Bot] Logged in as {bot.user}  |  Lavalink → {LAVALINK_HOST}:{LAVALINK_PORT}")

# ── Lavalink events ───────────────────────────────────────────────────────────
@bot.event
async def on_wavelink_node_ready(payload: wavelink.NodeReadyEventPayload):
    print(f"[Lavalink] Node ready: {payload.node.identifier} | Resumed: {payload.resumed}")

@bot.event
async def on_wavelink_track_start(payload: wavelink.TrackStartEventPayload):
    player: wavelink.Player = payload.player
    if not player or not player.channel:
        return
    # Find first text channel we can speak in
    guild: discord.Guild = player.guild
    ch = discord.utils.find(
        lambda c: isinstance(c, discord.TextChannel) and c.permissions_for(guild.me).send_messages,
        guild.text_channels,
    )
    if ch and hasattr(player, "_np_channel"):
        ch = player._np_channel  # type: ignore
    if ch:
        embed = now_playing_embed(payload.track, player)
        await ch.send(embed=embed, view=PlayerView())

@bot.event
async def on_wavelink_track_end(payload: wavelink.TrackEndEventPayload):
    player: wavelink.Player = payload.player
    if not player:
        return
    # Auto-disconnect if queue is empty after track ends
    if player.queue.is_empty and not player.playing:
        ch = getattr(player, "_np_channel", None)
        if ch:
            await ch.send("✅ Queue finished. Disconnecting.", delete_after=30)
        await player.disconnect()

# ── /play ─────────────────────────────────────────────────────────────────────
@bot.tree.command(name="play", description="Play or queue a song (URL or search query)")
@app_commands.describe(query="Song name or YouTube/SoundCloud URL")
async def play(interaction: discord.Interaction, query: str):
    if not interaction.user.voice:
        return await interaction.response.send_message("❌ Join a voice channel first!", ephemeral=True)

    await interaction.response.defer()

    channel = interaction.user.voice.channel
    player: wavelink.Player = interaction.guild.voice_client  # type: ignore

    if player is None:
        player = await channel.connect(cls=wavelink.Player, self_deaf=True)
    elif player.channel != channel:
        await player.move_to(channel)

    # Store text channel for track start events
    player._np_channel = interaction.channel  # type: ignore

    # Search / resolve
    tracks = await wavelink.Playable.search(query)
    if not tracks:
        return await interaction.followup.send("❌ No results found.", ephemeral=True)

    if isinstance(tracks, wavelink.Playlist):
        for t in tracks:
            t.extras = wavelink.ExtrasNamespace({"requester": str(interaction.user)})
            await player.queue.put_wait(t)
        embed = discord.Embed(
            title="📋 Playlist Added",
            description=f"**{tracks.name}** — {len(tracks.tracks)} tracks",
            color=0x5865F2,
        )
        await interaction.followup.send(embed=embed)
    else:
        track = tracks[0]
        track.extras = wavelink.ExtrasNamespace({"requester": str(interaction.user)})

        if player.playing or not player.queue.is_empty:
            await player.queue.put_wait(track)
            embed = discord.Embed(
                title="➕ Added to Queue",
                description=f"**[{track.title}]({track.uri})**",
                color=0x5865F2,
            )
            embed.add_field(name="⏱ Duration", value=fmt_duration(track.length), inline=True)
            embed.add_field(name="📋 Position", value=f"#{queue_position(player)}", inline=True)
            if track.artwork:
                embed.set_thumbnail(url=track.artwork)
            return await interaction.followup.send(embed=embed)

    if not player.playing:
        await player.play(player.queue.get(), volume=80)

    await interaction.followup.send("▶️ Starting…", delete_after=3)

# ── /playtop ──────────────────────────────────────────────────────────────────
@bot.tree.command(name="playtop", description="Add a song to the front of the queue")
@app_commands.describe(query="Song name or URL")
async def playtop(interaction: discord.Interaction, query: str):
    if not interaction.user.voice:
        return await interaction.response.send_message("❌ Join a voice channel first!", ephemeral=True)

    await interaction.response.defer()
    player: wavelink.Player = interaction.guild.voice_client  # type: ignore

    if player is None:
        player = await interaction.user.voice.channel.connect(cls=wavelink.Player, self_deaf=True)
        player._np_channel = interaction.channel  # type: ignore

    tracks = await wavelink.Playable.search(query)
    if not tracks:
        return await interaction.followup.send("❌ No results found.", ephemeral=True)

    track = tracks[0] if not isinstance(tracks, wavelink.Playlist) else tracks[0]
    track.extras = wavelink.ExtrasNamespace({"requester": str(interaction.user)})
    player.queue.put_at(0, track)

    await interaction.followup.send(f"⬆️ **{track.title}** added to the top of the queue!")

    if not player.playing:
        await player.play(player.queue.get(), volume=80)

# ── /pause ────────────────────────────────────────────────────────────────────
@bot.tree.command(name="pause", description="Pause playback")
async def pause(interaction: discord.Interaction):
    player: wavelink.Player = interaction.guild.voice_client  # type: ignore
    if player and player.playing and not player.paused:
        await player.pause(True)
        await interaction.response.send_message("⏸ Paused.")
    else:
        await interaction.response.send_message("Nothing is playing.", ephemeral=True)

# ── /resume ───────────────────────────────────────────────────────────────────
@bot.tree.command(name="resume", description="Resume playback")
async def resume(interaction: discord.Interaction):
    player: wavelink.Player = interaction.guild.voice_client  # type: ignore
    if player and player.paused:
        await player.pause(False)
        await interaction.response.send_message("▶️ Resumed.")
    else:
        await interaction.response.send_message("Not paused.", ephemeral=True)

# ── /skip ─────────────────────────────────────────────────────────────────────
@bot.tree.command(name="skip", description="Skip the current song")
async def skip(interaction: discord.Interaction):
    player: wavelink.Player = interaction.guild.voice_client  # type: ignore
    if player and (player.playing or player.paused):
        await player.skip(force=True)
        await interaction.response.send_message("⏭ Skipped!")
    else:
        await interaction.response.send_message("Nothing to skip.", ephemeral=True)

# ── /stop ─────────────────────────────────────────────────────────────────────
@bot.tree.command(name="stop", description="Stop music and clear the queue")
async def stop(interaction: discord.Interaction):
    player: wavelink.Player = interaction.guild.voice_client  # type: ignore
    if player:
        player.queue.clear()
        await player.stop()
        await player.disconnect()
        await interaction.response.send_message("⏹ Stopped and cleared the queue.")
    else:
        await interaction.response.send_message("Not in a VC.", ephemeral=True)

# ── /leave ────────────────────────────────────────────────────────────────────
@bot.tree.command(name="leave", description="Disconnect the bot from VC")
async def leave(interaction: discord.Interaction):
    player: wavelink.Player = interaction.guild.voice_client  # type: ignore
    if player:
        player.queue.clear()
        await player.disconnect()
        await interaction.response.send_message("👋 Disconnected.")
    else:
        await interaction.response.send_message("I'm not in a VC.", ephemeral=True)

# ── /queue ────────────────────────────────────────────────────────────────────
@bot.tree.command(name="queue", description="Show the current queue")
async def queue_cmd(interaction: discord.Interaction):
    player: wavelink.Player = interaction.guild.voice_client  # type: ignore

    embed = discord.Embed(title="📋 Queue", color=0x1DB954)

    if player and player.current:
        t = player.current
        embed.add_field(
            name="🎵 Now Playing",
            value=f"[{t.title}]({t.uri}) — `{fmt_duration(t.length)}`",
            inline=False,
        )

    if player and not player.queue.is_empty:
        lines = []
        for i, t in enumerate(list(player.queue)[:10], 1):
            lines.append(f"`{i}.` [{t.title}]({t.uri}) — `{fmt_duration(t.length)}`")
        if len(player.queue) > 10:
            lines.append(f"…and {len(player.queue) - 10} more")
        embed.add_field(name="⏳ Up Next", value="\n".join(lines), inline=False)
    else:
        embed.add_field(name="⏳ Up Next", value="Queue is empty.", inline=False)

    mode_labels = {
        wavelink.QueueMode.normal:   "➡️ Off",
        wavelink.QueueMode.loop:     "🔂 Song",
        wavelink.QueueMode.loop_all: "🔁 Queue",
    }
    mode = player.queue.mode if player else wavelink.QueueMode.normal
    total = len(player.queue) if player else 0
    embed.set_footer(text=f"Loop: {mode_labels.get(mode, '➡️ Off')}  •  {total} song(s) in queue")
    await interaction.response.send_message(embed=embed)

# ── /nowplaying ───────────────────────────────────────────────────────────────
@bot.tree.command(name="nowplaying", description="Show what's currently playing")
async def nowplaying(interaction: discord.Interaction):
    player: wavelink.Player = interaction.guild.voice_client  # type: ignore
    if not player or not player.current:
        return await interaction.response.send_message("Nothing is playing.", ephemeral=True)
    embed = now_playing_embed(player.current, player)
    await interaction.response.send_message(embed=embed, view=PlayerView())

# ── /volume ───────────────────────────────────────────────────────────────────
@bot.tree.command(name="volume", description="Set volume (0–100)")
@app_commands.describe(level="Volume level 0–100")
async def volume(interaction: discord.Interaction, level: int):
    if not 0 <= level <= 100:
        return await interaction.response.send_message("❌ Volume must be 0–100.", ephemeral=True)
    player: wavelink.Player = interaction.guild.voice_client  # type: ignore
    if not player:
        return await interaction.response.send_message("Not in a VC.", ephemeral=True)
    await player.set_volume(level)
    await interaction.response.send_message(f"🔊 Volume set to **{level}%**")

# ── /loop ─────────────────────────────────────────────────────────────────────
@bot.tree.command(name="loop", description="Set loop mode")
@app_commands.describe(mode="Loop mode")
@app_commands.choices(mode=[
    app_commands.Choice(name="Off",   value="off"),
    app_commands.Choice(name="Song",  value="song"),
    app_commands.Choice(name="Queue", value="queue"),
])
async def loop_cmd(interaction: discord.Interaction, mode: app_commands.Choice[str]):
    player: wavelink.Player = interaction.guild.voice_client  # type: ignore
    if not player:
        return await interaction.response.send_message("Not in a VC.", ephemeral=True)
    mode_map = {
        "off":   wavelink.QueueMode.normal,
        "song":  wavelink.QueueMode.loop,
        "queue": wavelink.QueueMode.loop_all,
    }
    player.queue.mode = mode_map[mode.value]
    icons = {"off": "➡️", "song": "🔂", "queue": "🔁"}
    await interaction.response.send_message(f"{icons[mode.value]} Loop set to **{mode.name}**")

# ── /shuffle ──────────────────────────────────────────────────────────────────
@bot.tree.command(name="shuffle", description="Shuffle the queue")
async def shuffle(interaction: discord.Interaction):
    player: wavelink.Player = interaction.guild.voice_client  # type: ignore
    if not player or player.queue.is_empty:
        return await interaction.response.send_message("Queue is empty.", ephemeral=True)
    player.queue.shuffle()
    await interaction.response.send_message("🔀 Queue shuffled!")

# ── /remove ───────────────────────────────────────────────────────────────────
@bot.tree.command(name="remove", description="Remove a song from the queue by position")
@app_commands.describe(position="Position in queue (1-based)")
async def remove(interaction: discord.Interaction, position: int):
    player: wavelink.Player = interaction.guild.voice_client  # type: ignore
    if not player or player.queue.is_empty or not (1 <= position <= len(player.queue)):
        return await interaction.response.send_message("❌ Invalid position.", ephemeral=True)
    track = player.queue[position - 1]
    del player.queue[position - 1]
    await interaction.response.send_message(f"🗑️ Removed **{track.title}** from the queue.")

# ── /search ───────────────────────────────────────────────────────────────────
@bot.tree.command(name="search", description="Search YouTube and see top 5 results")
@app_commands.describe(query="Search term")
async def search(interaction: discord.Interaction, query: str):
    await interaction.response.defer()
    tracks = await wavelink.Playable.search(query)
    if not tracks:
        return await interaction.followup.send("No results found.", ephemeral=True)

    results = tracks[:5] if not isinstance(tracks, wavelink.Playlist) else tracks.tracks[:5]
    embed = discord.Embed(title=f"🔎 Results for: {query}", color=0x5865F2)
    lines = []
    for i, t in enumerate(results, 1):
        lines.append(f"`{i}.` **[{t.title}]({t.uri})** — `{fmt_duration(t.length)}` by {t.author or '?'}")
    embed.description = "\n\n".join(lines)
    embed.set_footer(text="Use /play <title> to queue a song")
    await interaction.followup.send(embed=embed)

# ── /seek ─────────────────────────────────────────────────────────────────────
@bot.tree.command(name="seek", description="Seek to a position in the current track")
@app_commands.describe(seconds="Position in seconds")
async def seek(interaction: discord.Interaction, seconds: int):
    player: wavelink.Player = interaction.guild.voice_client  # type: ignore
    if not player or not player.current:
        return await interaction.response.send_message("Nothing is playing.", ephemeral=True)
    await player.seek(seconds * 1000)
    await interaction.response.send_message(f"⏩ Seeked to **{fmt_duration(seconds * 1000)}**")

# ── /filter ───────────────────────────────────────────────────────────────────
@bot.tree.command(name="filter", description="Apply an audio filter")
@app_commands.describe(preset="Choose a filter preset")
@app_commands.choices(preset=[
    app_commands.Choice(name="None (Reset)",  value="none"),
    app_commands.Choice(name="Bass Boost",    value="bass"),
    app_commands.Choice(name="Nightcore",     value="nightcore"),
    app_commands.Choice(name="Slowed",        value="slowed"),
    app_commands.Choice(name="Vaporwave",     value="vaporwave"),
])
async def filter_cmd(interaction: discord.Interaction, preset: app_commands.Choice[str]):
    player: wavelink.Player = interaction.guild.voice_client  # type: ignore
    if not player:
        return await interaction.response.send_message("Not in a VC.", ephemeral=True)

    filters = wavelink.Filters()

    if preset.value == "bass":
        eq = wavelink.Equalizer(bands=[
            {"band": 0, "gain": 0.3},
            {"band": 1, "gain": 0.3},
            {"band": 2, "gain": 0.2},
        ])
        filters.equalizer.set(bands=[
            {"band": 0, "gain": 0.3},
            {"band": 1, "gain": 0.3},
            {"band": 2, "gain": 0.2},
        ])
    elif preset.value == "nightcore":
        filters.timescale.set(pitch=1.2, speed=1.1, rate=1.0)
    elif preset.value == "slowed":
        filters.timescale.set(pitch=0.85, speed=0.85, rate=1.0)
    elif preset.value == "vaporwave":
        filters.timescale.set(pitch=0.8, speed=0.8, rate=1.0)
    # "none" leaves filters empty → resets

    await player.set_filters(filters)
    await interaction.response.send_message(f"🎛️ Filter set to **{preset.name}**")

# ─────────────────────────────────────────────────────────────────────────────
bot.run(TOKEN)
