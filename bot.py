import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
from datetime import datetime, timedelta
import re
from flask import Flask
import threading
import os

# --------- Flask keep-alive setup ---------
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

def keep_alive():
    threading.Thread(target=run_flask).start()

# --------- Bot setup ---------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# --------- Globals ---------
WELCOME_CHANNEL_ID = 1387583772030927100

# Command usage tracker
command_usage = {}

# XP and leveling data
user_xp = {}
user_level = {}

# Helper function: parse duration like '5m', '2h', '1d'
def parse_duration(duration: str):
    match = re.match(r"(\d+)([smhd])", duration.lower())
    if not match:
        return None
    amount, unit = match.groups()
    amount = int(amount)
    if unit == 's':
        return amount
    elif unit == 'm':
        return amount * 60
    elif unit == 'h':
        return amount * 3600
    elif unit == 'd':
        return amount * 86400
    return None

# Track command usage
def track_command(user_id, cmd_name):
    if user_id not in command_usage:
        command_usage[user_id] = {}
    command_usage[user_id][cmd_name] = command_usage[user_id].get(cmd_name, 0) + 1

# Add XP and check for level up
def add_xp(user_id, xp_amount=10):
    user_xp[user_id] = user_xp.get(user_id, 0) + xp_amount
    lvl = user_level.get(user_id, 1)
    needed = lvl * 100  # XP needed per level
    if user_xp[user_id] >= needed:
        user_level[user_id] = lvl + 1
        return True, user_level[user_id]
    return False, lvl

# --------- Events ---------

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("------")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

@bot.event
async def on_member_join(member):
    channel = bot.get_channel(WELCOME_CHANNEL_ID)
    if channel:
        await channel.send(f"Welcome to the server, {member.mention}! 🎉")
    else:
        print(f"Welcome channel {WELCOME_CHANNEL_ID} not found.")

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    # Give XP per message
    leveled_up, new_level = add_xp(message.author.id)
    if leveled_up:
        await message.channel.send(f"🎉 Congrats {message.author.mention}, you reached level {new_level}!")
    await bot.process_commands(message)

# --------- Moderation commands ---------

@tree.command(name="kick", description="Kick a user from the server")
@app_commands.describe(member="The member to kick", reason="Reason for kicking")
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    if not interaction.user.guild_permissions.kick_members:
        await interaction.response.send_message("❌ You do not have permission to kick members.", ephemeral=True)
        return
    try:
        await member.kick(reason=reason)
        await interaction.response.send_message(f"👢 Kicked {member.mention}. Reason: {reason}")
        track_command(interaction.user.id, "kick")
    except Exception as e:
        await interaction.response.send_message(f"❌ Failed to kick: {e}", ephemeral=True)

@tree.command(name="ban", description="Ban a user from the server")
@app_commands.describe(member="The member to ban", reason="Reason for banning")
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    if not interaction.user.guild_permissions.ban_members:
        await interaction.response.send_message("❌ You do not have permission to ban members.", ephemeral=True)
        return
    try:
        await member.ban(reason=reason)
        await interaction.response.send_message(f"🔨 Banned {member.mention}. Reason: {reason}")
        track_command(interaction.user.id, "ban")
    except Exception as e:
        await interaction.response.send_message(f"❌ Failed to ban: {e}", ephemeral=True)

@tree.command(name="timeout", description="Timeout a user")
@app_commands.describe(member="The member to timeout", duration="Duration (e.g. 5m, 2h, 1d)", reason="Reason for timeout")
async def timeout(interaction: discord.Interaction, member: discord.Member, duration: str, reason: str = "No reason provided"):
    if not interaction.user.guild_permissions.moderate_members:
        await interaction.response.send_message("❌ You do not have permission to timeout members.", ephemeral=True)
        return
    seconds = parse_duration(duration)
    if seconds is None:
        await interaction.response.send_message("❌ Invalid duration format. Use like '5m', '2h', or '1d'.", ephemeral=True)
        return
    until = datetime.utcnow() + timedelta(seconds=seconds)
    try:
        await member.timeout(until, reason=reason)
        await interaction.response.send_message(f"⏱️ Timed out {member.mention} for {duration}. Reason: {reason}")
        track_command(interaction.user.id, "timeout")
    except Exception as e:
        await interaction.response.send_message(f"❌ Failed to timeout: {e}", ephemeral=True)

@tree.command(name="untimeout", description="Remove timeout from a user")
@app_commands.describe(member="The member to untimeout")
async def untimeout(interaction: discord.Interaction, member: discord.Member):
    if not interaction.user.guild_permissions.moderate_members:
        await interaction.response.send_message("❌ You do not have permission to untimeout members.", ephemeral=True)
        return
    try:
        await member.timeout(None)
        await interaction.response.send_message(f"✅ Timeout removed from {member.mention}.")
    except Exception as e:
        await interaction.response.send_message(f"❌ Failed to remove timeout: {e}", ephemeral=True)

@tree.command(name="purge", description="Delete a number of messages")
@app_commands.describe(amount="Number of messages to delete (max 100)")
async def purge(interaction: discord.Interaction, amount: int):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("❌ You do not have permission to manage messages.", ephemeral=True)
        return
    if amount < 1 or amount > 100:
        await interaction.response.send_message("❌ Amount must be between 1 and 100.", ephemeral=True)
        return
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.response.send_message(f"🧹 Deleted {len(deleted)} messages.", ephemeral=True)
    track_command(interaction.user.id, "purge")

@tree.command(name="lock", description="Lock the current channel (deny sending messages)")
async def lock(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_channels:
        await interaction.response.send_message("❌ You do not have permission to manage channels.", ephemeral=True)
        return
    overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
    overwrite.send_messages = False
    await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
    await interaction.response.send_message("🔒 Channel locked.")
    track_command(interaction.user.id, "lock")

@tree.command(name="unlock", description="Unlock the current channel (allow sending messages)")
async def unlock(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_channels:
        await interaction.response.send_message("❌ You do not have permission to manage channels.", ephemeral=True)
        return
    overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
    overwrite.send_messages = True
    await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
    await interaction.response.send_message("🔓 Channel unlocked.")
    track_command(interaction.user.id, "unlock")

# --------- Utility commands ---------

@tree.command(name="cmdstats", description="Show your command usage statistics")
async def cmdstats(interaction: discord.Interaction):
    usage = command_usage.get(interaction.user.id, {})
    if not usage:
        await interaction.response.send_message("You have not used any commands yet.", ephemeral=True)
        return
    stats = "\n".join(f"{cmd}: {count}" for cmd, count in usage.items())
    await interaction.response.send_message(f"Your command usage:\n{stats}", ephemeral=True)

@tree.command(name="level", description="Check your or another user's level")
@app_commands.describe(user="User to check (optional)")
async def level(interaction: discord.Interaction, user: discord.Member = None):
    user = user or interaction.user
    lvl = user_level.get(user.id, 1)
    xp = user_xp.get(user.id, 0)
    await interaction.response.send_message(f"{user.display_name} is level {lvl} with {xp} XP.")

@tree.command(name="leaderboard", description="Show the top 10 users by level")
async def leaderboard(interaction: discord.Interaction):
    if not user_level:
        await interaction.response.send_message("No leveling data yet.", ephemeral=True)
        return
    sorted_users = sorted(user_level.items(), key=lambda x: x[1], reverse=True)[:10]
    lines = []
    for i, (uid, lvl) in enumerate(sorted_users, 1):
        user = interaction.guild.get_member(uid)
        name = user.display_name if user else f"User ID {uid}"
        lines.append(f"{i}. {name} - Level {lvl}")
    await interaction.response.send_message("🏆 Leaderboard:\n" + "\n".join(lines))

@tree.command(name="whatcommands", description="List all commands")
async def whatcommands(interaction: discord.Interaction):
    cmds = [cmd.name for cmd in bot.tree.walk_commands()]
    await interaction.response.send_message("Available commands:\n" + ", ".join(cmds), ephemeral=True)

# --------- Key response filter (example) ---------
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # XP and leveling
    leveled_up, new_level = add_xp(message.author.id)
    if leveled_up:
        await message.channel.send(f"🎉 Congrats {message.author.mention}, you reached level {new_level}!")

    # Example key response: if user says "hello"
    if "hello" in message.content.lower():
        await message.channel.send(f"Hello {message.author.mention}! 👋")

    await bot.process_commands(message)

# --------- Main ---------
if __name__ == "__main__":
    keep_alive()
    TOKEN = os.getenv("DISCORD_TOKEN")  # Put your token in environment variables
    if not TOKEN:
        print("Error: DISCORD_TOKEN environment variable not set.")
        exit(1)
    bot.run(TOKEN)
