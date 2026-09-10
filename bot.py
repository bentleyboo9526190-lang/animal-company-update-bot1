import os
import json
import threading
from datetime import datetime, timezone

from flask import Flask
import aiohttp
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

load_dotenv()

# =========================
# SETTINGS
# =========================

TOKEN = os.getenv("DISCORD_TOKEN")

UPDATE_CHANNEL_ID = int(
    os.getenv("UPDATE_CHANNEL_ID", "0")
)

UPDATE_ROLE_ID = int(
    os.getenv("UPDATE_ROLE_ID", "0")
)

CHECK_MINUTES = 2

DATA_FILE = "update_data.json"

META_METADATA_URL = (
    "https://raw.githubusercontent.com/"
    "threethan/MetaMetadata/main/"
    "data/common/woosterGames.animalCompany.json"
)

META_STORE_URL = (
    "https://www.meta.com/experiences/"
    "quest/7190422614401072/"
)


# =========================
# FLASK / RENDER WEB SERVER
# =========================

app = Flask(__name__)


@app.route("/")
def home():
    return "Animal Company Update Bot is online!"


def run_web_server():

    port = int(
        os.getenv("PORT", "10000")
    )

    app.run(
        host="0.0.0.0",
        port=port
    )


web_thread = threading.Thread(
    target=run_web_server,
    daemon=True
)

web_thread.start()


# =========================
# DISCORD BOT
# =========================

intents = discord.Intents.default()

intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# =========================
# DATA STORAGE
# =========================

def default_data():

    return {
        "version": None,
        "version_code": None,
        "release_time": None
    }


def load_data():

    if not os.path.exists(DATA_FILE):

        return default_data()

    try:

        with open(
            DATA_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(file)

        return {
            "version": data.get("version"),
            "version_code": data.get("version_code"),
            "release_time": data.get("release_time")
        }

    except Exception as error:

        print(
            f"WARNING: Could not load saved data: {error}",
            flush=True
        )

        return default_data()


def save_data(data):

    try:

        with open(
            DATA_FILE,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                data,
                file,
                indent=4
            )

    except Exception as error:

        print(
            f"ERROR: Could not save data: {error}",
            flush=True
        )


# =========================
# DISCORD EMBED
# =========================

def make_update_embed(
    previous_version,
    new_version,
    version_code,
    release_time,
    image_url=None
):

    embed = discord.Embed(
        title="📦 New Animal Company Update!",
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

    embed.add_field(
        name="🛒 Meta Store",
        value=(
            f"[Open Animal Company page]"
            f"({META_STORE_URL})"
        ),
        inline=False
    )

    if image_url:

        embed.set_image(
            url=image_url
        )

    return embed


# =========================
# GET ANIMAL COMPANY DATA
# =========================

async def fetch_animal_company():

    timeout = aiohttp.ClientTimeout(
        total=20
    )

    headers = {
        "User-Agent":
            "AnimalCompanyUpdateBot/1.0",
        "Accept":
            "application/json"
    }

    async with aiohttp.ClientSession(
        timeout=timeout,
        headers=headers
    ) as session:

        async with session.get(
            META_METADATA_URL
        ) as response:

            response.raise_for_status()

            data = await response.json(
                content_type=None
            )

    version = str(
        data.get("version", "")
    ).strip()

    version_code = data.get(
        "versioncode"
    )

    if not version:

        raise ValueError(
            "Version was missing from the metadata."
        )

    if version_code is None:

        raise ValueError(
            "Version code was missing from the metadata."
        )

    image_url = (
        data.get("landscape")
        or data.get("hero")
        or data.get("portrait")
    )

    return {
        "version": version,
        "version_code": version_code,
        "image_url": image_url
    }


# =========================
# SEND UPDATE
# =========================

async def send_update(
    previous_version,
    new_version,
    version_code,
    release_time,
    image_url
):

    channel = bot.get_channel(
        UPDATE_CHANNEL_ID
    )

    if channel is None:

        print(
            "Channel not found in cache. "
            "Trying to fetch it...",
            flush=True
        )

        try:

            channel = await bot.fetch_channel(
                UPDATE_CHANNEL_ID
            )

        except Exception as error:

            print(
                f"ERROR: Could not find channel: {error}",
                flush=True
            )

            return

    embed = make_update_embed(
        previous_version=previous_version,
        new_version=new_version,
        version_code=version_code,
        release_time=release_time,
        image_url=image_url
    )

    role_mention = (
        f"<@&{UPDATE_ROLE_ID}>"
    )

    await channel.send(
        content=role_mention,
        embed=embed,
        allowed_mentions=discord.AllowedMentions(
            roles=True
        )
    )

    print(
        "Update notification sent successfully!",
        flush=True
    )


# =========================
# UPDATE CHECKER
# =========================

@tasks.loop(minutes=CHECK_MINUTES)
async def check_for_updates():

    print(
        "Checking for Animal Company updates...",
        flush=True
    )

    try:

        latest = await fetch_animal_company()

    except Exception as error:

        print(
            f"ERROR: Update check failed: {error}",
            flush=True
        )

        return

    latest_version = latest["version"]

    latest_code = latest["version_code"]

    image_url = latest["image_url"]

    print(
        f"Source: version={latest_version}, "
        f"version_code={latest_code}",
        flush=True
    )

    data = load_data()

    previous_version = data.get(
        "version"
    )

    previous_code = data.get(
        "version_code"
    )

    # =========================
    # FIRST STARTUP
    # =========================

    if (
        previous_version is None
        or previous_code is None
    ):

        data["version"] = latest_version

        data["version_code"] = latest_code

        data["release_time"] = None

        save_data(data)

        print(
            "First startup detected.",
            flush=True
        )

        print(
            f"Saved current version: "
            f"{latest_version} "
            f"({latest_code})",
            flush=True
        )

        print(
            "No notification sent because "
            "this is the initial version.",
            flush=True
        )

        return

    # =========================
    # NO UPDATE
    # =========================

    if (
        str(previous_version)
        == str(latest_version)
        and
        str(previous_code)
        == str(latest_code)
    ):

        print(
            "No new Animal Company update.",
            flush=True
        )

        return

    # =========================
    # NEW UPDATE
    # =========================

    now = datetime.now(
        timezone.utc
    )

    release_time = now.strftime(
        "%B %d, %Y at %I:%M %p UTC"
    )

    print(
        "================================",
        flush=True
    )

    print(
        "NEW ANIMAL COMPANY UPDATE!",
        flush=True
    )

    print(
        f"Previous: {previous_version}",
        flush=True
    )

    print(
        f"New: {latest_version}",
        flush=True
    )

    print(
        f"Code: {latest_code}",
        flush=True
    )

    print(
        "================================",
        flush=True
    )

    try:

        await send_update(
            previous_version=previous_version,
            new_version=latest_version,
            version_code=latest_code,
            release_time=release_time,
            image_url=image_url
        )

    except Exception as error:

        print(
            f"ERROR: Could not send update: {error}",
            flush=True
        )

        return

    # Save only after the Discord message succeeds.

    data["version"] = latest_version

    data["version_code"] = latest_code

    data["release_time"] = release_time

    save_data(data)

    print(
        "New version saved.",
        flush=True
    )


# =========================
# BEFORE CHECKER STARTS
# =========================

@check_for_updates.before_loop
async def before_update_check():

    print(
        "Waiting for Discord to become ready...",
        flush=True
    )

    await bot.wait_until_ready()

    print(
        "Discord is ready. Starting update checker.",
        flush=True
    )


# =========================
# BOT READY
# =========================

@bot.event
async def on_ready():

    print(
        "================================",
        flush=True
    )

    print(
        f"Logged in as {bot.user}",
        flush=True
    )

    print(
        f"Bot ID: {bot.user.id}",
        flush=True
    )

    print(
        f"Update Channel ID: "
        f"{UPDATE_CHANNEL_ID}",
        flush=True
    )

    print(
        f"Update Role ID: "
        f"{UPDATE_ROLE_ID}",
        flush=True
    )

    print(
        f"Checking every "
        f"{CHECK_MINUTES} minutes.",
        flush=True
    )

    print(
        "================================",
        flush=True
    )

    if not check_for_updates.is_running():

        check_for_updates.start()

        print(
            "Automatic update checker STARTED.",
            flush=True
        )

    else:

        print(
            "Automatic update checker is "
            "already running.",
            flush=True
        )


# =========================
# MANUAL TEST COMMAND
# =========================

@bot.command()
@commands.has_permissions(
    administrator=True
)
async def testupdate(ctx):

    now = datetime.now(
        timezone.utc
    )

    release_time = now.strftime(
        "%B %d, %Y at %I:%M %p UTC"
    )

    embed = make_update_embed(
        previous_version="1.90.0.3474",
        new_version="1.90.1.3492",
        version_code="3492",
        release_time=release_time
    )

    role_mention = (
        f"<@&{UPDATE_ROLE_ID}>"
    )

    await ctx.send(
        content=role_mention,
        embed=embed,
        allowed_mentions=discord.AllowedMentions(
            roles=True
        )
    )

    print(
        "Manual test update sent.",
        flush=True
    )


# =========================
# ERROR HANDLER
# =========================

@bot.event
async def on_command_error(
    ctx,
    error
):

    if isinstance(
        error,
        commands.MissingPermissions
    ):

        return

    if isinstance(
        error,
        commands.CommandNotFound
    ):

        return

    print(
        f"Command error: {error}",
        flush=True
    )


# =========================
# START
# =========================

if not TOKEN:

    raise RuntimeError(
        "DISCORD_TOKEN is missing!"
    )


if UPDATE_CHANNEL_ID == 0:

    raise RuntimeError(
        "UPDATE_CHANNEL_ID is missing!"
    )


if UPDATE_ROLE_ID == 0:

    raise RuntimeError(
        "UPDATE_ROLE_ID is missing!"
    )


print(
    "Starting Animal Company Update Bot...",
    flush=True
)

print(
    "Connecting to Discord...",
    flush=True
)

bot.run(TOKEN)
