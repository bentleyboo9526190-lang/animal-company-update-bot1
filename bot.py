import os
import re
import json
import requests
import discord
from discord.ext import commands, tasks
from datetime import datetime, timezone


# =========================================================
# CONFIG
# =========================================================

TOKEN = os.getenv("DISCORD_TOKEN")

UPDATE_CHANNEL_ID = int(os.getenv("UPDATE_CHANNEL_ID", "0"))
UPDATE_ROLE_ID = int(os.getenv("UPDATE_ROLE_ID", "0"))

# Last version already known to be released
KNOWN_GOOD_VERSION = "1.91.1.3570"

# Number of consecutive detections required
REQUIRED_CONFIRMATIONS = 2

# =========================================================
# VERSION SOURCES
# =========================================================

# Official Meta Animal Company page
META_STORE_URL = (
    "https://www.meta.com/en-gb/experiences/"
    "animal-company/7190422614401072/"
)

# Backup sources
VRDB_URL = (
    "https://vrdb.app/game/"
    "animal-company/7190422614401072"
)

QUEST_STORE_DB_URL = (
    "https://queststoredb.com/game/"
    "animal-company-7190422614401072/"
)

# =========================================================
# STATE
# =========================================================

STATE_FILE = "update_data.json"


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
# VERSION HELPERS
# =========================================================

def version_tuple(version):
    return tuple(
        int(x)
        for x in version.split(".")
    )


def valid_version(version):
    return bool(
        re.fullmatch(
            r"\d+\.\d+\.\d+\.\d+",
            version
        )
    )


# =========================================================
# STATE HELPERS
# =========================================================

def load_state():

    if not os.path.exists(STATE_FILE):
        return {}

    try:

        with open(
            STATE_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)

    except Exception as e:

        print(
            f"[STATE] Could not load state: {e}"
        )

        return {}


def save_state(state):

    try:

        with open(
            STATE_FILE,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                state,
                f,
                indent=4
            )

    except Exception as e:

        print(
            f"[STATE] Could not save state: {e}"
        )


# =========================================================
# META
# =========================================================

def get_meta_version():

    try:

        response = requests.get(
            META_STORE_URL,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/140.0.0.0 "
                    "Safari/537.36"
                )
            },
            timeout=15
        )

        print(
            f"[META] HTTP {response.status_code}"
        )

        if response.status_code != 200:
            return None

        html = response.text

        patterns = [

            r'"version"\s*:\s*"'
            r'(\d+\.\d+\.\d+\.\d+)"',

            r'"latestVersion"\s*:\s*"'
            r'(\d+\.\d+\.\d+\.\d+)"',

            r'"latest_version"\s*:\s*"'
            r'(\d+\.\d+\.\d+\.\d+)"',

            r'"versionName"\s*:\s*"'
            r'(\d+\.\d+\.\d+\.\d+)"',

            r'Version\s*</[^>]+>\s*'
            r'(\d+\.\d+\.\d+\.\d+)',

            r'Version\s*[:\-]\s*'
            r'(\d+\.\d+\.\d+\.\d+)'
        ]

        for pattern in patterns:

            match = re.search(
                pattern,
                html,
                re.IGNORECASE
            )

            if match:

                version = match.group(1)

                if valid_version(version):

                    print(
                        f"[META] Version found: "
                        f"{version}"
                    )

                    return version

        print(
            "[META] No readable version "
            "found on Meta page."
        )

        return None

    except Exception as e:

        print(
            f"[META] Error: {e}"
        )

        return None


# =========================================================
# VRDB
# =========================================================

def get_vrdb_version():

    try:

        response = requests.get(
            VRDB_URL,
            headers={
                "User-Agent": "Mozilla/5.0"
            },
            timeout=15
        )

        print(
            f"[VRDB] HTTP {response.status_code}"
        )

        if response.status_code != 200:
            return None

        matches = re.findall(
            r"\b\d+\.\d+\.\d+\.\d+\b",
            response.text
        )

        versions = []

        for version in matches:

            if valid_version(version):
                versions.append(version)

        if not versions:

            print(
                "[VRDB] No version found."
            )

            return None

        newest = max(
            versions,
            key=version_tuple
        )

        print(
            f"[VRDB] Version found: "
            f"{newest}"
        )

        return newest

    except Exception as e:

        print(
            f"[VRDB] Error: {e}"
        )

        return None


# =========================================================
# QUEST STORE DB
# =========================================================

def get_queststoredb_version():

    try:

        response = requests.get(
            QUEST_STORE_DB_URL,
            headers={
                "User-Agent": "Mozilla/5.0"
            },
            timeout=15
        )

        print(
            "[QUEST STORE DB] HTTP "
            f"{response.status_code}"
        )

        if response.status_code != 200:
            return None

        matches = re.findall(
            r"\b\d+\.\d+\.\d+\.\d+\b",
            response.text
        )

        versions = []

        for version in matches:

            if valid_version(version):
                versions.append(version)

        if not versions:

            print(
                "[QUEST STORE DB] "
                "No version found."
            )

            return None

        newest = max(
            versions,
            key=version_tuple
        )

        print(
            "[QUEST STORE DB] Version found: "
            f"{newest}"
        )

        return newest

    except Exception as e:

        print(
            "[QUEST STORE DB] Error: "
            f"{e}"
        )

        return None


# =========================================================
# FIND BEST VERSION
# =========================================================

def get_best_version():

    meta = get_meta_version()
    vrdb = get_vrdb_version()
    quest = get_queststoredb_version()

    print("")
    print("========== VERSION RESULTS ==========")
    print(f"Meta:          {meta}")
    print(f"VRDB:          {vrdb}")
    print(f"Quest Store:   {quest}")
    print("=====================================")
    print("")

    # -----------------------------------------------------
    # META IS PRIMARY
    # -----------------------------------------------------

    if meta:

        try:

            if (
                version_tuple(meta)
                >=
                version_tuple(KNOWN_GOOD_VERSION)
            ):

                print(
                    f"[VERSION] Using Meta: {meta}"
                )

                return (
                    meta,
                    "Meta Store"
                )

        except Exception:
            pass

    # -----------------------------------------------------
    # FALLBACKS
    # -----------------------------------------------------

    candidates = []

    if vrdb:
        candidates.append(
            ("VRDB", vrdb)
        )

    if quest:
        candidates.append(
            ("Quest Store DB", quest)
        )

    valid_candidates = []

    for source, version in candidates:

        try:

            if (
                version_tuple(version)
                >=
                version_tuple(KNOWN_GOOD_VERSION)
            ):

                valid_candidates.append(
                    (source, version)
                )

        except Exception:
            pass

    if valid_candidates:

        source, version = max(
            valid_candidates,
            key=lambda item:
                version_tuple(item[1])
        )

        print(
            f"[VERSION] Using fallback: "
            f"{version} ({source})"
        )

        return (
            version,
            source
        )

    # Nothing newer was detected
    print(
        "[VERSION] No newer version detected."
    )

    return (
        KNOWN_GOOD_VERSION,
        "Known Good"
    )


# =========================================================
# DISCORD UPDATE EMBED
# =========================================================

async def send_update(
    old_version,
    new_version,
    source,
    release_time=None
):

    channel = bot.get_channel(
        UPDATE_CHANNEL_ID
    )

    if channel is None:

        print(
            "[DISCORD] Update channel "
            "was not found."
        )

        return

    # Version code is the last number
    version_code = (
        new_version.split(".")[-1]
    )

    embed = discord.Embed(
        title="🦍 Animal Company",
        description=(
            "📦 **New Animal Company "
            "Update!**"
        ),
        color=discord.Color.red()
    )

    # -----------------------------------------------------
    # VERSION INFORMATION
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # RELEASE TIME
    # -----------------------------------------------------

    if release_time:

        embed.add_field(
            name="🕘 Released",
            value=release_time,
            inline=False
        )

    # -----------------------------------------------------
    # CHANNEL
    # -----------------------------------------------------

    embed.add_field(
        name="📡 Channel",
        value="`LIVE`",
        inline=True
    )

    # -----------------------------------------------------
    # META STORE
    # -----------------------------------------------------

    embed.add_field(
        name="🔗 Meta Store",
        value=(
            f"[Open Animal Company page]"
            f"({META_STORE_URL})"
        ),
        inline=True
    )

    # -----------------------------------------------------
    # FOOTER
    # -----------------------------------------------------

    embed.set_footer(
        text=f"Detected from {source}"
    )

    # -----------------------------------------------------
    # ROLE PING
    # -----------------------------------------------------

    role_mention = (
        f"<@&{UPDATE_ROLE_ID}>"
    )

    await channel.send(
        content=role_mention,
        embed=embed
    )

    print(
        "[DISCORD] Update announced: "
        f"{new_version}"
    )


# =========================================================
# AUTOMATIC UPDATE CHECKER
# =========================================================

@tasks.loop(seconds=20)
async def update_checker():

    try:

        version, source = (
            get_best_version()
        )

        if not version:
            return

        state = load_state()

        saved_version = state.get(
            "current_version"
        )

        pending_version = state.get(
            "pending_version"
        )

        confirmations = state.get(
            "confirmations",
            0
        )

        # -------------------------------------------------
        # FIRST RUN
        # -------------------------------------------------

        if not saved_version:

            state = {
                "current_version": version,
                "pending_version": None,
                "confirmations": 0
            }

            save_state(state)

            print(
                "[CHECKER] First run."
            )

            print(
                f"[CHECKER] Saved: {version}"
            )

            return

        # -------------------------------------------------
        # SAME VERSION
        # -------------------------------------------------

        if version == saved_version:

            if pending_version:

                print(
                    "[CHECKER] Pending update "
                    "disappeared."
                )

                state["pending_version"] = None
                state["confirmations"] = 0

                save_state(state)

            print(
                "[CHECKER] No update. "
                f"Current: {saved_version}"
            )

            return

        # -------------------------------------------------
        # OLDER VERSION
        # -------------------------------------------------

        if (
            version_tuple(version)
            <
            version_tuple(saved_version)
        ):

            print(
                "[CHECKER] Ignoring older "
                f"version: {version}"
            )

            return

        # -------------------------------------------------
        # NEW VERSION
        # -------------------------------------------------

        if pending_version == version:

            confirmations += 1

        else:

            pending_version = version
            confirmations = 1

        state["pending_version"] = (
            pending_version
        )

        state["confirmations"] = (
            confirmations
        )

        save_state(state)

        print(
            "[CHECKER] New version: "
            f"{version}"
        )

        print(
            "[CHECKER] Confirmation: "
            f"{confirmations}/"
            f"{REQUIRED_CONFIRMATIONS}"
        )

        # -------------------------------------------------
        # CONFIRMED
        # -------------------------------------------------

        if (
            confirmations
            >=
            REQUIRED_CONFIRMATIONS
        ):

            await send_update(
                saved_version,
                version,
                source
            )

            state = {
                "current_version": version,
                "pending_version": None,
                "confirmations": 0
            }

            save_state(state)

            print(
                "[CHECKER] UPDATE CONFIRMED!"
            )


# =========================================================
# CHECK VERSION COMMAND
# =========================================================

@bot.command()
async def checkversion(ctx):

    version, source = (
        get_best_version()
    )

    if not version:

        await ctx.send(
            "❌ Could not detect "
            "the Animal Company version."
        )

        return

    await ctx.send(
        "🔎 **Animal Company Version**\n"
        f"📦 Version: `{version}`\n"
        f"📡 Source: `{source}`"
    )


# =========================================================
# CHECK STATE COMMAND
# =========================================================

@bot.command()
async def checkstate(ctx):

    state = load_state()

    current = state.get(
        "current_version",
        "None"
    )

    pending = state.get(
        "pending_version",
        "None"
    )

    confirmations = state.get(
        "confirmations",
        0
    )

    await ctx.send(
        "📊 **Update Checker State**\n"
        f"📦 Current: `{current}`\n"
        f"⏳ Pending: `{pending}`\n"
        f"🔢 Confirmations: "
        f"`{confirmations}/{REQUIRED_CONFIRMATIONS}`"
    )


# =========================================================
# TEST UPDATE COMMAND
# =========================================================

@bot.command()
async def testupdate(ctx):

    await send_update(
        KNOWN_GOOD_VERSION,
        "1.91.2.9999",
        "TEST"
    )

    await ctx.send(
        "✅ Test update announcement sent."
    )


# =========================================================
# BOT READY
# =========================================================

@bot.event
async def on_ready():

    print("")
    print("==============================")
    print(" Animal Company Update Bot")
    print("==============================")
    print(
        f"Logged in as: {bot.user}"
    )
    print(
        f"Known version: "
        f"{KNOWN_GOOD_VERSION}"
    )
    print(
        "Meta: PRIMARY"
    )
    print(
        "VRDB: FALLBACK"
    )
    print(
        "Quest Store DB: FALLBACK"
    )
    print("==============================")
    print("")

    if not update_checker.is_running():

        update_checker.start()

        print(
            "[CHECKER] Started."
        )


# =========================================================
# START BOT
# =========================================================

if not TOKEN:

    raise RuntimeError(
        "DISCORD_TOKEN environment "
        "variable is missing."
    )


bot.run(TOKEN)
