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

OCULUS_GRAPHQL_URL = "https://graph.oculus.com/graphql"

META_STORE_URL = (
    "https://www.meta.com/experiences/animal-company/"
    "7190422614401072/"
)

ANIMAL_COMPANY_ICON = (
    "https://www.animalcompanyvr.com/favicon.ico"
)

DATA_FILE = "update_data.json"


# ============================================================
# FLASK
# ============================================================

app = Flask(__name__)


@app.route("/")
def home():
    return "Animal Company Update Bot is online!"


def run_web_server():
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
# SAVED DATA
# ============================================================

def load_saved_data():

    if not os.path.exists(DATA_FILE):
        return None

    try:

        with open(
            DATA_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)

    except Exception as e:

        print(
            f"ERROR reading saved data: {e}"
        )

        return None


def save_version(
    version,
    version_code
):

    data = {
        "version": str(version),
        "version_code": int(version_code)
    }

    try:

        with open(
            DATA_FILE,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                data,
                f,
                indent=2
            )

        print(
            f"Saved version: "
            f"{version} "
            f"(code {version_code})"
        )

    except Exception as e:

        print(
            f"ERROR saving version: {e}"
        )


# ============================================================
# META GRAPHQL
# ============================================================

async def graphql_request(payload):

    print(
        "Sending request to Meta GraphQL..."
    )

    timeout = aiohttp.ClientTimeout(
        total=30
    )

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
                    f"Meta HTTP status: "
                    f"{response.status}"
                )

                if response.status != 200:

                    print(
                        "Meta returned an error:"
                    )

                    print(
                        text[:5000]
                    )

                    return None

                try:

                    return json.loads(text)

                except Exception:

                    print(
                        "Meta response was "
                        "not JSON:"
                    )

                    print(
                        text[:5000]
                    )

                    return None

    except Exception as e:

        print(
            f"ERROR connecting to Meta: {e}"
        )

        return None


# ============================================================
# GET VERSION
# ============================================================

async def fetch_meta_version():

    print(
        "Fetching current Animal Company version..."
    )

    # First request
    store_payload = {

        "doc_id": "8571881679548867",

        "access_token":
            "OC|1076686279105243|",

        "variables": json.dumps({
            "applicationID":
                ANIMAL_COMPANY_ID
        })
    }

    store_data = await graphql_request(
        store_payload
    )

    if store_data is not None:

        print(
            "Store request completed."
        )

    # Second request
    details_payload = {

        "doc_id": "3828663700542720",

        "access_token":
            "OC|1076686279105243|",

        "variables": json.dumps({
            "applicationID":
                ANIMAL_COMPANY_ID
        })
    }

    data = await graphql_request(
        details_payload
    )

    if data is None:

        print(
            "Could not retrieve "
            "Animal Company version."
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
                "Meta response has no node."
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
                "No release channels "
                "were returned."
            )

            return None

        latest_binary = (
            release_channels[0]
            .get("latest_supported_binary")
        )

        if not latest_binary:

            print(
                "No latest supported "
                "binary was returned."
            )

            return None

        version = latest_binary.get(
            "version"
        )

        version_code = latest_binary.get(
            "version_code"
        )

        if version is None:

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
            "================================"
        )

        print(
            f"CURRENT VERSION: {version}"
        )

        print(
            f"VERSION CODE: {version_code}"
        )

        print(
            "================================"
        )

        return {
            "version": str(version),
            "version_code": int(version_code)
        }

    except Exception as e:

        print(
            f"ERROR parsing Meta data: {e}"
        )

        print(
            json.dumps(
                data,
                indent=2
            )[:5000]
        )

        return None


# ============================================================
# ARTWORK
# ============================================================

async def get_update_artwork():

    url = (
        "https://raw.githubusercontent.com/"
        "threethan/MetaMetadata/main/data/common/"
        "woosterGames.animalCompany.json"
    )

    try:

        timeout = aiohttp.ClientTimeout(
            total=20
        )

        async with aiohttp.ClientSession(
            timeout=timeout
        ) as session:

            async with session.get(
                url
            ) as response:

                if response.status != 200:

                    return None

                data = await response.json()

        fields = [
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

        for field in fields:

            value = data.get(field)

            if (
                isinstance(value, str)
                and value.startswith("http")
            ):

                return value

        return None

    except Exception as e:

        print(
            f"Artwork error: {e}"
        )

        return None


# ============================================================
# SEND UPDATE
# ============================================================

async def send_update(
    previous_version,
    new_version,
    version_code
):

    print(
        "Preparing Discord update message..."
    )

    channel = bot.get_channel(
        UPDATE_CHANNEL_ID
    )

    if channel is None:

        print(
            "Channel not cached. "
            "Fetching channel..."
        )

        try:

            channel = await bot.fetch_channel(
                UPDATE_CHANNEL_ID
            )

        except Exception as e:

            print(
                f"ERROR finding channel: {e}"
            )

            return False

    artwork = await get_update_artwork()

    embed = discord.Embed(
        title="📦 New Animal Company Update!",
        color=discord.Color.blue()
    )

    embed.set_author(
        name="Animal Company",
        icon_url=ANIMAL_COMPANY_ICON
    )

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

    embed.add_field(
        name="🕐 Released",
        value=(
            f"<t:{int(discord.utils.utcnow().timestamp())}:R>"
        ),
        inline=False
    )

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

    embed.set_thumbnail(
        url=ANIMAL_COMPANY_ICON
    )

    if artwork:

        embed.set_image(
            url=artwork
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

        print(
            "================================"
        )

        print(
            "UPDATE MESSAGE SENT!"
        )

        print(
            "================================"
        )

        return True

    except Exception as e:

        print(
            f"ERROR sending Discord message: {e}"
        )

        return False


# ============================================================
# CHECK FOR UPDATES
# ============================================================

async def check_for_updates():

    print(
        "--------------------------------"
    )

    print(
        "Checking for Animal Company updates..."
    )

    print(
        "--------------------------------"
    )

    current = await fetch_meta_version()

    if current is None:

        print(
            "Update check failed."
        )

        return

    current_version = current[
        "version"
    ]

    current_code = current[
        "version_code"
    ]

    saved = load_saved_data()

    # First run
    if saved is None:

        print(
            "This is the first successful check."
        )

        print(
            f"Saving {current_version} "
            f"(code {current_code})"
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
        f"Saved: {previous_version} "
        f"(code {previous_code})"
    )

    print(
        f"Current: {current_version} "
        f"(code {current_code})"
    )

    # No update
    if (
        str(previous_version)
        == str(current_version)
        and
        int(previous_code)
        == int(current_code)
    ):

        print(
            "No new update."
        )

        return

    # New update
    print(
        "================================"
    )

    print(
        "NEW UPDATE DETECTED!"
    )

    print(
        f"{previous_version} -> "
        f"{current_version}"
    )

    print(
        f"New code: {current_code}"
    )

    print(
        "================================"
    )

    sent = await send_update(
        previous_version,
        current_version,
        current_code
    )

    if sent:

        save_version(
            current_version,
            current_code
        )

    else:

        print(
            "Message failed. "
            "Saved version was not changed."
        )


# ============================================================
# AUTOMATIC CHECKER
# ============================================================

@tasks.loop(minutes=CHECK_MINUTES)
async def update_checker():

    try:

        await check_for_updates()

    except Exception as e:

        print(
            f"UPDATE CHECKER ERROR: {e}"
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
        "========================================"
    )

    print(
        f"Logged in as {bot.user}"
    )

    print(
        f"Bot ID: {bot.user.id}"
    )

    print(
        "Discord connection is READY."
    )

    print(
        "========================================"
    )

    if not update_checker.is_running():

        update_checker.start()

        print(
            "Automatic checker started."
        )

    # Immediate check instead of waiting 2 minutes
    await asyncio.sleep(5)

    print(
        "Running initial update check..."
    )

    try:

        await check_for_updates()

    except Exception as e:

        print(
            f"Initial check error: {e}"
        )


# ============================================================
# TEST COMMAND
# ============================================================

@bot.command()
@commands.has_permissions(
    administrator=True
)
async def testupdate(ctx):

    print(
        "Test update command received."
    )

    sent = await send_update(
        "1.90.1.3492",
        "1.90.2.3504",
        3504
    )

    if sent:

        await ctx.send(
            "✅ Test update sent."
        )

    else:

        await ctx.send(
            "❌ Test update failed."
        )


# ============================================================
# COMMAND ERRORS
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
            "❌ You need administrator "
            "permission to use that."
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
# MAIN
# ============================================================

def main():

    if not TOKEN:

        print(
            "ERROR: DISCORD_TOKEN is missing!"
        )

        return

    print(
        "Starting Animal Company Update Bot..."
    )

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


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    main()
