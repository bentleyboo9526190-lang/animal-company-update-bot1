import os
import json
import asyncio
import threading

import aiohttp
import discord
from discord.ext import commands, tasks
from flask import Flask
from dotenv import load_dotenv


# ============================================================
# CONFIG
# ============================================================

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

UPDATE_CHANNEL_ID = 1547679561960132695
UPDATE_ROLE_ID = 1547729517395714178

CHECK_MINUTES = 2

ANIMAL_COMPANY_ID = "7190422614401072"

# Oculus GraphQL endpoint used by MetaMetadata
OCULUS_GRAPHQL_URL = "https://graph.oculus.com/graphql"

# Animal Company Meta Store page
META_STORE_URL = (
    "https://www.meta.com/experiences/animal-company/"
    "7190422614401072/"
)

# Animal Company website icon
ANIMAL_COMPANY_ICON = (
    "https://www.animalcompanyvr.com/favicon.ico"
)

DATA_FILE = "update_data.json"


# ============================================================
# FLASK SERVER
# ============================================================

app = Flask(__name__)


@app.route("/")
def home():
    return "Animal Company Update Bot is online!"


def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


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
# SAVED VERSION DATA
# ============================================================

def load_saved_data():
    if not os.path.exists(DATA_FILE):
        return None

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    except Exception as e:
        print(f"Could not read {DATA_FILE}: {e}")
        return None


def save_version(version, version_code):
    data = {
        "version": version,
        "version_code": version_code
    }

    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        print(
            f"Saved version: {version} "
            f"(code {version_code})"
        )

    except Exception as e:
        print(f"Could not save version: {e}")


# ============================================================
# GRAPHQL
# ============================================================

async def graphql_request(payload):
    print("Sending request to Meta Oculus GraphQL...")

    timeout = aiohttp.ClientTimeout(total=30)

    try:
        async with aiohttp.ClientSession(
            timeout=timeout
        ) as session:

            async with session.post(
                OCULUS_GRAPHQL_URL,
                data=payload
            ) as response:

                text = await response.text()

                print(
                    f"Meta GraphQL HTTP status: "
                    f"{response.status}"
                )

                if response.status != 200:
                    print(
                        "Meta GraphQL error response:"
                    )
                    print(text[:3000])

                    return None

                try:
                    return json.loads(text)

                except json.JSONDecodeError:
                    print(
                        "Meta returned something that "
                        "was not valid JSON."
                    )
                    print(text[:3000])
                    return None

    except Exception as e:
        print(
            f"Meta GraphQL connection error: {e}"
        )
        return None


# ============================================================
# GET ANIMAL COMPANY VERSION
# ============================================================

async def fetch_meta_version():
    print(
        "Fetching current Animal Company version..."
    )

    # --------------------------------------------------------
    # Request 1:
    # Get the store information.
    # This follows the current MetaMetadata approach.
    # --------------------------------------------------------

    store_payload = {
        "doc_id": "8571881679548867",
        "access_token": "OC|1076686279105243|",
        "variables": json.dumps({
            "applicationID": ANIMAL_COMPANY_ID
        })
    }

    store_data = await graphql_request(
        store_payload
    )

    if store_data is None:
        print(
            "Store GraphQL request failed."
        )

    else:
        print(
            "Store GraphQL request succeeded."
        )

    # --------------------------------------------------------
    # Request 2:
    # Get the latest supported binary.
    # --------------------------------------------------------

    app_details_payload = {
        "doc_id": "3828663700542720",
        "access_token": "OC|1076686279105243|",
        "variables": json.dumps({
            "applicationID": ANIMAL_COMPANY_ID
        })
    }

    data = await graphql_request(
        app_details_payload
    )

    if data is None:
        print(
            "Could not get Animal Company "
            "version data from Meta."
        )
        return None

    try:
        node = (
            data
            .get("data", {})
            .get("node")
        )

        if not node:
            print(
                "Meta response did not contain "
                "the application node."
            )
            print(
                json.dumps(
                    data,
                    indent=2
                )[:5000]
            )
            return None

        release_channels = (
            node
            .get("release_channels", {})
            .get("nodes", [])
        )

        if not release_channels:
            print(
                "Meta response did not contain "
                "release channels."
            )
            return None

        latest_binary = (
            release_channels[0]
            .get("latest_supported_binary")
        )

        if not latest_binary:
            print(
                "Meta response did not contain "
                "latest_supported_binary."
            )
            return None

        version = latest_binary.get("version")
        version_code = latest_binary.get(
            "version_code"
        )

        if not version:
            print(
                "Meta returned no version."
            )
            return None

        if version_code is None:
            print(
                "Meta returned no version code."
            )
            return None

        print(
            f"Animal Company version found: "
            f"{version} "
            f"(code {version_code})"
        )

        return {
            "version": str(version),
            "version_code": int(version_code)
        }

    except Exception as e:
        print(
            f"Could not parse Meta response: {e}"
        )

        print(
            json.dumps(
                data,
                indent=2
            )[:5000]
        )

        return None


# ============================================================
# GET UPDATE ARTWORK
# ============================================================

async def get_update_artwork():
    url = (
        "https://raw.githubusercontent.com/"
        "threethan/MetaMetadata/main/data/common/"
        "woosterGames.animalCompany.json"
    )

    try:
        timeout = aiohttp.ClientTimeout(total=20)

        async with aiohttp.ClientSession(
            timeout=timeout
        ) as session:

            async with session.get(url) as response:

                if response.status != 200:
                    print(
                        "Could not download "
                        "Animal Company artwork data."
                    )
                    return None

                data = await response.json()

        # Try several possible artwork fields.
        possible_fields = [
            "hero",
            "landscape",
            "banner",
            "artwork",
            "cover",
            "thumbnail",
            "icon",
            "square",
            "portrait"
        ]

        for field in possible_fields:
            value = data.get(field)

            if isinstance(value, str) and value.startswith(
                "http"
            ):
                return value

        return None

    except Exception as e:
        print(
            f"Could not get update artwork: {e}"
        )
        return None


# ============================================================
# SEND UPDATE EMBED
# ============================================================

async def send_update(
    previous_version,
    new_version,
    version_code
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
            print(
                f"Could not find update channel: {e}"
            )
            return False

    artwork = await get_update_artwork()

    embed = discord.Embed(
        title="📦 New Animal Company Update!",
        color=discord.Color.blue()
    )

    # --------------------------------------------------------
    # Author
    # --------------------------------------------------------

    embed.set_author(
        name="Animal Company",
        icon_url=ANIMAL_COMPANY_ICON
    )

    # --------------------------------------------------------
    # Version row
    # --------------------------------------------------------

    embed.add_field(
        name="⬅️ Previous Version",
        value=f"`{previous_version}`",
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
        value="<t:%d:R>" % int(
            discord.utils.utcnow().timestamp()
        ),
        inline=False
    )

    # --------------------------------------------------------
    # Channel + Meta Store
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
    # Small thumbnail
    # --------------------------------------------------------

    embed.set_thumbnail(
        url=ANIMAL_COMPANY_ICON
    )

    # --------------------------------------------------------
    # Large artwork
    # --------------------------------------------------------

    if artwork:
        embed.set_image(
            url=artwork
        )

    # --------------------------------------------------------
    # Role mention
    # --------------------------------------------------------

    role_mention = f"<@&{UPDATE_ROLE_ID}>"

    try:
        await channel.send(
            content=role_mention,
            embed=embed,
            allowed_mentions=discord.AllowedMentions(
                roles=True
            )
        )

        print(
            "Update notification sent successfully."
        )

        return True

    except Exception as e:
        print(
            f"Could not send update notification: {e}"
        )

        return False


# ============================================================
# UPDATE CHECKER
# ============================================================

async def check_for_updates():

    print(
        "Checking for Animal Company updates..."
    )

    current = await fetch_meta_version()

    if current is None:
        print(
            "Update check failed: "
            "Could not get Meta version data."
        )
        return

    current_version = current["version"]
    current_code = current["version_code"]

    saved = load_saved_data()

    # --------------------------------------------------------
    # First startup
    # --------------------------------------------------------

    if saved is None:

        print(
            "No previous version saved."
        )

        print(
            f"Saving current version "
            f"{current_version} "
            f"(code {current_code}) "
            f"without sending a notification."
        )

        save_version(
            current_version,
            current_code
        )

        return

    previous_version = saved.get(
        "version"
    )

    previous_code = saved.get(
        "version_code"
    )

    print(
        f"Saved version: "
        f"{previous_version} "
        f"(code {previous_code})"
    )

    print(
        f"Current version: "
        f"{current_version} "
        f"(code {current_code})"
    )

    # --------------------------------------------------------
    # Nothing changed
    # --------------------------------------------------------

    if (
        str(previous_version)
        == str(current_version)
        and int(previous_code)
        == int(current_code)
    ):
        print(
            "No new Animal Company update."
        )
        return

    # --------------------------------------------------------
    # New update
    # --------------------------------------------------------

    print(
        "NEW ANIMAL COMPANY UPDATE DETECTED!"
    )

    print(
        f"{previous_version} -> "
        f"{current_version}"
    )

    print(
        f"Version code: "
        f"{current_code}"
    )

    sent = await send_update(
        previous_version,
        current_version,
        current_code
    )

    # Only save after Discord successfully
    # receives the notification.
    if sent:

        save_version(
            current_version,
            current_code
        )

        print(
            "New version saved."
        )

    else:

        print(
            "Notification failed, so the "
            "old version was NOT replaced."
        )


# ============================================================
# AUTOMATIC LOOP
# ============================================================

@tasks.loop(minutes=CHECK_MINUTES)
async def update_checker():

    try:
        await check_for_updates()

    except Exception as e:

        print(
            f"Unexpected update checker error: {e}"
        )


@update_checker.before_loop
async def before_update_checker():

    await bot.wait_until_ready()

    print(
        "Update checker is ready."
    )


# ============================================================
# BOT READY
# ============================================================

@bot.event
async def on_ready():

    print(
        "================================================"
    )

    print(
        f"Logged in as {bot.user}"
    )

    print(
        f"Bot ID: {bot.user.id}"
    )

    print(
        f"Update channel ID: "
        f"{UPDATE_CHANNEL_ID}"
    )

    print(
        f"Update role ID: "
        f"{UPDATE_ROLE_ID}"
    )

    print(
        f"Checking every {CHECK_MINUTES} minutes."
    )

    print(
        "================================================"
    )

    if not update_checker.is_running():

        update_checker.start()

        print(
            "Automatic update checker started."
        )


# ============================================================
# TEST COMMAND
# ============================================================

@bot.command()
@commands.has_permissions(administrator=True)
async def testupdate(ctx):

    print(
        "Manual test update requested."
    )

    previous_version = "1.90.1.3492"
    new_version = "1.90.2.3504"
    version_code = 3504

    sent = await send_update(
        previous_version,
        new_version,
        version_code
    )

    if sent:

        await ctx.send(
            "✅ Test update notification sent."
        )

    else:

        await ctx.send(
            "❌ Failed to send test notification."
        )


# ============================================================
# COMMAND ERROR HANDLER
# ============================================================

@bot.event
async def on_command_error(
    ctx,
    error
):

    if isinstance(
        error,
        commands.MissingPermissions
    ):

        await ctx.send(
            "❌ You need administrator permission "
            "to use this command."
        )

        return

    if isinstance(
        error,
        commands.CommandNotFound
    ):
        return

    print(
        f"Command error: {error}"
    )


# ============================================================
# START BOT
# ============================================================

def main():

    if not TOKEN:

        print(
            "ERROR: DISCORD_TOKEN is not set."
        )

        return

    print(
        "Starting Animal Company Update Bot..."
    )

    # Start Flask so Render sees an open web port.
    web_thread = threading.Thread(
        target=run_web_server,
        daemon=True
    )

    web_thread.start()

    print(
        "Web server started."
    )

    print(
        "Starting Discord bot..."
    )

    bot.run(TOKEN)


if __name__ == "__main__":
    main()
