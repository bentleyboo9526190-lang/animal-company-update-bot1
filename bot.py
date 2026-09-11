import os
import json
import logging
import re
from datetime import datetime, timezone
from threading import Thread

import aiohttp
import discord
from discord.ext import commands, tasks
from flask import Flask
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# CONFIG
# ============================================================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

UPDATE_CHANNEL_ID = int(
    os.getenv("UPDATE_CHANNEL_ID", "1547679561960132695")
)

UPDATE_ROLE_ID = int(
    os.getenv("UPDATE_ROLE_ID", "1547729517395714178")
)

ANIMAL_COMPANY_APP_ID = "7190422614401072"

QUEST_STORE_DB_URL = (
    "https://queststoredb.com/game/"
    "animal-company-7190422614401072/"
)

META_STORE_URL = (
    "https://www.meta.com/experiences/"
    "animal-company/7190422614401072/"
)

STATE_FILE = "update_data.json"

# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

log = logging.getLogger("animal-company-bot")

# ============================================================
# FLASK
# ============================================================

app = Flask(__name__)


@app.route("/")
def home():
    return "Animal Company Update Bot is running."


def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


# ============================================================
# DISCORD
# ============================================================

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

# ============================================================
# STATE
# ============================================================


def load_state():
    if not os.path.exists(STATE_FILE):
        return None

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    except Exception as e:
        log.warning(f"Could not read {STATE_FILE}: {e}")
        return None


def save_state(version, version_code):
    data = {
        "version": version,
        "version_code": str(version_code),
        "saved_at": datetime.now(timezone.utc).isoformat()
    }

    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ============================================================
# QUEST STORE DB
# ============================================================


async def get_queststoredb_version():
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/151.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml",
    }

    try:
        timeout = aiohttp.ClientTimeout(total=20)

        async with aiohttp.ClientSession(
            headers=headers
        ) as session:

            async with session.get(
                QUEST_STORE_DB_URL,
                timeout=timeout
            ) as response:

                text = await response.text()

                log.info(
                    f"Quest Store DB request: HTTP {response.status}"
                )

                if response.status != 200:
                    log.warning(
                        f"Quest Store DB returned HTTP "
                        f"{response.status}"
                    )
                    return None

                # ------------------------------------------------
                # Find the app version.
                #
                # Quest Store DB currently renders:
                #
                # app version | 1.90.0.3474
                # ------------------------------------------------

                patterns = [
                    r"app version\s*</[^>]+>\s*"
                    r"(?:<[^>]+>\s*)?"
                    r"([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)",

                    r"app version\s*\|\s*"
                    r"([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)",

                    r"app.version[^0-9]*"
                    r"([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)",
                ]

                version = None

                for pattern in patterns:
                    match = re.search(
                        pattern,
                        text,
                        re.IGNORECASE | re.DOTALL
                    )

                    if match:
                        version = match.group(1)
                        break

                # ------------------------------------------------
                # More general fallback.
                # ------------------------------------------------

                if not version:
                    versions = re.findall(
                        r"\b\d+\.\d+\.\d+\.\d+\b",
                        text
                    )

                    if versions:
                        # Prefer versions close to "app version".
                        position = text.lower().find(
                            "app version"
                        )

                        if position >= 0:
                            nearby = text[
                                max(0, position - 100):
                                position + 500
                            ]

                            nearby_versions = re.findall(
                                r"\b\d+\.\d+\.\d+\.\d+\b",
                                nearby
                            )

                            if nearby_versions:
                                version = nearby_versions[0]

                        if not version:
                            version = versions[0]

                if not version:
                    log.warning(
                        "Quest Store DB page did not contain "
                        "a recognizable app version."
                    )
                    return None

                log.info(
                    f"Quest Store DB version: {version}"
                )

                # The version-code portion is the final number.
                version_code = version.split(".")[-1]

                log.info(
                    f"Quest Store DB version code: "
                    f"{version_code}"
                )

                return {
                    "version": version,
                    "version_code": version_code,
                }

    except Exception as e:
        log.warning(
            f"Quest Store DB request failed: {e}"
        )

        return None


# ============================================================
# METAMETADATA
#
# Used ONLY for artwork so your existing embed stays the same.
# It is NOT used for version detection anymore.
# ============================================================


async def get_metametadata():
    url = (
        "https://raw.githubusercontent.com/"
        "threethan/MetaMetadata/main/data/common/"
        "woosterGames.animalCompany.json"
    )

    try:
        async with aiohttp.ClientSession() as session:

            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=20)
            ) as response:

                text = await response.text()

                log.info(
                    f"MetaMetadata artwork request: "
                    f"HTTP {response.status}"
                )

                if response.status != 200:
                    return {}

                try:
                    return json.loads(text)

                except json.JSONDecodeError:
                    log.warning(
                        "MetaMetadata returned invalid JSON."
                    )
                    return {}

    except Exception as e:
        log.warning(
            f"MetaMetadata request failed: {e}"
        )
        return {}


# ============================================================
# CURRENT APP INFO
# ============================================================


async def get_current_app_info():

    # Version comes from Quest Store DB.
    version_info = await get_queststoredb_version()

    if not version_info:
        return None

    # Artwork comes from MetaMetadata.
    metadata = await get_metametadata()

    return {
        "version": version_info["version"],
        "version_code": version_info["version_code"],
        "metadata": metadata,
    }


# ============================================================
# EMBED
# ============================================================


def build_update_embed(
    old_version,
    new_version,
    version_code,
    metadata
):

    embed = discord.Embed(
        title="📦 New Animal Company Update!",
        color=discord.Color.blurple(),
        timestamp=datetime.now(timezone.utc)
    )

    logo = (
        metadata.get("logo")
        or metadata.get("icon")
    )

    thumbnail = (
        metadata.get("icon")
        or metadata.get("logo")
    )

    artwork = (
        metadata.get("hero")
        or metadata.get("landscape")
        or metadata.get("portrait")
        or metadata.get("square")
    )

    # --------------------------------------------------------
    # Author
    # --------------------------------------------------------

    if logo:
        embed.set_author(
            name="Animal Company",
            icon_url=logo
        )
    else:
        embed.set_author(
            name="Animal Company"
        )

    # --------------------------------------------------------
    # Version row
    # --------------------------------------------------------

    embed.add_field(
        name="⬅️ Previous Version",
        value=f"`{old_version}`",
        inline=True
    )

    embed.add_field(
        name="📦 New Version",
        value=f"`{new_version}`",
        inline=True
    )

    embed.add_field(
        name="🔢 Version Code",
        value=f"`{version_code}`",
        inline=True
    )

    # --------------------------------------------------------
    # Released
    # --------------------------------------------------------

    embed.add_field(
        name="🕐 Released",
        value=(
            f"<t:{int(datetime.now(timezone.utc).timestamp())}:F>"
        ),
        inline=False
    )

    # --------------------------------------------------------
    # Channel + Store
    # --------------------------------------------------------

    embed.add_field(
        name="📡 Channel",
        value="`LIVE`",
        inline=True
    )

    embed.add_field(
        name="🔗 Meta Store",
        value=(
            f"[Open Animal Company page]"
            f"({META_STORE_URL})"
        ),
        inline=True
    )

    # --------------------------------------------------------
    # Images
    # --------------------------------------------------------

    if thumbnail:
        embed.set_thumbnail(
            url=thumbnail
        )

    if artwork:
        embed.set_image(
            url=artwork
        )

    return embed


# ============================================================
# SEND UPDATE
# ============================================================


async def send_update(
    old_version,
    new_version,
    version_code,
    metadata
):

    channel = bot.get_channel(
        UPDATE_CHANNEL_ID
    )

    if channel is None:
        try:
            channel = await bot.fetch_channel(
                UPDATE_CHANNEL_ID
            )

        except Exception as e:
            log.error(
                f"Could not find update channel: {e}"
            )
            return

    embed = build_update_embed(
        old_version,
        new_version,
        version_code,
        metadata
    )

    role_ping = f"<@&{UPDATE_ROLE_ID}>"

    await channel.send(
        content=role_ping,
        embed=embed,
        allowed_mentions=discord.AllowedMentions(
            roles=True
        )
    )

    log.info(
        f"Update notification sent: "
        f"{old_version} -> {new_version} "
        f"({version_code})"
    )


# ============================================================
# UPDATE CHECKER
# ============================================================


@tasks.loop(seconds=20)
async def update_checker():

    log.info(
        "Checking Animal Company version..."
    )

    info = await get_current_app_info()

    if not info:
        log.warning(
            "Could not determine current version."
        )
        return

    new_version = info["version"]
    new_version_code = str(
        info["version_code"]
    )

    metadata = info["metadata"]

    saved = load_state()

    # --------------------------------------------------------
    # First run
    # --------------------------------------------------------

    if not saved:

        log.info(
            f"No previous saved version. "
            f"Saving {new_version} "
            f"({new_version_code}) "
            f"without notification."
        )

        save_state(
            new_version,
            new_version_code
        )

        return

    old_version = str(
        saved.get("version", "")
    )

    old_version_code = str(
        saved.get("version_code", "")
    )

    # --------------------------------------------------------
    # No update
    # --------------------------------------------------------

    if (
        old_version == new_version
        and old_version_code == new_version_code
    ):

        log.info(
            f"No update. Current version: "
            f"{new_version} "
            f"({new_version_code})"
        )

        return

    # --------------------------------------------------------
    # Update detected
    # --------------------------------------------------------

    log.info(
        f"UPDATE FOUND: "
        f"{old_version} ({old_version_code}) "
        f"-> "
        f"{new_version} ({new_version_code})"
    )

    await send_update(
        old_version,
        new_version,
        new_version_code,
        metadata
    )

    save_state(
        new_version,
        new_version_code
    )


@update_checker.before_loop
async def before_update_checker():

    await bot.wait_until_ready()


# ============================================================
# TEST COMMAND
# ============================================================


@bot.command()
@commands.has_permissions(administrator=True)
async def testupdate(ctx):

    metadata = await get_metametadata()

    await send_update(
        "1.90.1.3492",
        "1.90.2.3504",
        "3504",
        metadata
    )

    await ctx.send(
        "✅ Test update sent."
    )


# ============================================================
# CHECK VERSION COMMAND
# ============================================================


@bot.command()
@commands.has_permissions(administrator=True)
async def checkversion(ctx):

    await ctx.send(
        "🔎 Checking Quest Store DB..."
    )

    info = await get_current_app_info()

    if not info:

        await ctx.send(
            "❌ Quest Store DB did not return a version."
        )

        return

    await ctx.send(
        f"📦 Version: `{info['version']}`\n"
        f"🔢 Version Code: `{info['version_code']}`"
    )


# ============================================================
# READY
# ============================================================


@bot.event
async def on_ready():

    log.info(
        f"Logged in as {bot.user}"
    )

    log.info(
        f"Bot ID: {bot.user.id}"
    )

    if not update_checker.is_running():

        update_checker.start()

        log.info(
            "Automatic update checker started "
            "(every 20 seconds)."
        )


# ============================================================
# START
# ============================================================


if __name__ == "__main__":

    if not DISCORD_TOKEN:
        raise RuntimeError(
            "DISCORD_TOKEN environment variable is missing."
        )

    Thread(
        target=run_web,
        daemon=True
    ).start()

    bot.run(DISCORD_TOKEN)
