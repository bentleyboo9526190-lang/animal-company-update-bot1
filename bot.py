import os
import json
import threading
from datetime import datetime, timezone

from flask import Flask
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

load_dotenv()

# =========================
# SETTINGS
# =========================

TOKEN = os.getenv("DISCORD_TOKEN")

UPDATE_CHANNEL_ID = int(
    os.getenv("UPDATE_CHANNEL_ID", "0")
)

UPDATE_ROLE_ID = int(
    os.getenv("UPDATE_ROLE_ID", "0")
)

DATA_FILE = "update_data.json"


# =========================
# WEB SERVER FOR RENDER
# =========================

app = Flask(__name__)


@app.route("/")
def home():
    return "Animal Company Update Bot is online!"


def run_web_server():
    port = int(os.getenv("PORT", "10000"))
    app.run(
        host="0.0.0.0",
        port=port
    )


# Start web server in background
web_thread = threading.Thread(
    target=run_web_server,
    daemon=True
)

web_thread.start()


# =========================
# DISCORD BOT
# =========================

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# =========================
# SAVE / LOAD UPDATE DATA
# =========================

def load_data():
    if not os.path.exists(DATA_FILE):
        return {
            "version": None,
            "version_code": None,
            "release_time": None
        }

    try:
        with open(
            DATA_FILE,
            "r",
            encoding="utf-8"
        ) as file:
            return json.load(file)

    except Exception:
        return {
            "version": None,
            "version_code": None,
            "release_time": None
        }


def save_data(data):
    with open(
        DATA_FILE,
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            data,
            file,
            indent=4
        )


# =========================
# UPDATE EMBED
# =========================

def make_update_embed(
    previous_version,
    new_version,
    version_code,
    release_time
):
    embed = discord.Embed(
        title="📦 New Animal Company Update!",
        color=discord.Color.green()
    )

    embed.add_field(
        name="⬅️ Previous Version",
        value=f"`{previous_version}`",
        inline=False
    )

    embed.add_field(
        name="📦 New Version",
        value=f"`{new_version}`",
        inline=False
    )

    embed.add_field(
        name="🔢 Version Code",
        value=f"`{version_code}`",
        inline=False
    )

    embed.add_field(
        name="🕐 Released",
        value=release_time,
        inline=False
    )

    embed.add_field(
        name="📡 Channel",
        value="`LIVE`",
        inline=False
    )

    return embed


# =========================
# SEND UPDATE
# =========================

async def send_update(
    previous_version,
    new_version,
    version_code,
    release_time
):
    channel = bot.get_channel(
        UPDATE_CHANNEL_ID
    )

    if channel is None:
        print("ERROR: Update channel not found.")
        return

    embed = make_update_embed(
        previous_version,
        new_version,
        version_code,
        release_time
    )

    role_mention = (
        f"<@&{UPDATE_ROLE_ID}>"
    )

    await channel.send(
        content=role_mention,
        embed=embed,
        allowed_mentions=discord.AllowedMentions(
            roles=True
        )
    )


# =========================
# UPDATE CHECKER
# =========================

@tasks.loop(minutes=2)
async def check_for_updates():

    print("Checking for Animal Company updates...")

    # =====================================
    # ACTUAL ANIMAL COMPANY CHECKER
    # WILL GO HERE NEXT
    # =====================================

    # We are NOT hard-coding versions here.
    #
    # The finished checker will automatically
    # get:
    #
    # Previous Version
    # New Version
    # Version Code
    # Release Time
    #
    # and compare it with the last update.


@check_for_updates.before_loop
async def before_update_check():
    await bot.wait_until_ready()


# =========================
# BOT STARTUP
# =========================

@bot.event
async def on_ready():

    print(
        f"Logged in as {bot.user}"
    )

    print(
        f"Update Channel ID: "
        f"{UPDATE_CHANNEL_ID}"
    )

    print(
        f"Update Role ID: "
        f"{UPDATE_ROLE_ID}"
    )

    if not check_for_updates.is_running():
        check_for_updates.start()


# =========================
# TEST COMMAND
# =========================

@bot.command()
@commands.has_permissions(
    administrator=True
)
async def testupdate(ctx):

    now = datetime.now(
        timezone.utc
    )

    release_time = now.strftime(
        "%B %d, %Y at %I:%M %p UTC"
    )

    embed = make_update_embed(
        previous_version="1.90.0.3474",
        new_version="1.90.1.3492",
        version_code="3492",
        release_time=release_time
    )

    role_mention = (
        f"<@&{UPDATE_ROLE_ID}>"
    )

    await ctx.send(
        content=role_mention,
        embed=embed,
        allowed_mentions=discord.AllowedMentions(
            roles=True
        )
    )


# =========================
# START BOT
# =========================

if not TOKEN:
    raise RuntimeError(
        "DISCORD_TOKEN is missing!"
    )

bot.run(TOKEN)
