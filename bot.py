import os
import json
import asyncio
import threading
import logging
from datetime import datetime, timezone

import aiohttp
import discord
from discord.ext import commands, tasks
from flask import Flask
from dotenv import load_dotenv


# ============================================================
# CONFIGURATION
# ============================================================

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

UPDATE_CHANNEL_ID = int(
    os.getenv(
        "UPDATE_CHANNEL_ID",
        "1547679561960132695"
    )
)

UPDATE_ROLE_ID = int(
    os.getenv(
        "UPDATE_ROLE_ID",
        "1547729517395714178"
    )
)

APP_ID = "7190422614401072"

CHECK_MINUTES = 5

DATA_FILE = "update_data.json"


# ============================================================
# OCULUS GRAPHQL
# ============================================================

OCULUS_GRAPHQL_URL = (
    "https://graph.oculus.com/graphql"
)

# Public Oculus Store token
OCULUS_TOKEN = (
    "OC|752908224809889|"
)

# Documented "Latest version of an App" query
LATEST_VERSION_DOC_ID = (
    "5373392672732392"
)

# Older documented "Versions of App" query
VERSIONS_DOC_ID = (
    "1586217024733717"
)


# ============================================================
# METADATA FALLBACK
# ============================================================

METADATA_URL = (
    "https://raw.githubusercontent.com/"
    "threethan/MetaMetadata/main/"
    "data/common/woosterGames.animalCompany.json"
)


# ============================================================
# META STORE
# ============================================================

META_STORE_URL = (
    "https://www.meta.com/experiences/"
    "animal-company/7190422614401072/"
)


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(
    "animal-company-bot"
)


# ============================================================
# FLASK WEB SERVER
# ============================================================

app = Flask(__name__)


@app.route("/")
def home():
    return "Animal Company Update Bot is online!"


@app.route("/health")
def health():
    return "OK"


def run_web_server():

    port = int(
        os.environ.get(
            "PORT",
            10000
        )
    )

    logger.info(
        "Starting Flask web server on port %s",
        port
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
        use_reloader=False
    )


# ============================================================
# DISCORD BOT
# ============================================================

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# ============================================================
# IMAGE CACHE
# ============================================================

ANIMAL_COMPANY_IMAGES = {
    "icon": None,
    "logo": None,
    "hero": None,
    "landscape": None,
    "portrait": None,
    "square": None
}


# ============================================================
# FILE STORAGE
# ============================================================

def load_saved_version():

    try:

        if not os.path.exists(DATA_FILE):
            return None

        with open(
            DATA_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            data = json.load(f)

        version = data.get("version")

        if version:

            logger.info(
                "Saved version loaded: %s",
                version
            )

        return version

    except Exception as e:

        logger.error(
            "Could not read %s: %s",
            DATA_FILE,
            e
        )

        return None


def save_version(
    version,
    version_code=None
):

    try:

        with open(
            DATA_FILE,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                {
                    "version": version,
                    "version_code": version_code,
                    "updated_at": datetime.now(
                        timezone.utc
                    ).isoformat()
                },
                f,
                indent=2
            )

        logger.info(
            "Saved version: %s",
            version
        )

    except Exception as e:

        logger.error(
            "Could not save version: %s",
            e
        )


# ============================================================
# VERSION HELPERS
# ============================================================

def normalize_version(version):

    if version is None:
        return None

    return str(version).strip()


def is_version_string(value):

    if value is None:
        return False

    value = str(value).strip()

    if not value:
        return False

    # Animal Company versions look like:
    # 1.90.2.3504
    parts = value.split(".")

    if len(parts) < 3:
        return False

    return all(
        part.isdigit()
        for part in parts
    )


def find_version_data(obj):

    """
    Search an unknown Oculus GraphQL response recursively.

    Different Oculus queries have returned slightly different
    response structures over time, so we search for version
    and version-code fields instead of assuming one exact layout.
    """

    if isinstance(obj, dict):

        version_keys = [
            "version",
            "version_name",
            "versionName"
        ]

        code_keys = [
            "version_code",
            "versioncode",
            "versionCode"
        ]

        version = None
        version_code = None

        for key in version_keys:

            value = obj.get(key)

            if is_version_string(value):

                version = str(value).strip()
                break

        for key in code_keys:

            value = obj.get(key)

            if value is not None:

                text = str(value).strip()

                if text.isdigit():

                    version_code = value
                    break

        if version:

            return {
                "version": version,
                "version_code": version_code
            }

        for value in obj.values():

            result = find_version_data(value)

            if result:
                return result

    elif isinstance(obj, list):

        for item in obj:

            result = find_version_data(item)

            if result:
                return result

    return None


# ============================================================
# OCULUS GRAPHQL REQUEST
# ============================================================

async def oculus_graphql_request(
    session,
    doc_id,
    variables
):

    try:

        timeout = aiohttp.ClientTimeout(
            total=20
        )

        headers = {
            "Accept": "application/json",
            "User-Agent": (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/151.0 Safari/537.36"
            ),
            "TE": "Trailers"
        }

        # Oculus expects the GraphQL parameters as form data
        # rather than the JSON body used by the previous code.

        form_data = {
            "access_token": OCULUS_TOKEN,
            "variables": json.dumps(
                variables,
                separators=(",", ":")
            ),
            "doc_id": doc_id
        }

        logger.info(
            "Sending Oculus GraphQL request with doc_id %s...",
            doc_id
        )

        async with session.post(
            OCULUS_GRAPHQL_URL,
            data=form_data,
            headers=headers,
            timeout=timeout
        ) as response:

            text = await response.text()

            logger.info(
                "Oculus GraphQL HTTP status: %s",
                response.status
            )

            if response.status != 200:

                logger.error(
                    "Oculus GraphQL HTTP %s: %s",
                    response.status,
                    text[:3000]
                )

                return None

            try:

                data = json.loads(text)

            except json.JSONDecodeError:

                logger.error(
                    "Oculus GraphQL returned invalid JSON: %s",
                    text[:3000]
                )

                return None

            if isinstance(data, dict) and data.get("errors"):

                logger.error(
                    "Oculus GraphQL returned errors: %s",
                    json.dumps(
                        data.get("errors"),
                        indent=2
                    )[:3000]
                )

                return None

            return data

    except asyncio.TimeoutError:

        logger.error(
            "Oculus GraphQL request timed out."
        )

        return None

    except aiohttp.ClientError as e:

        logger.error(
            "Oculus GraphQL network error: %s",
            e
        )

        return None

    except Exception as e:

        logger.exception(
            "Unexpected Oculus GraphQL error: %s",
            e
        )

        return None


# ============================================================
# LIVE OCULUS VERSION
# ============================================================

async def get_oculus_latest_version():

    logger.info(
        "=============================================="
    )

    logger.info(
        "TRYING LIVE OCULUS VERSION SOURCE..."
    )

    logger.info(
        "=============================================="
    )

    variables = {
        "itemId": APP_ID,
        "first": 5,
        "last": None,
        "after": None,
        "before": None,
        "forward": True,
        "ordering": None,
        "ratingScores": None,
        "hmdType": "MONTEREY"
    }

    async with aiohttp.ClientSession() as session:

        data = await oculus_graphql_request(
            session,
            LATEST_VERSION_DOC_ID,
            variables
        )

    if not data:

        logger.warning(
            "Live Oculus latest-version request failed."
        )

        return None

    logger.info(
        "Live Oculus request succeeded."
    )

    result = find_version_data(data)

    if not result:

        logger.error(
            "Oculus response did not contain a recognizable "
            "version."
        )

        logger.error(
            "Oculus response: %s",
            json.dumps(
                data,
                indent=2
            )[:8000]
        )

        return None

    version = result.get("version")
    version_code = result.get("version_code")

    logger.info(
        "LIVE OCULUS VERSION FOUND: %s",
        version
    )

    logger.info(
        "LIVE OCULUS VERSION CODE: %s",
        version_code
    )

    return {
        "version": normalize_version(version),
        "version_code": version_code,
        "channel": "LIVE"
    }


# ============================================================
# SECOND OCULUS VERSION QUERY
# ============================================================

async def get_oculus_versions_query():

    logger.info(
        "Trying secondary Oculus versions query..."
    )

    variables = {
        "id": APP_ID
    }

    async with aiohttp.ClientSession() as session:

        data = await oculus_graphql_request(
            session,
            VERSIONS_DOC_ID,
            variables
        )

    if not data:

        logger.warning(
            "Secondary Oculus versions query failed."
        )

        return None

    result = find_version_data(data)

    if not result:

        logger.warning(
            "Secondary Oculus response did not contain "
            "a recognizable version."
        )

        return None

    version = result.get("version")
    version_code = result.get("version_code")

    logger.info(
        "SECONDARY OCULUS VERSION FOUND: %s",
        version
    )

    logger.info(
        "SECONDARY OCULUS VERSION CODE: %s",
        version_code
    )

    return {
        "version": normalize_version(version),
        "version_code": version_code,
        "channel": "LIVE"
    }


# ============================================================
# METADATA FALLBACK
# ============================================================

async def get_metadata_fallback():

    logger.info(
        "Trying MetaMetadata fallback..."
    )

    try:

        timeout = aiohttp.ClientTimeout(
            total=20
        )

        async with aiohttp.ClientSession(
            timeout=timeout
        ) as session:

            async with session.get(
                METADATA_URL,
                headers={
                    "User-Agent":
                        "AnimalCompanyUpdateBot/1.0"
                }
            ) as response:

                text = await response.text()

                logger.info(
                    "MetaMetadata HTTP status: %s",
                    response.status
                )

                if response.status != 200:

                    logger.warning(
                        "MetaMetadata returned HTTP %s",
                        response.status
                    )

                    return None

                data = json.loads(text)

                global ANIMAL_COMPANY_IMAGES

                ANIMAL_COMPANY_IMAGES = {
                    "icon": data.get("icon"),
                    "logo": data.get("logo"),
                    "hero": data.get("hero"),
                    "landscape": data.get("landscape"),
                    "portrait": data.get("portrait"),
                    "square": data.get("square")
                }

                logger.info(
                    "Animal Company artwork URLs loaded."
                )

                version = data.get("version")
                version_code = data.get("versioncode")

                if not version:

                    logger.warning(
                        "MetaMetadata did not contain a version."
                    )

                    return None

                logger.info(
                    "Fallback version: %s",
                    version
                )

                logger.info(
                    "Fallback version code: %s",
                    version_code
                )

                return {
                    "version": normalize_version(
                        version
                    ),
                    "version_code": version_code,
                    "channel": "LIVE",
                    "images": ANIMAL_COMPANY_IMAGES
                }

    except Exception as e:

        logger.warning(
            "MetaMetadata fallback failed: %s",
            e
        )

        return None


# ============================================================
# GET CURRENT VERSION
# ============================================================

async def get_current_version():

    # --------------------------------------------------------
    # 1. PRIMARY LIVE OCULUS SOURCE
    # --------------------------------------------------------

    data = await get_oculus_latest_version()

    if data:

        # Get artwork separately.
        if not ANIMAL_COMPANY_IMAGES.get("icon"):

            artwork = await get_metadata_fallback()

            if artwork:

                data["images"] = artwork.get(
                    "images",
                    {}
                )

        return data

    # --------------------------------------------------------
    # 2. SECONDARY OCULUS SOURCE
    # --------------------------------------------------------

    logger.warning(
        "Primary Oculus version source failed."
    )

    data = await get_oculus_versions_query()

    if data:

        if not ANIMAL_COMPANY_IMAGES.get("icon"):

            artwork = await get_metadata_fallback()

            if artwork:

                data["images"] = artwork.get(
                    "images",
                    {}
                )

        return data

    # --------------------------------------------------------
    # 3. METAMETADATA FALLBACK
    # --------------------------------------------------------

    logger.warning(
        "All live Oculus version queries failed."
    )

    logger.warning(
        "Using MetaMetadata fallback."
    )

    return await get_metadata_fallback()


# ============================================================
# DISCORD CHANNEL
# ============================================================

async def get_update_channel():

    logger.info(
        "Looking for update channel: %s",
        UPDATE_CHANNEL_ID
    )

    channel = bot.get_channel(
        UPDATE_CHANNEL_ID
    )

    if channel:

        logger.info(
            "Update channel found through cache: #%s",
            getattr(
                channel,
                "name",
                "unknown"
            )
        )

        return channel

    logger.info(
        "Channel not cached. Fetching channel..."
    )

    try:

        channel = await bot.fetch_channel(
            UPDATE_CHANNEL_ID
        )

        logger.info(
            "Update channel fetched successfully."
        )

        return channel

    except Exception as e:

        logger.exception(
            "Could not fetch update channel: %s",
            e
        )

        return None


# ============================================================
# EMBED
# ============================================================

def build_update_embed(
    old_version,
    new_version,
    version_code,
    released=None,
    channel_name="LIVE",
    images=None
):

    if released is None:

        released = datetime.now(
            timezone.utc
        )

    if images is None:

        images = ANIMAL_COMPANY_IMAGES

    icon_url = images.get("icon")
    logo_url = images.get("logo")
    landscape_url = images.get("landscape")
    hero_url = images.get("hero")

    large_image_url = (
        landscape_url
        or hero_url
    )

    embed = discord.Embed(
        title="📦 New Animal Company Update!",
        color=discord.Color.orange(),
        timestamp=released
    )

    if logo_url or icon_url:

        embed.set_author(
            name="Animal Company",
            icon_url=(
                logo_url
                or icon_url
            )
        )

    else:

        embed.set_author(
            name="Animal Company"
        )

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

    released_unix = int(
        released.timestamp()
    )

    embed.add_field(
        name="🕐 Released",
        value=f"<t:{released_unix}:F>",
        inline=False
    )

    embed.add_field(
        name="📡 Channel",
        value=f"`{channel_name}`",
        inline=True
    )

    embed.add_field(
        name="🔗 Meta Store",
        value=(
            "[Open Animal Company page]"
            f"({META_STORE_URL})"
        ),
        inline=True
    )

    if icon_url:

        embed.set_thumbnail(
            url=icon_url
        )

    if large_image_url:

        embed.set_image(
            url=large_image_url
        )

    return embed


# ============================================================
# UPDATE CHECK
# ============================================================

async def check_for_updates():

    logger.info(
        "=============================================="
    )

    logger.info(
        "CHECKING FOR ANIMAL COMPANY UPDATE..."
    )

    logger.info(
        "=============================================="
    )

    current_data = await get_current_version()

    if not current_data:

        logger.error(
            "UPDATE CHECK FAILED: "
            "No version data received."
        )

        return

    new_version = current_data.get("version")
    version_code = current_data.get("version_code")

    channel_name = current_data.get(
        "channel",
        "LIVE"
    )

    images = current_data.get("images")

    if images:

        global ANIMAL_COMPANY_IMAGES

        ANIMAL_COMPANY_IMAGES.update(
            images
        )

    logger.info(
        "Detected version: %s",
        new_version
    )

    logger.info(
        "Detected version code: %s",
        version_code
    )

    old_version = load_saved_version()

    # --------------------------------------------------------
    # FIRST RUN
    # --------------------------------------------------------

    if not old_version:

        logger.info(
            "No previous version saved."
        )

        logger.info(
            "Saving current version without "
            "sending notification."
        )

        save_version(
            new_version,
            version_code
        )

        return

    # --------------------------------------------------------
    # NO UPDATE
    # --------------------------------------------------------

    if (
        normalize_version(old_version)
        ==
        normalize_version(new_version)
    ):

        logger.info(
            "No update detected."
        )

        logger.info(
            "Current version is still %s",
            new_version
        )

        return

    # --------------------------------------------------------
    # UPDATE FOUND
    # --------------------------------------------------------

    logger.info(
        "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    )

    logger.info(
        "NEW ANIMAL COMPANY UPDATE FOUND!"
    )

    logger.info(
        "%s -> %s",
        old_version,
        new_version
    )

    logger.info(
        "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    )

    channel = await get_update_channel()

    if not channel:

        logger.error(
            "Cannot send update notification because "
            "the Discord channel could not be found."
        )

        return

    released = datetime.now(
        timezone.utc
    )

    embed = build_update_embed(
        old_version=old_version,
        new_version=new_version,
        version_code=version_code,
        released=released,
        channel_name=channel_name,
        images=ANIMAL_COMPANY_IMAGES
    )

    role_mention = (
        f"<@&{UPDATE_ROLE_ID}>"
    )

    try:

        await channel.send(
            content=role_mention,
            embed=embed,
            allowed_mentions=discord.AllowedMentions(
                roles=True
            )
        )

        logger.info(
            "UPDATE NOTIFICATION SENT SUCCESSFULLY!"
        )

        save_version(
            new_version,
            version_code
        )

    except discord.Forbidden:

        logger.error(
            "Discord denied permission "
            "to send the message."
        )

    except discord.HTTPException as e:

        logger.error(
            "Discord HTTP error while "
            "sending update: %s",
            e
        )

    except Exception as e:

        logger.exception(
            "Unexpected error sending update: %s",
            e
        )


# ============================================================
# AUTOMATIC CHECKER
# ============================================================

@tasks.loop(
    minutes=CHECK_MINUTES
)
async def update_checker():

    logger.info(
        "Automatic update checker tick."
    )

    try:

        await check_for_updates()

    except Exception as e:

        logger.exception(
            "Automatic update checker error: %s",
            e
        )


@update_checker.before_loop
async def before_update_checker():

    logger.info(
        "Update checker waiting for Discord "
        "connection..."
    )

    await bot.wait_until_ready()

    logger.info(
        "Discord is ready. Update checker can begin."
    )


# ============================================================
# BOT EVENTS
# ============================================================

@bot.event
async def on_connect():

    logger.info(
        "=============================================="
    )

    logger.info(
        "DISCORD GATEWAY CONNECTED!"
    )

    logger.info(
        "=============================================="
    )

    if not update_checker.is_running():

        logger.info(
            "STARTING AUTOMATIC UPDATE CHECKER..."
        )

        update_checker.start()

        logger.info(
            "AUTOMATIC UPDATE CHECKER STARTED!"
        )

    else:

        logger.info(
            "Automatic update checker "
            "is already running."
        )


@bot.event
async def on_ready():

    logger.info(
        "=============================================="
    )

    logger.info(
        "DISCORD BOT IS READY!"
    )

    logger.info(
        "Logged in as %s",
        bot.user
    )

    logger.info(
        "Bot ID: %s",
        bot.user.id
        if bot.user
        else "unknown"
    )

    logger.info(
        "=============================================="
    )


@bot.event
async def on_disconnect():

    logger.warning(
        "Discord bot disconnected from Gateway."
    )


@bot.event
async def on_resumed():

    logger.info(
        "Discord session resumed."
    )


# ============================================================
# TEST COMMAND
# ============================================================

@bot.command(
    name="testupdate"
)
async def test_update(ctx):

    logger.info(
        "Test update command requested by %s",
        ctx.author
    )

    if not ANIMAL_COMPANY_IMAGES.get("icon"):

        await get_metadata_fallback()

    embed = build_update_embed(
        old_version="1.90.1.3492",
        new_version="1.90.2.3504",
        version_code="3504",
        released=datetime.now(
            timezone.utc
        ),
        channel_name="LIVE",
        images=ANIMAL_COMPANY_IMAGES
    )

    try:

        await ctx.send(
            content=f"<@&{UPDATE_ROLE_ID}>",
            embed=embed,
            allowed_mentions=discord.AllowedMentions(
                roles=True
            )
        )

        logger.info(
            "Test update message sent."
        )

    except Exception as e:

        logger.exception(
            "Could not send test update: %s",
            e
        )


# ============================================================
# ERROR HANDLER
# ============================================================

@bot.event
async def on_command_error(
    ctx,
    error
):

    if isinstance(
        error,
        commands.CommandNotFound
    ):

        return

    logger.error(
        "Command error: %s",
        error
    )


# ============================================================
# MAIN BOT
# ============================================================

async def run_bot():

    if not DISCORD_TOKEN:

        logger.error(
            "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
        )

        logger.error(
            "DISCORD_TOKEN IS MISSING!"
        )

        logger.error(
            "Add DISCORD_TOKEN to the Render "
            "environment variables."
        )

        logger.error(
            "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
        )

        return

    logger.info(
        "Starting Discord bot..."
    )

    try:

        await bot.start(
            DISCORD_TOKEN
        )

    except discord.LoginFailure:

        logger.error(
            "Discord login failed. "
            "Check the bot token."
        )

    except Exception as e:

        logger.exception(
            "Discord bot stopped unexpectedly: %s",
            e
        )


# ============================================================
# PROGRAM ENTRY
# ============================================================

def main():

    logger.info(
        "=============================================="
    )

    logger.info(
        "Starting Animal Company Update Bot..."
    )

    logger.info(
        "=============================================="
    )

    web_thread = threading.Thread(
        target=run_web_server,
        daemon=True
    )

    web_thread.start()

    logger.info(
        "Web server started."
    )

    logger.info(
        "Starting Discord bot..."
    )

    asyncio.run(
        run_bot()
    )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    main()
