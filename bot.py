import discord
from discord.ext import commands
from discord import app_commands
from flask import Flask
import threading
import os
import re
from datetime import datetime, timedelta

# --- Environment ---
TOKEN = os.getenv("DISCORD_TOKEN")

# --- Intents ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# --- Keep alive Flask app ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = threading.Thread(target=run)
    t.start()

# --- Constants ---
WELCOME_CHANNEL_ID = 1387583772030927100

# --- Data holders ---
command_usage = {}
user_xp = {}
user_levels = {}

# --- Helpers ---

def track_command(user_id, command_name):
    if user_id not in command_usage:
        command_usage[user_id] = {}
    command_usage[user_id][command_name] = command_usage[user_id].get(command_name, 0) + 1

def parse_duration(duration_str):
    match = re.fullmatch(r"(\d+)([mhd])", duration_str)
    if not match:
        return None
    value, unit = int(match.group(1)), match.group(2)
    if unit == "m":
        return value * 60
    elif unit == "h":
        return value * 3600
    elif unit == "d":
        return value * 86400
    return None

def add_xp(user_id, amount=5):
    user_xp[user_id] = user_xp.get(user_id, 0) + amount
    if user_xp[user_id] < 0:
        user_xp[user_id] = 0
    new_level = user_xp[user_id] // 500
    if user_levels.get(user_id, 0) < new_level:
        user_levels[user_id] = new_level
        return new_level
    return None

def xp_to_next_level(user_id):
    xp = user_xp.get(user_id, 0)
    level = user_levels.get(user_id, 0)
    return ((level + 1) * 500) - xp

# --- Events ---

@bot.event
async def on_ready():
    await tree.sync()
    print(f"✅ Bot ready as {bot.user}")

@bot.event
async def on_member_join(member):
    channel = bot.get_channel(WELCOME_CHANNEL_ID)
    if channel:
        await channel.send(f"👋 Welcome {member.mention}! We now have {member.guild.member_count} members.")

@bot.event
async def on_member_remove(member):
    channel = bot.get_channel(WELCOME_CHANNEL_ID)
    if channel:
        await channel.send(f"😢 {member.name} has left. We now have {member.guild.member_count} members.")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    user_id = message.author.id
    level_up = add_xp(user_id)
    if level_up:
        await message.channel.send(f"🎉 Congrats {message.author.mention}, you leveled up to level {level_up}!")

    if message.content.lower().startswith("level?"):
        mentioned = message.mentions[0] if message.mentions else message.author
        lvl = user_levels.get(mentioned.id, 0)
        xp = user_xp.get(mentioned.id, 0)
        await message.channel.send(f"📈 {mentioned.mention} is level {lvl} with {xp} XP.")

    elif message.content.lower() == "xp left":
        left = xp_to_next_level(message.author.id)
        await message.channel.send(f"⏳ {message.author.mention}, you need {left} XP to next level.")

    elif message.content.lower() == "what commands" or bot.user in message.mentions:
        await message.channel.send(
            "**Commands:**\n"
            "/kick, /ban, /timeout, /untimeout, /purge, /cmdstats, /leaderboard, /addxp, /removexp, /say\n"
            "!lock, !unlock\n"
            "level? @user, xp left"
        )

    elif message.content.lower() == "key":
        await message.channel.send("dumb it's 'vault'. Say 'ok gimme key role' to stop me answering u")

    await bot.process_commands(message)

# --- Slash commands ---

@tree.command(name="kick", description="Kick a user")
@app_commands.checks.has_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    try:
        await member.kick(reason=reason)
        track_command(interaction.user.id, "kick")
        await interaction.response.send_message(f"✅ {member} kicked.")
    except Exception:
        await interaction.response.send_message("❌ Failed to kick.", ephemeral=True)

@tree.command(name="ban", description="Ban a user")
@app_commands.checks.has_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    try:
        await member.ban(reason=reason)
        track_command(interaction.user.id, "ban")
        await interaction.response.send_message(f"✅ {member} banned.")
    except Exception:
        await interaction.response.send_message("❌ Failed to ban.", ephemeral=True)

@tree.command(name="timeout", description="Timeout a user")
@app_commands.checks.has_permissions(moderate_members=True)
async def timeout(interaction: discord.Interaction, member: discord.Member, duration: str, reason: str = "No reason provided"):
    seconds = parse_duration(duration)
    if seconds is None:
        await interaction.response.send_message("❌ Invalid duration! Use 5m, 1h, 2d format.", ephemeral=True)
        return
    try:
        until = discord.utils.utcnow() + timedelta(seconds=seconds)
        await member.timeout(until, reason=reason)
        track_command(interaction.user.id, "timeout")
        await interaction.response.send_message(f"⏳ {member.mention} timed out for {duration}.")
    except Exception:
        await interaction.response.send_message("❌ Timeout failed.", ephemeral=True)

@tree.command(name="untimeout", description="Remove timeout")
@app_commands.checks.has_permissions(moderate_members=True)
async def untimeout(interaction: discord.Interaction, member: discord.Member):
    try:
        await member.timeout(None)
        await interaction.response.send_message(f"✅ Timeout removed for {member.mention}.")
    except Exception:
        await interaction.response.send_message("❌ Failed to remove timeout.", ephemeral=True)

@tree.command(name="purge", description="Delete messages")
@app_commands.checks.has_permissions(manage_messages=True)
async def purge(interaction: discord.Interaction, amount: int):
    if amount < 1 or amount > 100:
        await interaction.response.send_message("❌ Amount must be between 1 and 100.", ephemeral=True)
        return
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.response.send_message(f"🧹 Deleted {len(deleted)} messages.", ephemeral=True)

@tree.command(name="cmdstats", description="View command usage stats for a user")
async def cmdstats(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    stats = command_usage.get(member.id, {})
    msg = f"📊 Command stats for {member.mention}:\n"
    for cmd, count in stats.items():
        msg += f"• {cmd}: {count}\n"
    await interaction.response.send_message(msg)

@tree.command(name="addxp", description="Add XP to a user")
@app_commands.checks.has_permissions(administrator=True)
async def addxp(interaction: discord.Interaction, member: discord.Member, amount: int):
    if amount <= 0:
        await interaction.response.send_message("❌ Amount must be positive.", ephemeral=True)
        return
    track_command(interaction.user.id, "addxp")
    new_level = add_xp(member.id, amount)
    await interaction.response.send_message(f"✅ Added {amount} XP to {member.mention}.")
    if new_level:
        await interaction.channel.send(f"🎉 {member.mention} leveled up to level {new_level}!")

@tree.command(name="removexp", description="Remove XP from a user")
@app_commands.checks.has_permissions(administrator=True)
async def removexp(interaction: discord.Interaction, member: discord.Member, amount: int):
    if amount <= 0:
        await interaction.response.send_message("❌ Amount must be positive.", ephemeral=True)
        return
    track_command(interaction.user.id, "removexp")
    add_xp(member.id, -amount)
    await interaction.response.send_message(f"✅ Removed {amount} XP from {member.mention}.")

@tree.command(name="leaderboard", description="Show the XP leaderboard")
async def leaderboard(interaction: discord.Interaction):
    sorted_users = sorted(user_xp.items(), key=lambda kv: kv[1], reverse=True)[:10]
    embed = discord.Embed(title="🏆 XP Leaderboard")
    for i, (user_id, xp) in enumerate(sorted_users, start=1):
        user = bot.get_user(user_id)
        name = user.name if user else f"User ID {user_id}"
        embed.add_field(name=f"{i}. {name}", value=f"{xp} XP", inline=False)
    await interaction.response.send_message(embed=embed)

# --- Text commands ---

@bot.command()
@commands.has_permissions(manage_channels=True)
async def lock(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
    await ctx.send("🔒 Channel locked.")

@bot.command()
@commands.has_permissions(manage_channels=True)
async def unlock(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=True)
    await ctx.send("🔓 Channel unlocked.")

@bot.command()
@commands.has_permissions(administrator=True)
async def say(ctx, *, message: str):
    await ctx.message.delete()
    await ctx.send(message)
    track_command(ctx.author.id, "say")

# --- Run ---

keep_alive()
bot.run(TOKEN)
