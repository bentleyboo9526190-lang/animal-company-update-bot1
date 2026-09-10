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

TOKEN = os.getenv("DISCORD_TOKEN")
UPDATE_CHANNEL_ID = int(os.getenv("UPDATE_CHANNEL_ID", "0"))
UPDATE_ROLE_ID = int(os.getenv("UPDATE_ROLE_ID", "0"))

# Animal Company public Quest metadata
META_METADATA_URL = (
    "https://raw.githubusercontent.com/threethan/MetaMetadata/main/"
    "data/common/woosterGames.animalCompany.json"
)

META_STORE_URL = "https://www.meta.com/experiences/quest/7190422614401072/"

DATA_FILE = "update_data.json"
CHECK_MINUTES = 2


# =========================
# RENDER WEB SERVER
# =========================

app = Flask(__name__)


@app.route("/")
def home():
    return "Animal Company Update Bot is online!"


def run_web_server():
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)


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
# SAVED UPDATE DATA
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
        with open(DATA_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)

        return {
            "version": data.get("version"),
            "version_code": data.get("version_code"),
            "release_time": data.get("release_time")
        }

    except Exception as error:

        print(
            f"WARNING: Could not read {DATA_FILE}: {error}"
        )

        return default_data()


def save_data(data):

    try:

        with open(DATA_FILE, "w", encoding="utf-8") as file:
            json.dump(
                data,
                file,
                indent=4
            )

    except Exception as error:

        print(
            f"ERROR: Could not save {DATA_FILE}: {error}"
        )


# =========================
# UPDATE EMBED
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
        color=discord.Color.green(),
        url=META_STORE_URL
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
        value=f"[Open Animal Company page]({META_STORE_URL})",
        inline=False
    )

    if image_url:
        embed.set_image(url=image_url)

    return embed


# =========================
# GET ANIMAL COMPANY DATA
# =========================

async def fetch_animal_company():

    timeout = aiohttp.ClientTimeout(
        total=20
    )

    headers = {
        "User-Agent": "AnimalCompanyUpdateBot/1.0",
        "Accept": "application/json"
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
            "Animal Company version was missing."
        )

    if version_code is None:

        raise ValueError(
            "Animal Company version code was missing."
        )

    try:

        version_code = int(
            version_code
        )

    except (TypeError, ValueError):

        version_code = str(
            version_code
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

        try:

            channel = await bot.fetch_channel(
                UPDATE_CHANNEL_ID
            )

        except Exception as error:

            print(
                f"ERROR: Could not find update channel: {error}"
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


# =========================
# CHECK FOR UPDATES
# =========================

@tasks.loop(minutes=CHECK_MINUTES)
async def check_for_updates():

    print(
        "Checking for Animal Company updates..."
    )

    try:

        latest = await fetch_animal_company()

    except Exception as error:

        print(
            f"ERROR: Animal Company check failed: {error}"
        )

        return

    latest_version = latest["version"]
    latest_code = latest["version_code"]
    image_url = latest["image_url"]

    data = load_data()

    previous_version = data.get(
        "version"
    )

    previous_code = data.get(
        "version_code"
    )

    print(
        f"Source: version={latest_version}, "
        f"version_code={latest_code}"
    )

    # First startup.
    # Save the current version without sending an alert.
    if (
        previous_version is None
        or previous_code is None
    ):

        data["version"] = latest_version
        data["version_code"] = latest_code
        data["release_time"] = None

        save_data(data)

        print(
            "Initialized current Animal Company version: "
            f"{latest_version} ({latest_code})"
        )

        return

    # No change.
    if (
        str(previous_version)
        == str(latest_version)
        and
        str(previous_code)
        == str(latest_code)
    ):

        print(
            "No new Animal Company update."
        )

        return

    # =========================
    # NEW UPDATE FOUND
    # =========================

    now = datetime.now(
        timezone.utc
    )

    detected_time = now.strftime(
        "%B %d, %Y at %I:%M %p UTC"
    )

    print(
        "NEW UPDATE DETECTED: "
        f"{previous_version} -> {latest_version} "
        f"(code {latest_code})"
    )

    await send_update(
        previous_version=previous_version,
        new_version=latest_version,
        version_code=latest_code,
        release_time=detected_time,
        image_url=image_url
    )

    # Save new version
    data["version"] = latest_version
    data["version_code"] = latest_code
    data["release_time"] = detected_time

    save_data(data)


# =========================
# WAIT FOR DISCORD
# =========================

@check_for_updates.before_loop
async def before_update_check():

    await bot.wait_until_ready()


# =========================
# BOT STARTED
# =========================

@bot.event
async def on_ready():

    print(
        f"Logged in as {bot.user}"
    )

    print(
        f"Update Channel ID: {UPDATE_CHANNEL_ID}"
    )

    print(
        f"Update Role ID: {UPDATE_ROLE_ID}"
    )

    print(
        f"Checking every {CHECK_MINUTES} minutes."
    )

    print(
        f"Metadata source: {META_METADATA_URL}"
    )

    if not check_for_updates.is_running():

        check_for_updates.start()


# =========================
# TEST COMMAND
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


# =========================
# START BOT
# =========================

if not TOKEN:

    raise RuntimeError(
        "DISCORD_TOKEN is missing!"
    )


bot.run(TOKEN)
