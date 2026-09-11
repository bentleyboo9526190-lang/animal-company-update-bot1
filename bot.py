import os
import json
import threading
import asyncio
from datetime import datetime, timezone

from flask import Flask
import aiohttp
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

UPDATE_CHANNEL_ID = 1547679561960132695
UPDATE_ROLE_ID = 1547729517395714178

CHECK_MINUTES = 2
DATA_FILE = "update_data.json"

# Animal Company Meta Quest App ID
ANIMAL_COMPANY_ID = "7190422614401072"

# Meta/Oculus GraphQL endpoint used by MetaMetadata
META_GRAPHQL_URL = "https://www.meta.com/ocapi/graphql"

META_STORE_URL = (
    "https://www.meta.com/experiences/"
    "quest/7190422614401072/"
)

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


intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


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
            f"WARNING: Could not load saved data: {error}",
            flush=True
        )
        return default_data()


def save_data(data):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=4)

    except Exception as error:
        print(
            f"ERROR: Could not save data: {error}",
            flush=True
        )


def make_update_embed(
    previous_version,
    new_version,
    version_code,
    release_time,
    image_url=None,
    logo_url=None
):
    embed = discord.Embed(
        title="📦 New Animal Company Update!",
        color=discord.Color.red()
    )

    if logo_url:
        embed.set_author(
            name="Animal Company",
            icon_url=logo_url
        )
    else:
        embed.set_author(
            name="Animal Company"
        )

    if image_url:
        embed.set_thumbnail(
            url=image_url
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
        value=release_time,
        inline=False
    )

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

    if image_url:
        embed.set_image(
            url=image_url
        )

    return embed


async def fetch_animal_company():
    """Fetch the latest Animal Company Quest version from Meta's current OCAPI GraphQL endpoint."""
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    # Current MetaMetadata query documents.
    requests_to_try = [
        {
            "doc_id": "8571881679548867",
            "variables": {"applicationID": ANIMAL_COMPANY_ID},
        },
        {
            "doc_id": "3828663700542720",
            "variables": {"applicationID": ANIMAL_COMPANY_ID},
        },
    ]

    timeout = aiohttp.ClientTimeout(total=30)

    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        data = None
        last_error = None

        for request_index, request in enumerate(requests_to_try, 1):
            try:
                payload = {
                    "doc_id": request["doc_id"],
                    "access_token": "OC|1076686279105243|",
                    "variables": json.dumps(request["variables"]),
                }

                async with session.post(
                    META_GRAPHQL_URL,
                    data=payload
                ) as response:
                    body = await response.text()

                    if response.status != 200:
                        raise RuntimeError(
                            f"Meta OCAPI returned HTTP {response.status}: "
                            f"{body[:1000]}"
                        )

                    try:
                        data = json.loads(body)
                    except json.JSONDecodeError:
                        raise RuntimeError(
                            f"Meta OCAPI returned non-JSON response: "
                            f"{body[:500]}"
                        )

                if request_index == 1:
                    # The first request is store metadata. Continue to the
                    # app-details query to get the actual latest binary.
                    continue

                break

            except Exception as error:
                last_error = error
                print(
                    f"WARNING: Meta OCAPI request {request_index}/2 failed: "
                    f"{error}",
                    flush=True
                )

        if data is None:
            raise RuntimeError(
                f"Could not get Meta version data: {last_error}"
            )

        try:
            binary = (
                data["data"]["node"]["release_channels"]["nodes"][0]
                ["latest_supported_binary"]
            )
            version = binary["version"]
            version_code = binary["version_code"]
        except (KeyError, IndexError, TypeError) as error:
            raise RuntimeError(
                f"Meta OCAPI response did not contain latest binary: "
                f"{error}; response={str(data)[:1500]}"
            )

        if not version or version_code is None:
            raise RuntimeError(
                f"Meta returned an empty version/build: "
                f"{version} ({version_code})"
            )

        print(
            f"Meta OCAPI source: {version} ({version_code})",
            flush=True
        )

        image_url = None
        logo_url = None

        metadata_url = (
            "https://raw.githubusercontent.com/"
            "threethan/MetaMetadata/main/"
            "data/common/woosterGames.animalCompany.json"
        )

        try:
            async with session.get(metadata_url) as metadata_response:
                metadata_response.raise_for_status()
                metadata = await metadata_response.json(content_type=None)

                image_url = (
                    metadata.get("landscape")
                    or metadata.get("hero")
                    or metadata.get("portrait")
                    or metadata.get("square")
                )

                logo_url = (
                    metadata.get("logo")
                    or metadata.get("icon")
                )

        except Exception as error:
            print(
                f"WARNING: Could not load artwork: {error}",
                flush=True
            )

    return {
        "version": str(version),
        "version_code": version_code,
        "image_url": image_url,
        "logo_url": logo_url
    }


async def send_update(
    previous_version,
    new_version,
    version_code,
    release_time,
    image_url,
    logo_url
):
    channel = bot.get_channel(
        UPDATE_CHANNEL_ID
    )

    if channel is None:
        print(
            "Channel not found in cache. Fetching...",
            flush=True
        )

        try:
            channel = await bot.fetch_channel(
                UPDATE_CHANNEL_ID
            )

        except Exception as error:
            print(
                f"ERROR: Could not find channel: {error}",
                flush=True
            )
            return False

    embed = make_update_embed(
        previous_version=previous_version,
        new_version=new_version,
        version_code=version_code,
        release_time=release_time,
        image_url=image_url,
        logo_url=logo_url
    )

    role_mention = f"<@&{UPDATE_ROLE_ID}>"

    await channel.send(
        content=role_mention,
        embed=embed,
        allowed_mentions=discord.AllowedMentions(
            roles=True
        )
    )

    print(
        "Update notification sent successfully!",
        flush=True
    )

    return True


@tasks.loop(minutes=CHECK_MINUTES)
async def check_for_updates():
    print(
        "Checking for Animal Company updates...",
        flush=True
    )

    try:
        latest = await fetch_animal_company()

    except Exception as error:
        print(
            f"ERROR: Update check failed: {error}",
            flush=True
        )
        return

    latest_version = latest["version"]
    latest_code = latest["version_code"]

    image_url = latest["image_url"]
    logo_url = latest["logo_url"]

    data = load_data()

    previous_version = data.get(
        "version"
    )

    previous_code = data.get(
        "version_code"
    )

    print(
        f"Current Meta version: "
        f"{latest_version} ({latest_code})",
        flush=True
    )

    print(
        f"Saved bot version: "
        f"{previous_version} ({previous_code})",
        flush=True
    )

    # First startup
    if previous_version is None or previous_code is None:

        data["version"] = latest_version
        data["version_code"] = latest_code
        data["release_time"] = None

        save_data(data)

        print(
            "First startup detected.",
            flush=True
        )

        print(
            f"Saved current version: "
            f"{latest_version} ({latest_code})",
            flush=True
        )

        print(
            "No notification sent on first startup.",
            flush=True
        )

        return

    # Nothing changed
    if (
        str(previous_version) == str(latest_version)
        and
        str(previous_code) == str(latest_code)
    ):
        print(
            "No new Animal Company update.",
            flush=True
        )
        return

    # NEW UPDATE
    now = datetime.now(
        timezone.utc
    )

    release_time = now.strftime(
        "%A, %B %d, %Y at %I:%M %p UTC"
    )

    print(
        "================================",
        flush=True
    )

    print(
        "NEW ANIMAL COMPANY UPDATE!",
        flush=True
    )

    print(
        f"Previous: {previous_version}",
        flush=True
    )

    print(
        f"New: {latest_version}",
        flush=True
    )

    print(
        f"Code: {latest_code}",
        flush=True
    )

    print(
        "================================",
        flush=True
    )

    try:
        sent = await send_update(
            previous_version=previous_version,
            new_version=latest_version,
            version_code=latest_code,
            release_time=release_time,
            image_url=image_url,
            logo_url=logo_url
        )

    except Exception as error:
        print(
            f"ERROR: Could not send update: {error}",
            flush=True
        )
        return

    # Only save after Discord successfully receives it.
    if sent:

        data["version"] = latest_version
        data["version_code"] = latest_code
        data["release_time"] = release_time

        save_data(data)

        print(
            "New version saved.",
            flush=True
        )


@check_for_updates.before_loop
async def before_update_check():
    print(
        "Waiting for Discord to become ready...",
        flush=True
    )

    await bot.wait_until_ready()

    print(
        "Discord is ready.",
        flush=True
    )


@bot.event
async def on_ready():
    print(
        "================================",
        flush=True
    )

    print(
        f"Logged in as {bot.user}",
        flush=True
    )

    print(
        f"Bot ID: {bot.user.id}",
        flush=True
    )

    print(
        f"Update Channel ID: "
        f"{UPDATE_CHANNEL_ID}",
        flush=True
    )

    print(
        f"Update Role ID: "
        f"{UPDATE_ROLE_ID}",
        flush=True
    )

    print(
        f"Checking every {CHECK_MINUTES} minutes.",
        flush=True
    )

    print(
        "================================",
        flush=True
    )

    if not check_for_updates.is_running():

        check_for_updates.start()

        print(
            "Automatic update checker STARTED.",
            flush=True
        )

    else:

        print(
            "Automatic update checker is already running.",
            flush=True
        )


@bot.command()
@commands.has_permissions(
    administrator=True
)
async def testupdate(ctx):

    now = datetime.now(
        timezone.utc
    )

    release_time = now.strftime(
        "%A, %B %d, %Y at %I:%M %p UTC"
    )

    try:
        latest = await fetch_animal_company()

        image_url = latest["image_url"]
        logo_url = latest["logo_url"]

    except Exception:
        image_url = None
        logo_url = None

    embed = make_update_embed(
        previous_version="1.90.1.3492",
        new_version="1.90.2.3504",
        version_code="3504",
        release_time=release_time,
        image_url=image_url,
        logo_url=logo_url
    )

    role_mention = f"<@&{UPDATE_ROLE_ID}>"

    await ctx.send(
        content=role_mention,
        embed=embed,
        allowed_mentions=discord.AllowedMentions(
            roles=True
        )
    )

    print(
        "Manual test update sent.",
        flush=True
    )


@bot.event
async def on_command_error(ctx, error):

    if isinstance(
        error,
        commands.MissingPermissions
    ):
        return

    if isinstance(
        error,
        commands.CommandNotFound
    ):
        return

    print(
        f"Command error: {error}",
        flush=True
    )


if not TOKEN:
    raise RuntimeError(
        "DISCORD_TOKEN is missing!"
    )


print(
    "Starting Animal Company Update Bot...",
    flush=True
)

print(
    "Connecting to Discord...",
    flush=True
)

bot.run(TOKEN)
