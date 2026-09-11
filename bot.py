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

# Meta/Oculus GraphQL endpoint
META_GRAPHQL_URL = "https://graph.oculus.com/graphql"

DATA_FILE = "update_data.json"

META_STORE_URL = (
    "https://www.meta.com/experiences/quest/7190422614401072/"
)

# Animal Company icon
ANIMAL_COMPANY_ICON = (
    "https://www.animalcompanyvr.com/favicon.ico"
)


# ============================================================
# FLASK SERVER
# ============================================================

app = Flask(__name__)


@app.route("/")
def home():
    return "Animal Company Update Bot is running!"


def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
        use_reloader=False
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
# DATA STORAGE
# ============================================================

def load_saved_version():
    if not os.path.exists(DATA_FILE):
        return None

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        return data.get("version")

    except Exception as e:
        print(f"WARNING: Could not read {DATA_FILE}: {e}")
        return None


def save_version(version, version_code):
    data = {
        "version": version,
        "version_code": str(version_code)
    }

    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        print(
            f"Saved version: {version} "
            f"(code {version_code})"
        )

    except Exception as e:
        print(f"WARNING: Could not save version: {e}")


def load_saved_data():
    if not os.path.exists(DATA_FILE):
        return None

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    except Exception as e:
        print(f"WARNING: Could not read saved data: {e}")
        return None


# ============================================================
# META GRAPHQL
# ============================================================

async def meta_graphql_request(payload):
    """
    Sends a request to the Oculus GraphQL endpoint.
    """

    timeout = aiohttp.ClientTimeout(total=30)

    async with aiohttp.ClientSession(
        timeout=timeout
    ) as session:

        async with session.post(
            META_GRAPHQL_URL,
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
                print(text[:5000])

                raise RuntimeError(
                    f"Meta GraphQL returned HTTP "
                    f"{response.status}: {text}"
                )

            try:
                return json.loads(text)

            except json.JSONDecodeError:
                raise RuntimeError(
                    "Meta returned a non-JSON response: "
                    + text[:2000]
                )


# ============================================================
# FETCH ANIMAL COMPANY VERSION
# ============================================================

async def fetch_meta_version():
    """
    Gets the latest Animal Company version from
    Meta's Oculus GraphQL API.
    """

    print("================================")
    print("Fetching Animal Company version...")
    print("Meta endpoint:", META_GRAPHQL_URL)
    print("App ID:", ANIMAL_COMPANY_ID)

    payload = {
        "doc_id": "3828663700542720",
        "access_token": "OC|1076686279105243|",
        "variables": json.dumps({
            "applicationID": ANIMAL_COMPANY_ID
        })
    }

    data = await meta_graphql_request(payload)

    print("Meta response received.")

    # Check for GraphQL errors
    if data.get("errors"):
        raise RuntimeError(
            f"Meta GraphQL errors: {data['errors']}"
        )

    node = data.get("data", {}).get("node")

    if not node:
        raise RuntimeError(
            f"Meta response did not contain data.node: "
            f"{data}"
        )

    release_channels = (
        node
        .get("release_channels", {})
        .get("nodes", [])
    )

    if not release_channels:
        raise RuntimeError(
            f"No release channels returned: {data}"
        )

    latest_binary = release_channels[0].get(
        "latest_supported_binary"
    )

    if not latest_binary:
        raise RuntimeError(
            f"No latest_supported_binary returned: "
            f"{data}"
        )

    version = latest_binary.get("version")
    version_code = latest_binary.get("version_code")

    if not version:
        raise RuntimeError(
            f"Version was missing: {latest_binary}"
        )

    if version_code is None:
        raise RuntimeError(
            f"Version code was missing: {latest_binary}"
        )

    print("SUCCESS!")
    print("Version:", version)
    print("Version code:", version_code)
    print("================================")

    return version, str(version_code)


# ============================================================
# GET UPDATE ARTWORK
# ============================================================

async def get_update_artwork():
    """
    Gets Animal Company artwork from MetaMetadata.
    Artwork is only used for the Discord embed.
    """

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
                        "WARNING: Artwork source returned "
                        f"HTTP {response.status}"
                    )
                    return None

                data = await response.json()

                # Try several common image fields
                possible_fields = [
                    "image",
                    "cover",
                    "thumbnail",
                    "icon",
                    "banner",
                    "artwork"
                ]

                for field in possible_fields:
                    value = data.get(field)

                    if isinstance(value, str):
                        if value.startswith("http"):
                            return value

                return None

    except Exception as e:
        print(
            f"WARNING: Could not get artwork: {e}"
        )
        return None


# ============================================================
# MAKE DISCORD EMBED
# ============================================================

def make_update_embed(
    previous_version,
    new_version,
    version_code,
    artwork_url=None
):
    embed = discord.Embed(
        title="📦 New Animal Company Update!",
        color=discord.Color.blue()
    )

    # Author
    embed.set_author(
        name="Animal Company",
        icon_url=ANIMAL_COMPANY_ICON
    )

    # Version row
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

    # Released
    embed.add_field(
        name="🕐 Released",
        value="<t:{}:F>".format(
            int(discord.utils.utcnow().timestamp())
        ),
        inline=False
    )

    # Channel
    embed.add_field(
        name="📡 Channel",
        value="`LIVE`",
        inline=True
    )

    # Meta Store
    embed.add_field(
        name="🔗 Meta Store",
        value=(
            f"[Open Animal Company page]"
            f"({META_STORE_URL})"
        ),
        inline=True
    )

    # Small thumbnail
    if artwork_url:
        embed.set_thumbnail(url=artwork_url)

    # Large artwork
    if artwork_url:
        embed.set_image(url=artwork_url)

    # IMPORTANT:
    # No footer.

    return embed


# ============================================================
# SEND UPDATE
# ============================================================

async def send_update(
    previous_version,
    new_version,
    version_code
):
    channel = bot.get_channel(UPDATE_CHANNEL_ID)

    if channel is None:
        try:
            channel = await bot.fetch_channel(
                UPDATE_CHANNEL_ID
            )
        except Exception as e:
            print(
                f"ERROR: Could not find update channel: {e}"
            )
            return False

    artwork_url = await get_update_artwork()

    embed = make_update_embed(
        previous_version=previous_version,
        new_version=new_version,
        version_code=version_code,
        artwork_url=artwork_url
    )

    role_mention = f"<@&{UPDATE_ROLE_ID}>"

    try:
        await channel.send(
            content=role_mention,
            embed=embed
        )

        print(
            "Update notification sent successfully!"
        )

        return True

    except Exception as e:
        print(
            f"ERROR: Could not send update notification: "
            f"{e}"
        )

        return False


# ============================================================
# UPDATE CHECK
# ============================================================

async def check_for_updates():
    print(
        "Checking for Animal Company updates..."
    )

    try:
        new_version, new_version_code = (
            await fetch_meta_version()
        )

    except Exception as e:
        print(
            f"ERROR: Update check failed: {e}"
        )
        return

    saved_data = load_saved_data()

    # First startup
    if not saved_data:
        print(
            "No saved version found."
        )
        print(
            f"Current Animal Company version is "
            f"{new_version} ({new_version_code})"
        )
        print(
            "Saving current version without "
            "sending a notification."
        )

        save_version(
            new_version,
            new_version_code
        )

        return

    old_version = saved_data.get(
        "version",
        "Unknown"
    )

    old_version_code = str(
        saved_data.get(
            "version_code",
            ""
        )
    )

    # No update
    if (
        old_version == new_version
        and old_version_code == new_version_code
    ):
        print(
            f"No update. Current version: "
            f"{new_version} ({new_version_code})"
        )
        return

    # Update detected
    print("================================")
    print("NEW ANIMAL COMPANY UPDATE!")
    print(
        f"Previous: {old_version}"
    )
    print(
        f"New:      {new_version}"
    )
    print(
        f"Code:     {new_version_code}"
    )
    print("================================")

    success = await send_update(
        previous_version=old_version,
        new_version=new_version,
        version_code=new_version_code
    )

    # Only save after successful Discord message
    if success:
        save_version(
            new_version,
            new_version_code
        )


# ============================================================
# AUTOMATIC CHECKER
# ============================================================

@tasks.loop(minutes=CHECK_MINUTES)
async def automatic_update_check():
    await check_for_updates()


@automatic_update_check.before_loop
async def before_update_check():
    print(
        "Waiting for Discord to become ready..."
    )

    await bot.wait_until_ready()

    print("Discord is ready.")


# ============================================================
# BOT READY
# ============================================================

@bot.event
async def on_ready():

    print("===============================")
    print(
        f"Logged in as {bot.user}"
    )
    print(
        f"Bot ID: {bot.user.id}"
    )
    print(
        f"Update Channel ID: "
        f"{UPDATE_CHANNEL_ID}"
    )
    print(
        f"Update Role ID: "
        f"{UPDATE_ROLE_ID}"
    )
    print(
        f"Checking every "
        f"{CHECK_MINUTES} minutes."
    )
    print("===============================")

    if not automatic_update_check.is_running():

        print(
            "Automatic update checker STARTED."
        )

        automatic_update_check.start()


# ============================================================
# TEST COMMAND
# ============================================================

@bot.command(name="testupdate")
@commands.has_permissions(administrator=True)
async def testupdate(ctx):

    print(
        f"Test update requested by "
        f"{ctx.author}"
    )

    success = await send_update(
        previous_version="1.90.1.3492",
        new_version="1.90.2.3504",
        version_code="3504"
    )

    if success:
        await ctx.send(
            "✅ Test update sent."
        )
    else:
        await ctx.send(
            "❌ Failed to send test update."
        )


@testupdate.error
async def testupdate_error(ctx, error):

    if isinstance(
        error,
        commands.MissingPermissions
    ):
        await ctx.send(
            "❌ You need Administrator permission "
            "to use this command."
        )


# ============================================================
# START
# ============================================================

def main():

    print(
        "Starting Animal Company Update Bot..."
    )

    if not TOKEN:
        print(
            "ERROR: DISCORD_TOKEN is not set!"
        )
        return

    # Start Flask in background
    flask_thread = threading.Thread(
        target=run_flask,
        daemon=True
    )

    flask_thread.start()

    print("Connecting to Discord...")

    bot.run(TOKEN)


if __name__ == "__main__":
    main()
