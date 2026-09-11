import os
import json
import asyncio
import logging
from datetime import datetime, timezone

import aiohttp
import discord
from discord.ext import commands, tasks
from flask import Flask
from threading import Thread


# =========================================================
# CONFIG
# =========================================================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

UPDATE_CHANNEL_ID = int(
    os.getenv("UPDATE_CHANNEL_ID", "1547679561960132695")
)

UPDATE_ROLE_ID = int(
    os.getenv("UPDATE_ROLE_ID", "1547729517395714178")
)

ANIMAL_COMPANY_APP_ID = "7190422614401072"

# Meta/Oculus GraphQL
OCULUS_GRAPHQL_URL = "https://graph.oculus.com/graphql"
OCULUS_TOKEN = "OC|1076686279105243|"

# MetaMetadata fallback
METADATA_URL = (
    "https://raw.githubusercontent.com/threethan/"
    "MetaMetadata/main/data/common/woosterGames.animalCompany.json"
)

STATE_FILE = "update_data.json"


# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger("animal-company-bot")


# =========================================================
# FLASK WEB SERVER
# =========================================================

app = Flask(__name__)


@app.route("/")
def home():
    return "Animal Company Update Bot is running!"


def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(
        host="0.0.0.0",
        port=port,
        use_reloader=False
    )


# =========================================================
# DISCORD
# =========================================================

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# =========================================================
# STATE
# =========================================================

def load_state():
    if not os.path.exists(STATE_FILE):
        return None

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        return data

    except Exception as e:
        logger.error(f"Could not load state: {e}")
        return None


def save_state(version, version_code):
    data = {
        "version": version,
        "version_code": version_code
    }

    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        logger.info(
            f"Saved version state: {version} ({version_code})"
        )

    except Exception as e:
        logger.error(f"Could not save state: {e}")


# =========================================================
# META/Oculus VERSION DETECTION
# =========================================================

async def fetch_live_version():
    """
    Gets the current Animal Company LIVE version
    directly from Meta/Oculus GraphQL.
    """

    try:
        async with aiohttp.ClientSession() as session:

            # -------------------------------------------------
            # Request 1: Store information
            # -------------------------------------------------

            store_payload = {
                "doc_id": "8571881679548867",
                "access_token": OCULUS_TOKEN,
                "variables": json.dumps({
                    "applicationID": ANIMAL_COMPANY_APP_ID
                })
            }

            async with session.post(
                OCULUS_GRAPHQL_URL,
                data=store_payload
            ) as response:

                store_text = await response.text()

                logger.info(
                    f"Oculus store request: HTTP {response.status}"
                )

                if response.status != 200:
                    logger.warning(
                        f"Oculus store response: "
                        f"{store_text[:500]}"
                    )

                else:
                    try:
                        json.loads(store_text)
                    except Exception:
                        pass

            # -------------------------------------------------
            # Request 2: Release channels
            # -------------------------------------------------

            details_payload = {
                "doc_id": "3828663700542720",
                "access_token": OCULUS_TOKEN,
                "variables": json.dumps({
                    "applicationID": ANIMAL_COMPANY_APP_ID
                })
            }

            headers = {
                "TE": "Trailers"
            }

            async with session.post(
                OCULUS_GRAPHQL_URL,
                data=details_payload,
                headers=headers
            ) as response:

                details_text = await response.text()

                logger.info(
                    f"Oculus details request: HTTP {response.status}"
                )

                if response.status != 200:
                    logger.warning(
                        f"Oculus details response: "
                        f"{details_text[:700]}"
                    )
                    return None, None

                try:
                    details_data = json.loads(details_text)
                except Exception as e:
                    logger.error(
                        f"Could not decode Oculus response: {e}"
                    )
                    return None, None

        # -----------------------------------------------------
        # Parse response
        # -----------------------------------------------------

        node = (
            details_data
            .get("data", {})
            .get("node")
        )

        if not node:
            logger.warning(
                "Oculus response did not contain an app node."
            )
            return None, None

        release_channels = (
            node
            .get("release_channels", {})
            .get("nodes", [])
        )

        if not release_channels:
            logger.warning(
                "Oculus response did not contain release channels."
            )
            return None, None

        # -----------------------------------------------------
        # Find LIVE channel
        # -----------------------------------------------------

        live_channel = None

        for channel in release_channels:
            name = str(
                channel.get("name", "")
            ).upper()

            if name == "LIVE":
                live_channel = channel
                break

        # If LIVE isn't explicitly named, use first channel.
        if live_channel is None:
            live_channel = release_channels[0]

        binary = live_channel.get(
            "latest_supported_binary"
        )

        if not binary:
            logger.warning(
                "LIVE channel has no latest supported binary."
            )
            return None, None

        version = binary.get("version")
        version_code = binary.get("version_code")

        if not version:
            logger.warning(
                "Oculus returned no version."
            )
            return None, None

        version_code = (
            str(version_code)
            if version_code is not None
            else None
        )

        logger.info(
            f"Live Animal Company version: "
            f"{version} ({version_code})"
        )

        return version, version_code

    except Exception as e:
        logger.exception(
            f"Oculus version lookup failed: {e}"
        )

        return None, None


# =========================================================
# METADATA FALLBACK
# =========================================================

async def fetch_metadata_fallback():
    """
    Gets version/artwork from MetaMetadata if the
    direct Oculus request fails.
    """

    try:
        async with aiohttp.ClientSession() as session:

            async with session.get(
                METADATA_URL,
                timeout=aiohttp.ClientTimeout(total=20)
            ) as response:

                if response.status != 200:
                    logger.warning(
                        f"MetaMetadata HTTP {response.status}"
                    )
                    return None

                data = await response.json()

        version = data.get("version")
        version_code = data.get("versioncode")

        logger.info(
            f"Fallback version: {version}"
        )

        logger.info(
            f"Fallback version code: {version_code}"
        )

        return {
            "version": version,
            "version_code": (
                str(version_code)
                if version_code is not None
                else None
            ),
            "portrait": data.get("portrait"),
            "hero": data.get("hero"),
            "landscape": data.get("landscape"),
            "square": data.get("square"),
            "logo": data.get("logo"),
            "icon": data.get("icon")
        }

    except Exception as e:
        logger.exception(
            f"MetaMetadata fallback failed: {e}"
        )

        return None


# =========================================================
# ARTWORK
# =========================================================

async def get_artwork():
    data = await fetch_metadata_fallback()

    if not data:
        return {
            "portrait": None,
            "hero": None,
            "landscape": None,
            "square": None,
            "logo": None,
            "icon": None
        }

    logger.info("Animal Company artwork URLs loaded.")

    return data


# =========================================================
# UPDATE EMBED
# =========================================================

async def send_update(
    old_version,
    new_version,
    version_code
):

    channel = bot.get_channel(UPDATE_CHANNEL_ID)

    if channel is None:
        logger.error(
            f"Could not find update channel "
            f"{UPDATE_CHANNEL_ID}"
        )
        return

    role = channel.guild.get_role(
        UPDATE_ROLE_ID
    )

    if role is None:
        logger.error(
            f"Could not find update role "
            f"{UPDATE_ROLE_ID}"
        )
        return

    artwork = await get_artwork()

    embed = discord.Embed(
        title="📦 New Animal Company Update!",
        color=discord.Color.blue(),
        timestamp=datetime.now(timezone.utc)
    )

    # -----------------------------------------------------
    # Author
    # -----------------------------------------------------

    logo = artwork.get("logo")

    if logo:
        embed.set_author(
            name="Animal Company",
            icon_url=logo
        )
    else:
        embed.set_author(
            name="Animal Company"
        )

    # -----------------------------------------------------
    # Version fields
    # -----------------------------------------------------

    embed.add_field(
        name="⬅️ Previous Version",
        value=old_version,
        inline=True
    )

    embed.add_field(
        name="📦 New Version",
        value=new_version,
        inline=True
    )

    embed.add_field(
        name="🔢 Version Code",
        value=str(version_code),
        inline=True
    )

    # -----------------------------------------------------
    # Released
    # -----------------------------------------------------

    released_time = datetime.now(timezone.utc)

    embed.add_field(
        name="🕐 Released",
        value=discord.utils.format_dt(
            released_time,
            style="F"
        ),
        inline=False
    )

    # -----------------------------------------------------
    # Channel
    # -----------------------------------------------------

    embed.add_field(
        name="📡 Channel",
        value="LIVE",
        inline=True
    )

    # -----------------------------------------------------
    # Meta Store
    # -----------------------------------------------------

    embed.add_field(
        name="🔗 Meta Store",
        value=(
            "[Open Animal Company page]"
            "(https://www.meta.com/experiences/"
            "animal-company/7190422614401072/)"
        ),
        inline=True
    )

    # -----------------------------------------------------
    # Top-right thumbnail
    # -----------------------------------------------------

    icon = artwork.get("icon")

    if icon:
        embed.set_thumbnail(
            url=icon
        )

    # -----------------------------------------------------
    # Large artwork
    # -----------------------------------------------------

    hero = artwork.get("hero")

    if not hero:
        hero = artwork.get("landscape")

    if not hero:
        hero = artwork.get("portrait")

    if hero:
        embed.set_image(
            url=hero
        )

    # -----------------------------------------------------
    # Send
    # -----------------------------------------------------

    await channel.send(
        content=role.mention,
        embed=embed,
        allowed_mentions=discord.AllowedMentions(
            roles=True
        )
    )

    logger.info(
        f"Sent update notification: "
        f"{old_version} -> {new_version} "
        f"({version_code})"
    )


# =========================================================
# UPDATE CHECKER
# =========================================================

async def check_for_update():
    logger.info("Checking Animal Company version...")

    # -----------------------------------------------------
    # Try direct Meta/Oculus first
    # -----------------------------------------------------

    live_version, live_code = await fetch_live_version()

    # -----------------------------------------------------
    # Fallback if direct lookup fails
    # -----------------------------------------------------

    if not live_version:
        logger.warning(
            "Direct Oculus lookup failed. "
            "Using MetaMetadata fallback."
        )

        fallback = await fetch_metadata_fallback()

        if not fallback:
            logger.error(
                "Could not determine Animal Company version."
            )
            return

        live_version = fallback["version"]
        live_code = fallback["version_code"]

    # -----------------------------------------------------
    # Validate
    # -----------------------------------------------------

    if not live_version:
        logger.warning(
            "Version was empty. Skipping."
        )
        return

    # -----------------------------------------------------
    # Load previous version
    # -----------------------------------------------------

    previous = load_state()

    if previous is None:
        logger.info(
            f"No previous saved version. "
            f"Saving {live_version} ({live_code}) "
            f"without sending notification."
        )

        save_state(
            live_version,
            live_code
        )

        return

    old_version = previous.get("version")
    old_code = previous.get("version_code")

    logger.info(
        f"Previous saved version: "
        f"{old_version} ({old_code})"
    )

    logger.info(
        f"Current detected version: "
        f"{live_version} ({live_code})"
    )

    # -----------------------------------------------------
    # Detect change
    # -----------------------------------------------------

    version_changed = (
        old_version != live_version
        or str(old_code) != str(live_code)
    )

    if not version_changed:
        logger.info(
            "No new update detected."
        )
        return

    # -----------------------------------------------------
    # New update!
    # -----------------------------------------------------

    logger.info(
        f"NEW UPDATE DETECTED: "
        f"{old_version} -> {live_version}"
    )

    await send_update(
        old_version=old_version,
        new_version=live_version,
        version_code=live_code
    )

    save_state(
        live_version,
        live_code
    )


# =========================================================
# AUTOMATIC CHECK
# =========================================================

@tasks.loop(minutes=5)
async def update_checker():
    try:
        await check_for_update()

    except Exception as e:
        logger.exception(
            f"Update checker error: {e}"
        )


# =========================================================
# TEST COMMAND
# =========================================================

@bot.command()
@commands.has_permissions(administrator=True)
async def testupdate(ctx):

    old_version = "1.90.1.3492"
    new_version = "1.90.2.3504"
    version_code = "3504"

    await send_update(
        old_version=old_version,
        new_version=new_version,
        version_code=version_code
    )

    await ctx.send(
        "✅ Test update sent."
    )


# =========================================================
# BOT READY
# =========================================================

@bot.event
async def on_ready():

    logger.info(
        f"Logged in as {bot.user}"
    )

    logger.info(
        f"Bot ID: {bot.user.id}"
    )

    if not update_checker.is_running():

        logger.info(
            "Starting automatic update checker..."
        )

        update_checker.start()


# =========================================================
# ERROR HANDLING
# =========================================================

@bot.event
async def on_command_error(ctx, error):

    if isinstance(
        error,
        commands.MissingPermissions
    ):
        await ctx.send(
            "❌ You need administrator permissions "
            "to use this command."
        )
        return

    if isinstance(
        error,
        commands.CommandNotFound
    ):
        return

    logger.error(
        f"Command error: {error}"
    )


# =========================================================
# START
# =========================================================

if __name__ == "__main__":

    if not DISCORD_TOKEN:
        raise RuntimeError(
            "DISCORD_TOKEN environment variable is missing."
        )

    # Start Render web server
    web_thread = Thread(
        target=run_web,
        daemon=True
    )

    web_thread.start()

    # Start Discord bot
    bot.run(DISCORD_TOKEN)
