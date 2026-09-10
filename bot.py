import os
import json
import asyncio
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
UPDATE_CHANNEL_ID = int(os.getenv("UPDATE_CHANNEL_ID", "0"))
UPDATE_ROLE_ID = int(os.getenv("UPDATE_ROLE_ID", "0"))

DATA_FILE = "update_data.json"


intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


def load_data():
    if not os.path.exists(DATA_FILE):
        return {
            "version": None,
            "version_code": None,
            "release_time": None
        }

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


def make_update_embed(
    previous_version,
    new_version,
    version_code,
    release_time
):
    embed = discord.Embed(
        title="📦 New Animal Company Update!",
        description="A new Animal Company update has been released!",
        color=discord.Color.green()
    )

    embed.add_field(
        name="⬅️ Previous Version",
        value=f"`{previous_version}`",
        inline=False
    )

    embed.add_field(
        name="📦 New Version",
        value=f"`{new_version}`",
        inline=False
    )

    embed.add_field(
        name="🔢 Version Code",
        value=f"`{version_code}`",
        inline=False
    )

    embed.add_field(
        name="🕐 Released",
        value=release_time,
        inline=False
    )

    embed.add_field(
        name="📡 Channel",
        value="`LIVE`",
        inline=False
    )

    return embed


async def send_update(
    previous_version,
    new_version,
    version_code,
    release_time
):
    channel = bot.get_channel(UPDATE_CHANNEL_ID)

    if channel is None:
        print("Update channel not found.")
        return

    embed = make_update_embed(
        previous_version,
        new_version,
        version_code,
        release_time
    )

    role_mention = f"<@&{UPDATE_ROLE_ID}>"

    await channel.send(
        content=role_mention,
        embed=embed,
        allowed_mentions=discord.AllowedMentions(
            roles=True
        )
    )


@tasks.loop(minutes=2)
async def check_for_updates():
    """
    Animal Company update checking will go here.

    This will eventually:
      1. Check the Animal Company update source.
      2. Get the newest version.
      3. Get the previous version.
      4. Get the version code.
      5. Get the release time.
      6. Compare it with update_data.json.
      7. Send a Discord notification if it changed.
    """

    print("Checking for Animal Company updates...")

    # Temporary placeholder.
    # We will replace this with the real update checker.


@check_for_updates.before_loop
async def before_update_check():
    await bot.wait_until_ready()


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    if not check_for_updates.is_running():
        check_for_updates.start()


@bot.command()
@commands.has_permissions(administrator=True)
async def testupdate(ctx):
    """
    Sends a test notification so we can verify
    the Discord embed and role ping.
    """

    now = datetime.now(timezone.utc)

    embed = make_update_embed(
        previous_version="1.90.0.3474",
        new_version="1.90.1.3492",
        version_code="3492",
        release_time=now.strftime(
            "%B %d, %Y at %I:%M %p UTC"
        )
    )

    role_mention = f"<@&{UPDATE_ROLE_ID}>"

    await ctx.send(
        content=role_mention,
        embed=embed,
        allowed_mentions=discord.AllowedMentions(
            roles=True
        )
    )


bot.run(TOKEN)
