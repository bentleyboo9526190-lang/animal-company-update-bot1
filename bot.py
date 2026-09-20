import os
import re
import json
import requests
import discord
from discord.ext import commands, tasks


# =========================================================
# CONFIG
# =========================================================

TOKEN = os.getenv("DISCORD_TOKEN")

UPDATE_CHANNEL_ID = int(
    os.getenv("UPDATE_CHANNEL_ID", "0")
)

UPDATE_ROLE_ID = int(
    os.getenv("UPDATE_ROLE_ID", "0")
)

# Current known Animal Company version
KNOWN_GOOD_VERSION = "1.91.1.3570"

# Number of times a new version must be detected
REQUIRED_CONFIRMATIONS = 2

STATE_FILE = "update_data.json"


# =========================================================
# VERSION SOURCES
# =========================================================

META_STORE_URL = (
    "https://www.meta.com/en-gb/experiences/"
    "animal-company/7190422614401072/"
)

VRDB_URL = (
    "https://vrdb.app/game/"
    "animal-company/7190422614401072"
)

QUEST_STORE_DB_URL = (
    "https://queststoredb.com/game/"
    "animal-company-7190422614401072/"
)


# =========================================================
# DISCORD SETUP
# =========================================================

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# =========================================================
# VERSION FUNCTIONS
# =========================================================

def version_tuple(version):
    return tuple(
        int(number)
        for number in version.split(".")
    )


def valid_version(version):
    return bool(
        re.fullmatch(
            r"\d+\.\d+\.\d+\.\d+",
            version
        )
    )


def extract_versions(text):
    matches = re.findall(
        r"\b\d+\.\d+\.\d+\.\d+\b",
        text
    )

    versions = []

    for version in matches:
        if valid_version(version):
            if version not in versions:
                versions.append(version)

    return versions


# =========================================================
# STATE
# =========================================================

def load_state():

    if not os.path.exists(STATE_FILE):
        return {}

    try:

        with open(
            STATE_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(file)

        if isinstance(data, dict):
            return data

        return {}

    except Exception as error:

        print(
            f"[STATE] Load error: {error}"
        )

        return {}


def save_state(state):

    try:

        with open(
            STATE_FILE,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                state,
                file,
                indent=4
            )

    except Exception as error:

        print(
            f"[STATE] Save error: {error}"
        )


# =========================================================
# META VERSION
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
            "[META] No readable version found."
        )

        return None

    except Exception as error:

        print(
            f"[META] Error: {error}"
        )

        return None


# =========================================================
# VRDB VERSION
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

        versions = extract_versions(
            response.text
        )

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

    except Exception as error:

        print(
            f"[VRDB] Error: {error}"
        )

        return None


# =========================================================
# QUEST STORE DB VERSION
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

        versions = extract_versions(
            response.text
        )

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

    except Exception as error:

        print(
            "[QUEST STORE DB] Error: "
            f"{error}"
        )

        return None


# =========================================================
# GET BEST VERSION
# =========================================================

def get_best_version():

    meta = get_meta_version()

    vrdb = get_vrdb_version()

    quest = get_queststoredb_version()

    print("")
    print("========== VERSION RESULTS ==========")
    print(f"Meta:        {meta}")
    print(f"VRDB:        {vrdb}")
    print(f"Quest DB:    {quest}")
    print("=====================================")
    print("")

    # Meta is preferred
    if meta:

        try:

            if (
                version_tuple(meta)
                >=
                version_tuple(KNOWN_GOOD_VERSION)
            ):

                return (
                    meta,
                    "Meta Store"
                )

        except Exception:
            pass

    # Fallback sources
    candidates = []

    if vrdb:

        try:

            if (
                version_tuple(vrdb)
                >=
                version_tuple(KNOWN_GOOD_VERSION)
            ):

                candidates.append(
                    (vrdb, "VRDB")
                )

        except Exception:
            pass

    if quest:

        try:

            if (
                version_tuple(quest)
                >=
                version_tuple(KNOWN_GOOD_VERSION)
            ):

                candidates.append(
                    (
                        quest,
                        "Quest Store DB"
                    )
                )

        except Exception:
            pass

    if candidates:

        version, source = max(
            candidates,
            key=lambda item:
            version_tuple(item[0])
        )

        return (
            version,
            source
        )

    return (
        KNOWN_GOOD_VERSION,
        "Known Good"
    )


# =========================================================
# SEND UPDATE
# =========================================================

async def send_update(
    old_version,
    new_version,
    source,
    release_time=None,
    test=False
):

    channel = bot.get_channel(
        UPDATE_CHANNEL_ID
    )

    if channel is None:

        print(
            "[DISCORD] Update channel "
            "not found."
        )

        return False

    version_code = (
        new_version.split(".")[-1]
    )

    if test:

        description = (
            "🧪 **TEST — New Animal "
            "Company Update!**"
        )

    else:

        description = (
            "📦 **New Animal Company "
            "Update!**"
        )

    embed = discord.Embed(
        title="🦍 Animal Company",
        description=description,
        color=discord.Color.orange()
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

    if release_time:

        embed.add_field(
            name="🕘 Released",
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
        value=(
            f"[Open Animal Company page]"
            f"({META_STORE_URL})"
        ),
        inline=True
    )

    embed.set_footer(
        text=f"Detected from {source}"
    )

    role_mention = (
        f"<@&{UPDATE_ROLE_ID}>"
    )

    await channel.send(
        content=role_mention,
        embed=embed
    )

    print(
        f"[DISCORD] Announcement sent: "
        f"{new_version}"
    )

    return True


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

            print(
                "[CHECKER] No version detected."
            )

            return

        state = load_state()

        saved_version = state.get(
            "current_version"
        )

        pending_version = state.get(
            "pending_version"
        )

        confirmations = int(
            state.get(
                "confirmations",
                0
            )
        )

        # First run
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

        # Same version
        if version == saved_version:

            if pending_version:

                print(
                    "[CHECKER] Pending update "
                    "disappeared."
                )

                state[
                    "pending_version"
                ] = None

                state[
                    "confirmations"
                ] = 0

                save_state(state)

            print(
                "[CHECKER] No update. "
                f"Current: {saved_version}"
            )

            return

        # Older version
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

        # New version
        if pending_version == version:

            confirmations += 1

        else:

            pending_version = version
            confirmations = 1

        state[
            "pending_version"
        ] = pending_version

        state[
            "confirmations"
        ] = confirmations

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

        # Confirmed update
        if (
            confirmations
            >=
            REQUIRED_CONFIRMATIONS
        ):

            sent = await send_update(
                saved_version,
                version,
                source
            )

            if sent:

                state = {
                    "current_version": version,
                    "pending_version": None,
                    "confirmations": 0
                }

                save_state(state)

                print(
                    "[CHECKER] UPDATE "
                    "CONFIRMED!"
                )

    except Exception as error:

        print(
            f"[CHECKER] Error: {error}"
        )


# =========================================================
# CHECK VERSION COMMAND
# =========================================================

@bot.command()
async def checkversion(ctx):

    try:

        version, source = (
            get_best_version()
        )

        await ctx.send(
            "🔎 **Animal Company Version**\n"
            f"📦 Version: `{version}`\n"
            f"📡 Source: `{source}`"
        )

    except Exception as error:

        await ctx.send(
            "❌ Version check failed:\n"
            f"`{error}`"
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
        f"`{confirmations}/"
        f"{REQUIRED_CONFIRMATIONS}`"
    )


# =========================================================
# TEST UPDATE COMMAND
# =========================================================

@bot.command()
@commands.has_permissions(
    administrator=True
)
async def testupdate(ctx):

    sent = await send_update(
        KNOWN_GOOD_VERSION,
        "1.91.2.9999",
        "TEST",
        test=True
    )

    if sent:

        await ctx.send(
            "✅ Test announcement sent."
        )

    else:

        await ctx.send(
            "❌ Update channel not found."
        )


# =========================================================
# COMMAND ERROR HANDLER
# =========================================================

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
            "permissions to use that command."
        )

        return

    if isinstance(
        error,
        commands.CommandNotFound
    ):

        return

    print(
        f"[COMMAND] Error: {error}"
    )


# =========================================================
# BOT READY
# =========================================================

@bot.event
async def on_ready():

    print("")
    print("================================")
    print(" Animal Company Update Bot")
    print("================================")
    print(
        f"Logged in as: {bot.user}"
    )
    print(
        f"Known version: "
        f"{KNOWN_GOOD_VERSION}"
    )
    print("Meta: PRIMARY")
    print("VRDB: FALLBACK")
    print("Quest Store DB: FALLBACK")
    print("================================")
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
