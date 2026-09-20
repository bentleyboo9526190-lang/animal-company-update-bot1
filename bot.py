import os
import re
import json
import html
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

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

KNOWN_GOOD_VERSION = "1.91.1.3570"

REQUIRED_CONFIRMATIONS = 2

STATE_FILE = "update_data.json"


# =========================================================
# URLS
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


def extract_versions(text):
    found = re.findall(
        r"\b\d+\.\d+\.\d+\.\d+\b",
        text
    )

    return list(
        dict.fromkeys(
            version
            for version in found
            if valid_version(version)
        )
    )


# =========================================================
# HTTP HELPER
# =========================================================

def fetch_page(url):
    """
    Downloads a webpage using Python's built-in urllib.

    This replaces the requests package completely.
    """

    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/140.0.0.0 "
                "Safari/537.36"
            )
        }
    )

    try:

        with urlopen(
            request,
            timeout=15
        ) as response:

            body = response.read().decode(
                "utf-8",
                errors="replace"
            )

            return (
                response.status,
                body
            )

    except HTTPError as error:

        print(
            f"[HTTP] HTTP error for {url}: "
            f"{error.code}"
        )

        return (
            error.code,
            ""
        )

    except URLError as error:

        print(
            f"[HTTP] URL error for {url}: "
            f"{error}"
        )

        return (
            0,
            ""
        )

    except Exception as error:

        print(
            f"[HTTP] Error for {url}: "
            f"{error}"
        )

        return (
            0,
            ""
        )


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
# META ARTWORK
# =========================================================

def get_meta_artwork():

    try:

        status, page = fetch_page(
            META_STORE_URL
        )

        print(
            "[META] Artwork request: "
            f"HTTP {status}"
        )

        if status != 200:
            return None

        page = html.unescape(page)

        patterns = [

            r'https://[^"\']+oculuscdn\.com[^"\']+',

            r'https://scontent[^"\']+'
        ]

        for pattern in patterns:

            match = re.search(
                pattern,
                page
            )

            if match:

                artwork = match.group(0)

                artwork = artwork.replace(
                    "\\u0026",
                    "&"
                )

                artwork = artwork.replace(
                    "\\/",
                    "/"
                )

                print(
                    "[META] Artwork found."
                )

                return artwork

        print(
            "[META] Artwork URL not found."
        )

        return None

    except Exception as error:

        print(
            f"[META] Artwork error: "
            f"{error}"
        )

        return None


# =========================================================
# META VERSION
# =========================================================

def get_meta_version():

    try:

        status, page = fetch_page(
            META_STORE_URL
        )

        print(
            "[META] Version request: "
            f"HTTP {status}"
        )

        if status != 200:
            return None

        patterns = [

            r'"version"\s*:\s*"'
            r'(\d+\.\d+\.\d+\.\d+)"',

            r'"latestVersion"\s*:\s*"'
            r'(\d+\.\d+\.\d+\.\d+)"',

            r'"latest_version"\s*:\s*"'
            r'(\d+\.\d+\.\d+\.\d+)"',

            r'"versionName"\s*:\s*"'
            r'(\d+\.\d+\.\d+\.\d+)"'
        ]

        for pattern in patterns:

            match = re.search(
                pattern,
                page,
                re.IGNORECASE
            )

            if match:

                version = match.group(1)

                if valid_version(version):

                    print(
                        f"[META] Version: "
                        f"{version}"
                    )

                    return version

        print(
            "[META] Version not available "
            "in page source."
        )

        return None

    except Exception as error:

        print(
            f"[META] Version error: "
            f"{error}"
        )

        return None


# =========================================================
# GENERIC VERSION SOURCE
# =========================================================

def get_page_version(
    url,
    source_name
):

    try:

        status, page = fetch_page(url)

        print(
            f"[{source_name}] HTTP "
            f"{status}"
        )

        if status != 200:

            return None

        versions = extract_versions(
            page
        )

        if not versions:

            print(
                f"[{source_name}] "
                "No version found."
            )

            return None

        newest = max(
            versions,
            key=version_tuple
        )

        print(
            f"[{source_name}] Version: "
            f"{newest}"
        )

        return newest

    except Exception as error:

        print(
            f"[{source_name}] Error: "
            f"{error}"
        )

        return None


# =========================================================
# VRDB
# =========================================================

def get_vrdb_version():

    return get_page_version(
        VRDB_URL,
        "VRDB"
    )


# =========================================================
# QUEST STORE DB
# =========================================================

def get_queststoredb_version():

    return get_page_version(
        QUEST_STORE_DB_URL,
        "QUEST STORE DB"
    )


# =========================================================
# BEST VERSION
# =========================================================

def get_best_version():

    meta = get_meta_version()

    vrdb = get_vrdb_version()

    quest = get_queststoredb_version()

    print("")
    print(
        "========== VERSION RESULTS =========="
    )

    print(
        f"Meta:     {meta}"
    )

    print(
        f"VRDB:     {vrdb}"
    )

    print(
        f"Quest DB: {quest}"
    )

    print(
        "====================================="
    )

    print("")

    # -----------------------------------------------------
    # META FIRST
    # -----------------------------------------------------

    if meta:

        try:

            if (
                version_tuple(meta)
                >=
                version_tuple(
                    KNOWN_GOOD_VERSION
                )
            ):

                print(
                    "[VERSION] Using Meta: "
                    f"{meta}"
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

    for version, source in [

        (
            vrdb,
            "VRDB"
        ),

        (
            quest,
            "Quest Store DB"
        )

    ]:

        if version:

            try:

                if (
                    version_tuple(version)
                    >=
                    version_tuple(
                        KNOWN_GOOD_VERSION
                    )
                ):

                    candidates.append(
                        (
                            version,
                            source
                        )
                    )

            except Exception:

                pass

    if candidates:

        best = max(
            candidates,
            key=lambda item:
            version_tuple(item[0])
        )

        print(
            "[VERSION] Best detected: "
            f"{best[0]} "
            f"({best[1]})"
        )

        return best

    print(
        "[VERSION] No newer version "
        "detected."
    )

    return (
        KNOWN_GOOD_VERSION,
        "Known Good"
    )


# =========================================================
# VERSION EMBED
# =========================================================

def make_version_embed(
    version,
    source,
    artwork=None
):

    version_code = (
        version.split(".")[-1]
    )

    embed = discord.Embed(
        title="🦍 Animal Company",
        description=(
            "🔎 **Animal Company "
            "Version Check**"
        ),
        color=discord.Color.orange()
    )

    embed.add_field(
        name="📦 Version",
        value=f"`{version}`",
        inline=False
    )

    embed.add_field(
        name="🔢 Version Code",
        value=f"`{version_code}`",
        inline=True
    )

    embed.add_field(
        name="📡 Source",
        value=f"`{source}`",
        inline=True
    )

    embed.add_field(
        name="🔗 Meta Store",
        value=(
            f"[Open Animal Company page]"
            f"({META_STORE_URL})"
        ),
        inline=False
    )

    if artwork:

        embed.set_image(
            url=artwork
        )

    embed.set_footer(
        text="Animal Company Update Watcher"
    )

    return embed


# =========================================================
# SEND UPDATE
# =========================================================

async def send_update(
    old_version,
    new_version,
    source,
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

    artwork = get_meta_artwork()

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
        value=(
            f"`{new_version.split('.')[-1]}`"
        ),
        inline=True
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

    if artwork:

        embed.set_image(
            url=artwork
        )

    embed.set_footer(
        text=f"Detected from {source}"
    )

    await channel.send(
        content=f"<@&{UPDATE_ROLE_ID}>",
        embed=embed
    )

    print(
        "[DISCORD] Update sent: "
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

        # -------------------------------------------------
        # FIRST RUN
        # -------------------------------------------------

        if not saved_version:

            save_state({

                "current_version":
                    version,

                "pending_version":
                    None,

                "confirmations":
                    0
            })

            print(
                "[CHECKER] Saved version: "
                f"{version}"
            )

            return

        # -------------------------------------------------
        # NO UPDATE
        # -------------------------------------------------

        if version == saved_version:

            if pending_version:

                save_state({

                    "current_version":
                        saved_version,

                    "pending_version":
                        None,

                    "confirmations":
                        0
                })

            print(
                "[CHECKER] No update. "
                f"Current version: "
                f"{saved_version}"
            )

            return

        # -------------------------------------------------
        # IGNORE OLDER VERSION
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

            confirmations = 1

        save_state({

            "current_version":
                saved_version,

            "pending_version":
                version,

            "confirmations":
                confirmations
        })

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

            sent = await send_update(
                saved_version,
                version,
                source
            )

            if sent:

                save_state({

                    "current_version":
                        version,

                    "pending_version":
                        None,

                    "confirmations":
                        0
                })

                print(
                    "[CHECKER] UPDATE "
                    "CONFIRMED!"
                )

    except Exception as error:

        print(
            f"[CHECKER] Error: {error}"
        )


# =========================================================
# !CHECKVERSION
# =========================================================

@bot.command()
async def checkversion(ctx):

    try:

        await ctx.send(
            "🔎 Checking Animal Company "
            "version..."
        )

        version, source = (
            get_best_version()
        )

        artwork = get_meta_artwork()

        embed = make_version_embed(
            version,
            source,
            artwork
        )

        await ctx.send(
            embed=embed
        )

        print(
            "[COMMAND] checkversion: "
            f"{version} ({source})"
        )

    except Exception as error:

        print(
            "[COMMAND] checkversion "
            f"error: {error}"
        )

        await ctx.send(
            "❌ Version check failed:\n"
            f"`{error}`"
        )


# =========================================================
# !CHECKSTATE
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
# !TESTUPDATE
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
            "✅ Test update announcement sent."
        )

    else:

        await ctx.send(
            "❌ Update channel not found."
        )


# =========================================================
# COMMAND ERRORS
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
    print(
        "================================"
    )
    print(
        " Animal Company Update Bot"
    )
    print(
        "================================"
    )
    print(
        f"Logged in as: {bot.user}"
    )
    print(
        f"Known version: "
        f"{KNOWN_GOOD_VERSION}"
    )
    print(
        "Artwork: Meta"
    )
    print(
        "Version: Meta -> VRDB -> "
        "Quest Store DB"
    )
    print(
        "================================"
    )
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
