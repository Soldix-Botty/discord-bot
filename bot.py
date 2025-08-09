import discord
from discord.ext import commands
from flask import Flask
import threading
import os
import re
from datetime import datetime, timedelta

# Token from environment variables
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.messages = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

app = Flask("")

WELCOME_CHANNEL_ID = 1387583772030927100  # Your welcome channel ID

# Tracking data
command_usage = {}
message_counts = {}
user_xp = {}
user_levels = {}
voice_time = {}
user_last_voice = {}

# Flask keep-alive server
@app.route("/")
def home():
    return "Bot is alive!"

def run():
    print("🌐 Flask server started on port 8080")
    app.run(host="0.0.0.0", port=8080)

def keep_alive():
    t = threading.Thread(target=run)
    t.start()
    print("⏳ Keep-alive thread started")

# Helpers
def track_command(user_id, command_name):
    if user_id not in command_usage:
        command_usage[user_id] = {'kick': 0, 'ban': 0, 'timeout': 0, 'addxp': 0, 'say': 0}
    if command_name in command_usage[user_id]:
        command_usage[user_id][command_name] += 1

def parse_duration(duration_str):
    match = re.match(r"(\d+)([mhd])$", duration_str)
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
    level = user_xp[user_id] // 500  # 1 level per 500 XP
    if user_levels.get(user_id, 0) < level:
        user_levels[user_id] = level
        return level
    return None

def xp_to_next_level(user_id):
    xp = user_xp.get(user_id, 0)
    level = user_levels.get(user_id, 0)
    next_level_xp = (level + 1) * 500
    return next_level_xp - xp

# Events
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ Bot is online as {bot.user}!")

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
    message_counts[user_id] = message_counts.get(user_id, 0) + 1
    level_up = add_xp(user_id)
    if level_up:
        await message.channel.send(f"🎉 {message.author.mention} leveled up to level {level_up}!")

    # Level queries
    if message.content.lower() == "level?" or message.content.lower().startswith("level? "):
        mentioned = message.mentions[0] if message.mentions else message.author
        level = user_levels.get(mentioned.id, 0)
        xp = user_xp.get(mentioned.id, 0)
        await message.channel.send(f"📈 {mentioned.mention} is level {level} with {xp} XP.")

    if message.content.lower() == "xp left":
        left = xp_to_next_level(message.author.id)
        await message.channel.send(f"⏳ {message.author.mention}, you need {left} XP to reach the next level.")

    if message.content.lower() == "what commands" or bot.user in message.mentions:
        await message.channel.send(
            "📜 Available commands:\n"
            "• `/kick`, `/ban`, `/timeout`, `/untimeout`, `/purge`, `/cmdstats`, `/leaderboard`, `/addxp`, `/say` (admin only)\n"
            "• `!lock`, `!unlock` (admin only)\n"
            "• `level? @user` and `xp left` for everyone"
        )

    if message.content.lower() == "key":
        await message.channel.send('Dumb it\'s "vault". Say "ok gimme key role" to make me stop answering you.')

    await bot.process_commands(message)

@bot.event
async def on_voice_state_update(member, before, after):
    if after.channel and not before.channel:
        user_last_voice[member.id] = datetime.utcnow()
    elif before.channel and not after.channel:
        start = user_last_voice.get(member.id)
        if start:
            seconds = (datetime.utcnow() - start).total_seconds()
            voice_time[member.id] = voice_time.get(member.id, 0) + int(seconds)
            del user_last_voice[member.id]

# Slash Commands
@bot.tree.command(name="kick", description="Kick a user")
@commands.has_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    try:
        await member.kick(reason=reason)
        track_command(interaction.user.id, 'kick')
        await interaction.response.send_message(f"✅ {member} has been kicked.")
    except Exception:
        await interaction.response.send_message("❌ Kick failed. Do I have permissions?", ephemeral=True)

@bot.tree.command(name="ban", description="Ban a user")
@commands.has_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    try:
        await member.ban(reason=reason)
        track_command(interaction.user.id, 'ban')
        await interaction.response.send_message(f"✅ {member} has been banned.")
    except Exception:
        await interaction.response.send_message("❌ Ban failed. Do I have permissions?", ephemeral=True)

@bot.tree.command(name="timeout", description="Timeout a user")
@commands.has_permissions(moderate_members=True)
async def timeout(interaction: discord.Interaction, member: discord.Member, duration: str, reason: str = "No reason provided"):
    seconds = parse_duration(duration)
    if not seconds:
        await interaction.response.send_message("❌ Invalid duration. Use formats like `5m`, `1h`, `2d`.", ephemeral=True)
        return
    try:
        until = discord.utils.utcnow() + timedelta(seconds=seconds)
        await member.timeout(until, reason=reason)
        track_command(interaction.user.id, 'timeout')
        await interaction.response.send_message(f"⏳ {member.mention} timed out for {duration}.")
    except Exception:
        await interaction.response.send_message("❌ Timeout failed. Do I have permissions?", ephemeral=True)

@bot.tree.command(name="untimeout", description="Remove timeout")
@commands.has_permissions(moderate_members=True)
async def untimeout(interaction: discord.Interaction, member: discord.Member):
    try:
        await member.timeout(None)
        await interaction.response.send_message(f"✅ Timeout removed for {member.mention}.")
    except Exception:
        await interaction.response.send_message("❌ Untimeout failed.", ephemeral=True)

@bot.tree.command(name="purge", description="Delete messages")
@commands.has_permissions(manage_messages=True)
async def purge(interaction: discord.Interaction, amount: int):
    if amount < 1 or amount > 100:
        await interaction.response.send_message("❌ Choose an amount between 1 and 100.", ephemeral=True)
        return
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.response.send_message(f"🧹 Deleted {len(deleted)} messages.", ephemeral=True)

@bot.tree.command(name="cmdstats", description="Check moderation command usage")
async def cmdstats(interaction: discord.Interaction, member: discord.Member):
    stats = command_usage.get(member.id, {'kick': 0, 'ban': 0, 'timeout': 0, 'addxp': 0, 'say': 0})
    await interaction.response.send_message(
        f"📊 Stats for {member.mention}:\n"
        f"• Kicks: {stats.get('kick', 0)}\n"
        f"• Bans: {stats.get('ban', 0)}\n"
        f"• Timeouts: {stats.get('timeout', 0)}\n"
        f"• XP Adds: {stats.get('addxp', 0)}\n"
        f"• Say Commands: {stats.get('say', 0)}"
    )

@bot.tree.command(name="addxp", description="Add XP to a user")
@commands.has_permissions(administrator=True)
async def addxp(interaction: discord.Interaction, member: discord.Member, amount: int):
    if amount < 1:
        await interaction.response.send_message("❌ Amount must be positive.", ephemeral=True)
        return
    user_xp[member.id] = user_xp.get(member.id, 0) + amount
    track_command(interaction.user.id, 'addxp')
    await interaction.response.send_message(f"✅ Added {amount} XP to {member.mention}.")

@bot.tree.command(name="say", description="Make the bot say something")
@commands.has_permissions(administrator=True)
async def say(interaction: discord.Interaction, *, message: str):
    track_command(interaction.user.id, 'say')
    await interaction.response.send_message(message)

@bot.tree.command(name="leaderboard", description="Show XP leaderboard")
async def leaderboard(interaction: discord.Interaction):
    if not user_xp:
        await interaction.response.send_message("No XP data available yet.")
        return
    sorted_users = sorted(user_xp.items(), key=lambda x: x[1], reverse=True)[:10]
    lines = []
    for rank, (user_id, xp) in enumerate(sorted_users, start=1):
        member = interaction.guild.get_member(user_id)
        name = member.name if member else f"User ID {user_id}"
        lines.append(f"#{rank} - {name}: {xp} XP")
    await interaction.response.send_message("🏆 **XP Leaderboard:**\n" + "\n".join(lines))

# Text commands to lock/unlock channel
@bot.command()
@commands.has_permissions(manage_channels=True)
async def lock(ctx):
    overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
    overwrite.send_messages = False
    await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
    await ctx.send("🔒 Channel locked.")

@bot.command()
@commands.has_permissions(manage_channels=True)
async def unlock(ctx):
    overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
    overwrite.send_messages = True
    await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
    await ctx.send("🔓 Channel unlocked.")

if __name__ == "__main__":
    keep_alive()
    print("🚀 Starting Discord bot...")
    bot.run(TOKEN)
