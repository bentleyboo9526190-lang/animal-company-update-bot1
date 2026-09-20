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

# Helper channel
HELPER_CHANNEL_ID = 1546998948844281946

# Render Web Service
RENDER_URL = "https://animal-company-update-bot1.onrender.com/"

# Animal Company app
ANIMAL_COMPANY_APP_ID = "7190422614401072"

# ============================================================
# VERSION SOURCES
# ============================================================

# Primary source
VRDB_URL = (
    "https://vrdb.app/game/"
    "animal-company/7190422614401072"
)

# Backup source
QUEST_STORE_DB_URL = (
    "https://queststoredb.com/game/"
    "animal-company-7190422614401072/"
)

# Meta Store - used only as the clickable Discord link
META_STORE_URL = (
    "https://www.meta.com/experiences/"
    "animal-company/7190422614401072/"
)

# ============================================================
# STATE
# ============================================================

STATE_FILE = "update_data.json"

# ============================================================
# VERSION SAFETY
# ============================================================

# Newest version we already know is legitimate.
#
# The bot will NEVER move backwards below this version.

KNOWN_GOOD_VERSION = "1.91.0.3570"

# A new version must be seen this many consecutive times
# before the bot announces it.
#
# This prevents one bad web request from causing a fake update.

REQUIRED_CONFIRMATIONS = 2

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

    app.run(
        host="0.0.0.0",
        port=port
    )


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
# VERSION FUNCTIONS
# ============================================================


def version_tuple(version):
    """
    Converts:

        1.91.1.3570

    into:

        (1, 91, 1, 3570)
    """

    try:

        parts = version.strip().split(".")

        if len(parts) != 4:
            return (0, 0, 0, 0)

        return tuple(
            int(part)
            for part in parts
        )

    except Exception:

        return (0, 0, 0, 0)


def is_valid_version(version):
    """
    Makes sure the version is exactly in:

        X.X.X.X

    format.
    """

    if not isinstance(version, str):
        return False

    return bool(
        re.fullmatch(
            r"\d+\.\d+\.\d+\.\d+",
            version.strip()
        )
    )


def is_newer_version(
    new_version,
    old_version
):

    return (
        version_tuple(new_version)
        > version_tuple(old_version)
    )


def get_version_code(version):

    try:
        return version.split(".")[-1]

    except Exception:

        return ""


# ============================================================
# STATE
# ============================================================


def load_state():

    if not os.path.exists(STATE_FILE):
        return None

    try:

        with open(
            STATE_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)

    except Exception as e:

        log.warning(
            f"Could not read {STATE_FILE}: {e}"
        )

        return None


def save_state(
    version,
    version_code,
    pending_version=None,
    pending_count=0
):

    data = {
        "version": version,
        "version_code": str(version_code),
        "saved_at": datetime.now(
            timezone.utc
        ).isoformat(),

        "pending_version": pending_version,
        "pending_count": pending_count
    }

    with open(
        STATE_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            indent=2
        )


# ============================================================
# RENDER KEEP-ALIVE
# ============================================================


async def ping_render():

    try:

        timeout = aiohttp.ClientTimeout(
            total=15
        )

        async with aiohttp.ClientSession() as session:

            async with session.get(
                RENDER_URL,
                timeout=timeout
            ) as response:

                log.info(
                    f"Keep-alive ping: "
                    f"HTTP {response.status}"
                )

    except Exception as e:

        log.warning(
            f"Keep-alive ping failed: {e}"
        )


@tasks.loop(minutes=10)
async def render_keep_alive():

    await ping_render()


@render_keep_alive.before_loop
async def before_render_keep_alive():

    await bot.wait_until_ready()


# ============================================================
# HELPER MESSAGE
# ============================================================


async def send_helper_message():

    channel = bot.get_channel(
        HELPER_CHANNEL_ID
    )

    if channel is None:

        try:

            channel = await bot.fetch_channel(
                HELPER_CHANNEL_ID
            )

        except Exception as e:

            log.warning(
                f"Could not find helper channel: {e}"
            )

            return

    try:

        async for message in channel.history(
            limit=20
        ):

            if (
                message.author == bot.user
                and
                "I am larplyboovr's helper"
                in message.content
            ):

                log.info(
                    "Helper message already exists."
                )

                return

    except Exception as e:

        log.warning(
            f"Could not check helper channel history: {e}"
        )

    try:

        await channel.send(
            "🤖 **I am larplyboovr's helper!**\n"
            "🟢 I'm online and ready to help."
        )

        log.info(
            "Helper message sent."
        )

    except Exception as e:

        log.warning(
            f"Could not send helper message: {e}"
        )


# ============================================================
# HTTP SESSION
# ============================================================


async def fetch_page(url):

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/153.0.0.0 Safari/537.36"
        ),

        "Accept": (
            "text/html,"
            "application/xhtml+xml,"
            "application/xml;q=0.9,"
            "*/*;q=0.8"
        )
    }

    try:

        timeout = aiohttp.ClientTimeout(
            total=20
        )

        async with aiohttp.ClientSession(
            headers=headers
        ) as session:

            async with session.get(
                url,
                timeout=timeout
            ) as response:

                text = await response.text()

                log.info(
                    f"Version source request: "
                    f"{url} -> HTTP {response.status}"
                )

                if response.status != 200:

                    return None

                return text

    except Exception as e:

        log.warning(
            f"Could not fetch {url}: {e}"
        )

        return None


# ============================================================
# VRDB VERSION
# ============================================================


async def get_vrdb_version():

    text = await fetch_page(
        VRDB_URL
    )

    if not text:
        return None

    # VRDB normally displays:
    #
    # Version: 1.91.1.3570

    patterns = [

        r"Version:\s*"
        r"([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)",

        r'"version"\s*:\s*"'
        r"([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)",

        r"\bVersion\b[^0-9]+"
        r"([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)"
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE | re.DOTALL
        )

        if match:

            version = match.group(1)

            if is_valid_version(version):

                log.info(
                    f"VRDB version: {version}"
                )

                return {
                    "version": version,
                    "version_code": get_version_code(
                        version
                    )
                }

    log.warning(
        "VRDB did not contain a recognizable version."
    )

    return None


# ============================================================
# QUEST STORE DB VERSION
# ============================================================


async def get_queststoredb_version():

    text = await fetch_page(
        QUEST_STORE_DB_URL
    )

    if not text:
        return None

    patterns = [

        r"app version\s*</[^>]+>\s*"
        r"(?:<[^>]+>\s*)?"
        r"([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)",

        r"app version\s*\|\s*"
        r"([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)",

        r"app.version[^0-9]*"
        r"([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)"
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE | re.DOTALL
        )

        if match:

            version = match.group(1)

            if is_valid_version(version):

                log.info(
                    f"Quest Store DB version: {version}"
                )

                return {
                    "version": version,
                    "version_code": get_version_code(
                        version
                    )
                }

    log.warning(
        "Quest Store DB did not contain "
        "a recognizable version."
    )

    return None


# ============================================================
# GET BEST VERSION
# ============================================================


async def get_best_version():

    vrdb = await get_vrdb_version()

    queststore = await get_queststoredb_version()

    candidates = []

    if vrdb:

        candidates.append(
            (
                vrdb["version"],
                "VRDB"
            )
        )

    if queststore:

        candidates.append(
            (
                queststore["version"],
                "Quest Store DB"
            )
        )

    if not candidates:

        log.warning(
            "No version source returned a valid version."
        )

        return None

    # --------------------------------------------------------
    # Remove versions below the known-good version.
    # --------------------------------------------------------

    valid_candidates = []

    for version, source in candidates:

        if is_newer_version(
            version,
            KNOWN_GOOD_VERSION
        ) or version == KNOWN_GOOD_VERSION:

            valid_candidates.append(
                (
                    version,
                    source
                )
            )

        else:

            log.warning(
                f"Ignoring stale source result: "
                f"{version} from {source}"
            )

    # --------------------------------------------------------
    # If everything is stale, use the known-good version.
    # --------------------------------------------------------

    if not valid_candidates:

        log.warning(
            "All external version sources are "
            "older than the known-good version."
        )

        return {
            "version": KNOWN_GOOD_VERSION,
            "version_code": get_version_code(
                KNOWN_GOOD_VERSION
            ),
            "source": "KNOWN_GOOD"
        }

    # --------------------------------------------------------
    # Pick the newest valid version.
    # --------------------------------------------------------

    valid_candidates.sort(
        key=lambda item: version_tuple(
            item[0]
        ),
        reverse=True
    )

    best_version = valid_candidates[0][0]
    best_source = valid_candidates[0][1]

    log.info(
        f"Best detected version: "
        f"{best_version} "
        f"(source: {best_source})"
    )

    # Show all source results for debugging.
    for version, source in candidates:

        log.info(
            f"Source result: "
            f"{source} = {version}"
        )

    return {
        "version": best_version,
        "version_code": get_version_code(
            best_version
        ),
        "source": best_source
    }


# ============================================================
# METAMETADATA
#
# Artwork only.
# NOT used for version detection.
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
                timeout=aiohttp.ClientTimeout(
                    total=20
                )
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

    version_info = (
        await get_best_version()
    )

    if not version_info:

        return None

    metadata = (
        await get_metametadata()
    )

    return {
        "version": version_info["version"],
        "version_code": version_info["version_code"],
        "source": version_info["source"],
        "metadata": metadata
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
        timestamp=datetime.now(
            timezone.utc
        )
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
    # Versions
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
    # Channel
    # --------------------------------------------------------

    embed.add_field(
        name="📡 Channel",
        value="`LIVE`",
        inline=True
    )

    # --------------------------------------------------------
    # Meta Store
    # --------------------------------------------------------

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

    role_ping = (
        f"<@&{UPDATE_ROLE_ID}>"
    )

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

    info = (
        await get_current_app_info()
    )

    if not info:

        log.warning(
            "Could not determine current version."
        )

        return

    detected_version = str(
        info["version"]
    )

    detected_version_code = str(
        info["version_code"]
    )

    source = info["source"]

    metadata = info["metadata"]

    log.info(
        f"Detected version: "
        f"{detected_version} "
        f"({detected_version_code}) "
        f"from {source}"
    )

    # ========================================================
    # LOAD STATE
    # ========================================================

    saved = load_state()

    # ========================================================
    # FIRST RUN
    # ========================================================

    if not saved:

        if not is_newer_version(
            detected_version,
            KNOWN_GOOD_VERSION
        ):

            log.info(
                f"First run detected "
                f"{detected_version}, which is not "
                f"newer than known-good "
                f"{KNOWN_GOOD_VERSION}."
            )

            save_state(
                KNOWN_GOOD_VERSION,
                get_version_code(
                    KNOWN_GOOD_VERSION
                )
            )

            return

        log.info(
            f"No saved state. "
            f"Saving {detected_version} "
            f"without notification."
        )

        save_state(
            detected_version,
            detected_version_code
        )

        return

    # ========================================================
    # SAVED VERSION
    # ========================================================

    saved_version = str(
        saved.get(
            "version",
            ""
        )
    )

    saved_version_code = str(
        saved.get(
            "version_code",
            ""
        )
    )

    pending_version = saved.get(
        "pending_version"
    )

    pending_count = int(
        saved.get(
            "pending_count",
            0
        )
    )

    log.info(
        f"Saved version: "
        f"{saved_version} "
        f"({saved_version_code})"
    )

    # ========================================================
    # REPAIR OLD STATE
    # ========================================================

    if is_newer_version(
        KNOWN_GOOD_VERSION,
        saved_version
    ):

        log.warning(
            f"Saved version {saved_version} "
            f"is below known-good "
            f"{KNOWN_GOOD_VERSION}."
        )

        log.info(
            f"Repairing state to "
            f"{KNOWN_GOOD_VERSION}."
        )

        save_state(
            KNOWN_GOOD_VERSION,
            get_version_code(
                KNOWN_GOOD_VERSION
            )
        )

        saved_version = KNOWN_GOOD_VERSION
        saved_version_code = get_version_code(
            KNOWN_GOOD_VERSION
        )

        pending_version = None
        pending_count = 0

    # ========================================================
    # SAME VERSION
    # ========================================================

    if detected_version == saved_version:

        if pending_version:

            log.info(
                f"Pending version {pending_version} "
                f"disappeared, clearing confirmation."
            )

            save_state(
                saved_version,
                saved_version_code
            )

        log.info(
            f"No update. Current version: "
            f"{saved_version}"
        )

        return

    # ========================================================
    # DETECTED VERSION IS OLDER
    # ========================================================

    if not is_newer_version(
        detected_version,
        saved_version
    ):

        log.warning(
            f"Ignoring older/stale version: "
            f"{detected_version} "
            f"(saved: {saved_version})"
        )

        if pending_version:

            save_state(
                saved_version,
                saved_version_code
            )

        return

    # ========================================================
    # NEWER VERSION DETECTED
    # ========================================================

    log.info(
        f"Potential new version found: "
        f"{saved_version} -> {detected_version}"
    )

    # ========================================================
    # CONFIRMATION SYSTEM
    # ========================================================
    #
    # The same new version must be detected twice.
    #
    # Example:
    #
    # Check 1:
    # 1.91.1.3570
    #
    # Check 2:
    # 1.91.1.3570
    #
    # THEN notify.
    #
    # This prevents one bad web response from causing
    # an announcement.
    # ========================================================

    if pending_version == detected_version:

        pending_count += 1

    else:

        pending_version = detected_version
        pending_count = 1

    log.info(
        f"Confirmation for {detected_version}: "
        f"{pending_count}/{REQUIRED_CONFIRMATIONS}"
    )

    # ========================================================
    # NOT CONFIRMED YET
    # ========================================================

    if pending_count < REQUIRED_CONFIRMATIONS:

        save_state(
            saved_version,
            saved_version_code,
            pending_version,
            pending_count
        )

        log.info(
            f"Waiting for confirmation of "
            f"{detected_version}."
        )

        return

    # ========================================================
    # CONFIRMED NEW VERSION
    # ========================================================

    log.info(
        f"CONFIRMED NEW VERSION: "
        f"{saved_version} -> {detected_version}"
    )

    # --------------------------------------------------------
    # Send notification
    # --------------------------------------------------------

    await send_update(
        saved_version,
        detected_version,
        detected_version_code,
        metadata
    )

    # --------------------------------------------------------
    # Save the new version
    # --------------------------------------------------------

    save_state(
        detected_version,
        detected_version_code
    )

    log.info(
        f"Saved new version: "
        f"{detected_version} "
        f"({detected_version_code})"
    )


@update_checker.before_loop
async def before_update_checker():

    await bot.wait_until_ready()


# ============================================================
# TEST UPDATE COMMAND
# ============================================================


@bot.command()
@commands.has_permissions(
    administrator=True
)
async def testupdate(ctx):

    metadata = (
        await get_metametadata()
    )

    await send_update(
        "1.90.2.3504",
        "1.91.0.3549",
        "3549",
        metadata
    )

    await ctx.send(
        "✅ Test update sent."
    )


# ============================================================
# CHECK VERSION COMMAND
# ============================================================


@bot.command()
@commands.has_permissions(
    administrator=True
)
async def checkversion(ctx):

    await ctx.send(
        "🔎 Checking Animal Company version..."
    )

    info = (
        await get_current_app_info()
    )

    if not info:

        await ctx.send(
            "❌ Could not get a version."
        )

        return

    await ctx.send(
        f"📦 Version: `{info['version']}`\n"
        f"🔢 Version Code: `{info['version_code']}`\n"
        f"📡 Source: `{info['source']}`"
    )


# ============================================================
# DEBUG STATE COMMAND
# ============================================================


@bot.command()
@commands.has_permissions(
    administrator=True
)
async def checkstate(ctx):

    saved = load_state()

    if not saved:

        await ctx.send(
            "📁 No saved version."
        )

        return

    pending_version = saved.get(
        "pending_version"
    )

    pending_count = saved.get(
        "pending_count",
        0
    )

    message = (
        f"💾 Saved Version: "
        f"`{saved.get('version', 'unknown')}`\n"
        f"🔢 Saved Version Code: "
        f"`{saved.get('version_code', 'unknown')}`\n"
        f"⏳ Pending Version: "
        f"`{pending_version or 'None'}`\n"
        f"🔁 Confirmation Count: "
        f"`{pending_count}/{REQUIRED_CONFIRMATIONS}`"
    )

    await ctx.send(
        message
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

    # --------------------------------------------------------
    # Update checker
    # --------------------------------------------------------

    if not update_checker.is_running():

        update_checker.start()

        log.info(
            "Automatic update checker started "
            "(every 20 seconds)."
        )

    # --------------------------------------------------------
    # Render keep-alive
    # --------------------------------------------------------

    if not render_keep_alive.is_running():

        render_keep_alive.start()

        log.info(
            "Render keep-alive started "
            "(every 10 minutes)."
        )

    # --------------------------------------------------------
    # Helper message
    # --------------------------------------------------------

    await send_helper_message()


# ============================================================
# START
# ============================================================


if __name__ == "__main__":

    if not DISCORD_TOKEN:

        raise RuntimeError(
            "DISCORD_TOKEN environment variable "
            "is missing."
        )

    Thread(
        target=run_web,
        daemon=True
    ).start()

    bot.run(
        DISCORD_TOKEN
    )
