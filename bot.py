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
# META / OCULUS
# ============================================================

OCULUS_GRAPHQL_URL = (
    "https://graph.oculus.com/graphql"
)

OCULUS_TOKEN = (
    "OC|1076686279105243|"
)

STORE_DOC_ID = (
    "8571881679548867"
)

DETAILS_DOC_ID = (
    "3828663700542720"
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


startup_check_done = False


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

        version = data.get(
            "version"
        )

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


# ============================================================
# GRAPHQL REQUEST
# ============================================================

async def graphql_request(
    session,
    url,
    payload,
    headers=None,
    timeout_seconds=20
):

    try:

        timeout = aiohttp.ClientTimeout(
            total=timeout_seconds
        )

        async with session.post(
            url,
            json=payload,
            headers=headers or {},
            timeout=timeout
        ) as response:

            text = await response.text()

            logger.info(
                "GraphQL response HTTP status: %s",
                response.status
            )

            if response.status != 200:

                logger.error(
                    "GraphQL HTTP %s response: %s",
                    response.status,
                    text[:2000]
                )

                return None

            try:

                return json.loads(text)

            except json.JSONDecodeError:

                logger.error(
                    "GraphQL returned invalid JSON: %s",
                    text[:2000]
                )

                return None

    except asyncio.TimeoutError:

        logger.error(
            "GraphQL request timed out."
        )

        return None

    except aiohttp.ClientError as e:

        logger.error(
            "GraphQL network error: %s",
            e
        )

        return None

    except Exception as e:

        logger.exception(
            "Unexpected GraphQL error: %s",
            e
        )

        return None


# ============================================================
# META GRAPHQL VERSION
# ============================================================

async def get_meta_version():

    logger.info(
        "Fetching current Animal Company version..."
    )

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/151.0 Safari/537.36"
        )
    }

    async with aiohttp.ClientSession() as session:

        # ----------------------------------------------------
        # STORE REQUEST
        # ----------------------------------------------------

        store_payload = {
            "doc_id": STORE_DOC_ID,
            "access_token": OCULUS_TOKEN,
            "variables": json.dumps(
                {
                    "applicationID": APP_ID
                }
            )
        }

        logger.info(
            "Requesting Meta store information..."
        )

        store_data = await graphql_request(
            session,
            OCULUS_GRAPHQL_URL,
            store_payload,
            headers=headers
        )

        if store_data is None:

            logger.warning(
                "Meta store request failed."
            )

        else:

            logger.info(
                "Meta store request succeeded."
            )

        # ----------------------------------------------------
        # DETAILS REQUEST
        # ----------------------------------------------------

        details_payload = {
            "doc_id": DETAILS_DOC_ID,
            "access_token": OCULUS_TOKEN,
            "variables": json.dumps(
                {
                    "applicationID": APP_ID
                }
            )
        }

        logger.info(
            "Requesting Meta application details..."
        )

        details_data = await graphql_request(
            session,
            OCULUS_GRAPHQL_URL,
            details_payload,
            headers=headers
        )

        if details_data is None:

            logger.error(
                "Could not get Meta application details."
            )

            return None

        logger.info(
            "Meta application details request succeeded."
        )

    # --------------------------------------------------------
    # EXTRACT VERSION
    # --------------------------------------------------------

    try:

        node = (
            details_data
            .get("data", {})
            .get("node", {})
        )

        release_channels = (
            node.get(
                "release_channels",
                {}
            )
        )

        nodes = (
            release_channels.get(
                "nodes",
                []
            )
        )

        if not nodes:

            logger.error(
                "Meta response contained no release channels."
            )

            logger.error(
                "Response structure: %s",
                json.dumps(
                    details_data,
                    indent=2
                )[:5000]
            )

            return None

        latest_binary = (
            nodes[0]
            .get(
                "latest_supported_binary",
                {}
            )
        )

        version = latest_binary.get(
            "version"
        )

        version_code = latest_binary.get(
            "version_code"
        )

        if not version:

            logger.error(
                "Meta response did not contain a version."
            )

            logger.error(
                "Latest binary: %s",
                latest_binary
            )

            return None

        logger.info(
            "CURRENT ANIMAL COMPANY VERSION: %s",
            version
        )

        logger.info(
            "CURRENT VERSION CODE: %s",
            version_code
        )

        return {
            "version": normalize_version(
                version
            ),
            "version_code": version_code,
            "channel": "LIVE"
        }

    except Exception as e:

        logger.exception(
            "Error extracting Meta version: %s",
            e
        )

        return None


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

                # ------------------------------------------------
                # SAVE IMAGE URLS
                # ------------------------------------------------

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

                # ------------------------------------------------
                # VERSION
                # ------------------------------------------------

                version = data.get(
                    "version"
                )

                version_code = data.get(
                    "versioncode"
                )

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

    data = await get_meta_version()

    if data:

        # Make sure we also have artwork.
        if not ANIMAL_COMPANY_IMAGES.get(
            "icon"
        ):

            fallback = (
                await get_metadata_fallback()
            )

            if fallback:

                data["images"] = (
                    fallback.get(
                        "images",
                        {}
                    )
                )

        return data

    logger.warning(
        "Meta GraphQL failed."
    )

    logger.warning(
        "Trying fallback source..."
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

    # --------------------------------------------------------
    # IMAGE URLS
    # --------------------------------------------------------

    icon_url = images.get(
        "icon"
    )

    logo_url = images.get(
        "logo"
    )

    landscape_url = images.get(
        "landscape"
    )

    hero_url = images.get(
        "hero"
    )

    # Use landscape first.
    # If unavailable, use hero.
    large_image_url = (
        landscape_url
        or hero_url
    )

    # --------------------------------------------------------
    # EMBED
    # --------------------------------------------------------

    embed = discord.Embed(
        title="📦 New Animal Company Update!",
        color=discord.Color.orange(),
        timestamp=released
    )

    # --------------------------------------------------------
    # AUTHOR
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # VERSION FIELDS
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
    # RELEASED
    # --------------------------------------------------------

    released_unix = int(
        released.timestamp()
    )

    embed.add_field(
        name="🕐 Released",
        value=(
            f"<t:{released_unix}:F>"
        ),
        inline=False
    )

    # --------------------------------------------------------
    # CHANNEL
    # --------------------------------------------------------

    embed.add_field(
        name="📡 Channel",
        value=f"`{channel_name}`",
        inline=True
    )

    # --------------------------------------------------------
    # META STORE
    # --------------------------------------------------------

    embed.add_field(
        name="🔗 Meta Store",
        value=(
            "[Open Animal Company page]"
            f"({META_STORE_URL})"
        ),
        inline=True
    )

    # --------------------------------------------------------
    # THUMBNAIL
    # --------------------------------------------------------

    if icon_url:

        embed.set_thumbnail(
            url=icon_url
        )

    # --------------------------------------------------------
    # LARGE ARTWORK
    # --------------------------------------------------------

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

    current_data = (
        await get_current_version()
    )

    if not current_data:

        logger.error(
            "UPDATE CHECK FAILED: "
            "No version data received."
        )

        return

    new_version = current_data.get(
        "version"
    )

    version_code = current_data.get(
        "version_code"
    )

    channel_name = current_data.get(
        "channel",
        "LIVE"
    )

    images = current_data.get(
        "images"
    )

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

    old_version = (
        load_saved_version()
    )

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
        normalize_version(
            old_version
        )
        ==
        normalize_version(
            new_version
        )
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

    channel = (
        await get_update_channel()
    )

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

    global startup_check_done

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

    if not startup_check_done:

        startup_check_done = True

        logger.info(
            "Waiting 5 seconds before "
            "initial update check..."
        )

        await asyncio.sleep(5)

        logger.info(
            "RUNNING INITIAL UPDATE CHECK..."
        )

        try:

            await check_for_updates()

        except Exception as e:

            logger.exception(
                "INITIAL UPDATE CHECK FAILED: %s",
                e
            )

        logger.info(
            "INITIAL UPDATE CHECK FINISHED."
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

    # Get artwork if it hasn't been loaded yet.
    if not ANIMAL_COMPANY_IMAGES.get(
        "icon"
    ):

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
            content=(
                f"<@&{UPDATE_ROLE_ID}>"
            ),
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

    # --------------------------------------------------------
    # START FLASK
    # --------------------------------------------------------

    web_thread = threading.Thread(
        target=run_web_server,
        daemon=True
    )

    web_thread.start()

    logger.info(
        "Web server started."
    )

    # --------------------------------------------------------
    # START DISCORD
    # --------------------------------------------------------

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
