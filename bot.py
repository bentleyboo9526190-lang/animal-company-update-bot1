import os
import json
import logging
from datetime import datetime, timezone

import aiohttp
import discord
from discord.ext import commands, tasks
from flask import Flask
from threading import Thread
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# CONFIG
# ============================================================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

UPDATE_CHANNEL_ID = int(os.getenv("UPDATE_CHANNEL_ID", "1547679561960132695"))
UPDATE_ROLE_ID = int(os.getenv("UPDATE_ROLE_ID", "1547729517395714178"))

ANIMAL_COMPANY_APP_ID = "7190422614401072"

META_STORE_URL = (
    "https://www.meta.com/experiences/animal-company/"
    "7190422614401072/"
)

OCULUS_GRAPHQL_URL = "https://graph.oculus.com/graphql"

# Public Oculus Store token used by the store API.
OCULUS_TOKEN = "OC|1076686279105243|"

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
# FLASK SERVER
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
        "version_code": version_code,
        "saved_at": datetime.now(timezone.utc).isoformat()
    }

    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ============================================================
# META / OCULUS VERSION LOOKUP
# ============================================================

async def oculus_request(session, doc_id, variables):
    params = {
        "access_token": OCULUS_TOKEN,
        "variables": json.dumps(variables, separators=(",", ":")),
        "doc_id": doc_id,
    }

    headers = {
        "TE": "Trailers",
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
    }

    try:
        async with session.post(
            OCULUS_GRAPHQL_URL,
            params=params,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=20),
        ) as response:

            text = await response.text()

            log.info(
                f"Oculus request {doc_id}: HTTP {response.status}"
            )

            if response.status != 200:
                log.warning(
                    f"Oculus HTTP error {response.status}: {text[:500]}"
                )
                return None

            try:
                return json.loads(text)
            except json.JSONDecodeError:
                log.warning(
                    f"Oculus returned non-JSON: {text[:500]}"
                )
                return None

    except Exception as e:
        log.warning(f"Oculus request failed: {e}")
        return None


def find_versions(obj):
    """
    Recursively search the Oculus response for objects that contain
    version/version_code style fields.
    """

    found = []

    if isinstance(obj, dict):
        keys = {str(k).lower(): k for k in obj.keys()}

        version_key = None
        code_key = None

        for lowered, original in keys.items():
            if lowered in (
                "version",
                "version_name",
                "versionname",
            ):
                version_key = original

            if lowered in (
                "version_code",
                "versioncode",
                "versioncodeint",
            ):
                code_key = original

        if version_key is not None:
            version = obj.get(version_key)
            version_code = obj.get(code_key) if code_key else None

            if version:
                found.append(
                    (
                        str(version),
                        str(version_code) if version_code is not None else None,
                    )
                )

        for value in obj.values():
            found.extend(find_versions(value))

    elif isinstance(obj, list):
        for item in obj:
            found.extend(find_versions(item))

    return found


async def get_oculus_version():
    async with aiohttp.ClientSession() as session:

        # ----------------------------------------------------
        # METHOD 1
        # "Versions of App"
        # ----------------------------------------------------

        data = await oculus_request(
            session,
            "1586217024733717",
            {
                "id": ANIMAL_COMPANY_APP_ID
            }
        )

        if data:
            versions = find_versions(data)

            if versions:
                log.info(
                    f"Found {len(versions)} version candidate(s) "
                    f"from Oculus Versions API."
                )

                for version, code in versions:
                    log.info(
                        f"Oculus candidate: {version} "
                        f"(code {code})"
                    )

                # Prefer the first candidate that has a version code.
                for version, code in versions:
                    if code:
                        return version, code

                return versions[0]

        # ----------------------------------------------------
        # METHOD 2
        # "Latest version of an App"
        # ----------------------------------------------------

        data = await oculus_request(
            session,
            "5373392672732392",
            {
                "itemId": ANIMAL_COMPANY_APP_ID,
                "first": 5,
                "last": None,
                "after": None,
                "before": None,
                "forward": True,
                "ordering": None,
                "ratingScores": None,
                "hmdType": "MONTEREY",
            }
        )

        if data:
            versions = find_versions(data)

            if versions:
                log.info(
                    f"Found {len(versions)} version candidate(s) "
                    f"from Oculus Latest Version API."
                )

                for version, code in versions:
                    log.info(
                        f"Oculus latest candidate: {version} "
                        f"(code {code})"
                    )

                for version, code in versions:
                    if code:
                        return version, code

                return versions[0]

        # ----------------------------------------------------
        # METHOD 3
        # Release channels
        # ----------------------------------------------------

        data = await oculus_request(
            session,
            "3828663700542720",
            {
                "applicationID": ANIMAL_COMPANY_APP_ID
            }
        )

        if data:
            versions = find_versions(data)

            if versions:
                log.info(
                    f"Found {len(versions)} version candidate(s) "
                    f"from release channels."
                )

                for version, code in versions:
                    log.info(
                        f"Release channel candidate: "
                        f"{version} (code {code})"
                    )

                for version, code in versions:
                    if code:
                        return version, code

                return versions[0]

    return None, None


# ============================================================
# METAMETADATA FALLBACK
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
                    f"MetaMetadata request: HTTP {response.status}"
                )

                if response.status != 200:
                    return None

                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    log.warning(
                        "MetaMetadata returned invalid JSON."
                    )
                    return None

    except Exception as e:
        log.warning(f"MetaMetadata failed: {e}")
        return None


# ============================================================
# GET CURRENT APP INFO
# ============================================================

async def get_current_app_info():
    # Try live Oculus API first.
    version, version_code = await get_oculus_version()

    if version:
        log.info(
            f"LIVE Oculus version: {version} "
            f"(code {version_code})"
        )

        metadata = await get_metametadata()

        return {
            "version": version,
            "version_code": version_code or "",
            "metadata": metadata or {},
        }

    # Fallback only if Oculus API fails.
    metadata = await get_metametadata()

    if metadata:
        version = metadata.get("version")
        version_code = metadata.get("versioncode")

        log.info(
            f"Fallback version: {version}"
        )
        log.info(
            f"Fallback version code: {version_code}"
        )

        return {
            "version": version,
            "version_code": str(version_code or ""),
            "metadata": metadata,
        }

    return None


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
        timestamp=datetime.now(timezone.utc),
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

    # Author
    embed.set_author(
        name="Animal Company",
        icon_url=logo if logo else discord.Embed.Empty
    )

    # Version row
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

    # Released
    embed.add_field(
        name="🕐 Released",
        value=f"<t:{int(datetime.now(timezone.utc).timestamp())}:F>",
        inline=False
    )

    # Channel + Meta Store
    embed.add_field(
        name="📡 Channel",
        value="`LIVE`",
        inline=True
    )

    embed.add_field(
        name="🔗 Meta Store",
        value=f"[Open Animal Company page]({META_STORE_URL})",
        inline=True
    )

    # Small image
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)

    # Large image
    if artwork:
        embed.set_image(url=artwork)

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
    channel = bot.get_channel(UPDATE_CHANNEL_ID)

    if channel is None:
        try:
            channel = await bot.fetch_channel(UPDATE_CHANNEL_ID)
        except Exception as e:
            log.error(f"Could not find update channel: {e}")
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

    log.info("Checking Animal Company version...")

    info = await get_current_app_info()

    if not info:
        log.warning("Could not determine current version.")
        return

    new_version = info["version"]
    new_version_code = str(info["version_code"])
    metadata = info["metadata"]

    if not new_version:
        log.warning("Version was empty.")
        return

    saved = load_state()

    if not saved:
        log.info(
            f"No previous saved version. "
            f"Saving {new_version} ({new_version_code}) "
            f"without notification."
        )

        save_state(
            new_version,
            new_version_code
        )

        return

    old_version = str(saved.get("version", ""))
    old_version_code = str(
        saved.get("version_code", "")
    )

    # Nothing changed.
    if (
        old_version == new_version
        and old_version_code == new_version_code
    ):
        log.info(
            f"No update. Current version: "
            f"{new_version} ({new_version_code})"
        )
        return

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

    metadata = await get_metametadata() or {}

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
# DEBUG COMMAND
# ============================================================

@bot.command()
@commands.has_permissions(administrator=True)
async def checkversion(ctx):

    await ctx.send(
        "🔎 Checking the live Animal Company version..."
    )

    info = await get_current_app_info()

    if not info:
        await ctx.send(
            "❌ Could not get the current version."
        )
        return

    await ctx.send(
        f"📦 Version: `{info['version']}`\n"
        f"🔢 Version Code: `{info['version_code']}`"
    )


# ============================================================
# BOT EVENTS
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
