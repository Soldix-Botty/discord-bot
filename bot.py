import os
import re
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timedelta

# Bot token from environment variables (set this in Render)
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    print("Error: TOKEN environment variable not found.")
    exit(1)

# Intents and bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# Welcome channel ID (your TS channel)
WELCOME_CHANNEL_ID = 1387583772030927100

# In-memory data for commands and leveling
command_usage = {}
message_counts = {}
user_xp = {}
user_levels = {}

def track_command(user_id, command_name):
    if user_id not in command_usage:
        command_usage[user_id] = {"kick":0, "ban":0, "timeout":0, "addxp":0, "say":0}
    if command_name in command_usage[user_id]:
        command_usage[user_id][command_name] += 1

def parse_duration(duration_str):
    match = re.match(r"(\d+)([mhd])$", duration_str)
    if not match:
        return None
    value, unit = int(match.group(1)), match.group(2)
    return value * {"m": 60, "h": 3600, "d": 86400}[unit]

def add_xp(user_id, amount=5):
    user_xp[user_id] = user_xp.get(user_id, 0) + amount
    level = user_xp[user_id] // 500
    if user_levels.get(user_id, 0) < level:
        user_levels[user_id] = level
        return level
    return None

def xp_to_next_level(user_id):
    xp = user_xp.get(user_id, 0)
    level = user_levels.get(user_id, 0)
    return (level + 1) * 500 - xp

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    try:
        synced = await tree.sync()
        print(f"Synced {len(synced)} commands.")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

@bot.event
async def on_member_join(member):
    channel = bot.get_channel(WELCOME_CHANNEL_ID)
    if channel:
        await channel.send(f"👋 Welcome {member.mention}! We now have {member.guild.member_count} members.")

@bot.event
async def on_member_remove(member):
    channel = bot.get_channel(WELCOME_CHANNEL_ID)
    if channel:
        await channel.send(f"😢 {member.name} left. We now have {member.guild.member_count} members.")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Leveling and message count
    user_id = message.author.id
    message_counts[user_id] = message_counts.get(user_id, 0) + 1
    level_up = add_xp(user_id)
    if level_up:
        await message.channel.send(f"🎉 Congrats {message.author.mention}, you reached level {level_up}!")

    # Simple text commands
    content = message.content.lower()

    if content == "level?" or content.startswith("level? "):
        mentioned = message.mentions[0] if message.mentions else message.author
        level = user_levels.get(mentioned.id, 0)
        xp = user_xp.get(mentioned.id, 0)
        await message.channel.send(f"📈 {mentioned.mention} is level {level} with {xp} XP.")

    elif content == "xp left":
        left = xp_to_next_level(message.author.id)
        await message.channel.send(f"⏳ {message.author.mention}, you need {left} XP to next level.")

    elif content == "what commands" or bot.user in message.mentions:
        await message.channel.send(
            "📜 Commands:\n"
            "/kick, /ban, /timeout, /untimeout, /purge, /cmdstats, /leaderboard, /addxp, /say (admin)\n"
            "!lock, !unlock (admin)\n"
            "level? @user, xp left"
        )

    elif content == "key":
        await message.channel.send('dumb it\'s "vault". Say "ok gimme key role" to stop me.')

    await bot.process_commands(message)

# Moderation slash commands
@tree.command(name="kick", description="Kick a user")
@app_commands.describe(member="User to kick", reason="Reason for kick")
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    if not interaction.user.guild_permissions.kick_members:
        await interaction.response.send_message("❌ You don't have permission to kick.", ephemeral=True)
        return
    try:
        await member.kick(reason=reason)
        track_command(interaction.user.id, "kick")
        await interaction.response.send_message(f"✅ {member} kicked.")
    except:
        await interaction.response.send_message("❌ Failed to kick.", ephemeral=True)

@tree.command(name="ban", description="Ban a user")
@app_commands.describe(member="User to ban", reason="Reason for ban")
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    if not interaction.user.guild_permissions.ban_members:
        await interaction.response.send_message("❌ You don't have permission to ban.", ephemeral=True)
        return
    try:
        await member.ban(reason=reason)
        track_command(interaction.user.id, "ban")
        await interaction.response.send_message(f"✅ {member} banned.")
    except:
        await interaction.response.send_message("❌ Failed to ban.", ephemeral=True)

@tree.command(name="timeout", description="Timeout a user")
@app_commands.describe(member="User to timeout", duration="Duration e.g. 5m, 2h", reason="Reason")
async def timeout(interaction: discord.Interaction, member: discord.Member, duration: str, reason: str = "No reason provided"):
    if not interaction.user.guild_permissions.moderate_members:
        await interaction.response.send_message("❌ No permission to timeout.", ephemeral=True)
        return
    seconds = parse_duration(duration)
    if not seconds:
        await interaction.response.send_message("❌ Invalid duration format. Use 5m, 2h, 1d.", ephemeral=True)
        return
    until = discord.utils.utcnow() + timedelta(seconds=seconds)
    try:
        await member.timeout(until, reason=reason)
        track_command(interaction.user.id, "timeout")
        await interaction.response.send_message(f"⏳ {member} timed out for {duration}.")
    except:
        await interaction.response.send_message("❌ Failed to timeout.", ephemeral=True)

@tree.command(name="untimeout", description="Remove timeout")
@app_commands.describe(member="User to remove timeout from")
async def untimeout(interaction: discord.Interaction, member: discord.Member):
    if not interaction.user.guild_permissions.moderate_members:
        await interaction.response.send_message("❌ No permission.", ephemeral=True)
        return
    try:
        await member.timeout(None)
        await interaction.response.send_message(f"✅ Timeout removed from {member}.")
    except:
        await interaction.response.send_message("❌ Failed to remove timeout.", ephemeral=True)

@tree.command(name="purge", description="Delete messages")
@app_commands.describe(amount="Number of messages to delete (1-100)")
async def purge(interaction: discord.Interaction, amount: int):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("❌ No permission.", ephemeral=True)
        return
    if amount < 1 or amount > 100:
        await interaction.response.send_message("❌ Amount must be between 1 and 100.", ephemeral=True)
        return
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.response.send_message(f"🧹 Deleted {len(deleted)} messages.", ephemeral=True)

@tree.command(name="cmdstats", description="Show command usage stats for a user")
@app_commands.describe(member="User to check")
async def cmdstats(interaction: discord.Interaction, member: discord.Member):
    stats = command_usage.get(member.id, {"kick":0, "ban":0, "timeout":0, "addxp":0, "say":0})
    await interaction.response.send_message(
        f"📊 Stats for {member.mention}:\n"
        f"Kicks: {stats.get('kick', 0)}\n"
        f"Bans: {stats.get('ban', 0)}\n"
        f"Timeouts: {stats.get('timeout', 0)}\n"
        f"XP Adds: {stats.get('addxp', 0)}\n"
        f"Say Commands: {stats.get('say', 0)}"
    )

@tree.command(name="leaderboard", description="Show leaderboard")
@app_commands.describe(category="messages, voice, moderation")
async def leaderboard(interaction: discord.Interaction, category: str):
    await interaction.response.send_message("Leaderboard feature not implemented yet.", ephemeral=True)

@tree.command(name="addxp", description="Add XP to a user (admin)")
@app_commands.describe(member="User to add XP to", amount="XP amount")
async def addxp(interaction: discord.Interaction, member: discord.Member, amount: int):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ No permission.", ephemeral=True)
        return
    user_xp[member.id] = user_xp.get(member.id, 0) + amount
    track_command(interaction.user.id, "addxp")
    await interaction.response.send_message(f"✅ Added {amount} XP to {member}.")

@tree.command(name="say", description="Make the bot say something (admin)")
@app_commands.describe(message="Message to say")
async def say(interaction: discord.Interaction, message: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ No permission.", ephemeral=True)
        return
    track_command(interaction.user.id, "say")
    await interaction.response.send_message(message)

@bot.command(name="lock")
@commands.has_permissions(manage_channels=True)
async def lock(ctx):
    overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
    overwrite.send_messages = False
    await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
    await ctx.send("🔒 Channel locked.")

@bot.command(name="unlock")
@commands.has_permissions(manage_channels=True)
async def unlock(ctx):
    overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
    overwrite.send_messages = True
    await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
    await ctx.send("🔓 Channel unlocked.")

bot.run(TOKEN)
