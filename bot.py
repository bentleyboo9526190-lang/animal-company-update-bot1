import os
import re
import json
import requests
import discord
from discord.ext import commands, tasks

TOKEN = os.getenv("DISCORD_TOKEN")
UPDATE_CHANNEL_ID = int(os.getenv("UPDATE_CHANNEL_ID", "0"))
UPDATE_ROLE_ID = int(os.getenv("UPDATE_ROLE_ID", "0"))

KNOWN_GOOD_VERSION = "1.91.1.3570"
REQUIRED_CONFIRMATIONS = 2
STATE_FILE = "update_data.json"

META_STORE_URL = "https://www.meta.com/en-gb/experiences/animal-company/7190422614401072/"
VRDB_URL = "https://vrdb.app/game/animal-company/7190422614401072"
QUEST_STORE_DB_URL = "https://queststoredb.com/game/animal-company-7190422614401072/"

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


def version_tuple(version):
    return tuple(int(x) for x in version.split("."))


def valid_version(version):
    return bool(re.fullmatch(r"\d+\.\d+\.\d+\.\d+", version))


def extract_versions(text):
    found = re.findall(r"\b\d+\.\d+\.\d+\.\d+\b", text)
    return list(dict.fromkeys(v for v in found if valid_version(v)))


def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as error:
        print(f"[STATE] Load error: {error}")
        return {}


def save_state(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=4)
    except Exception as error:
        print(f"[STATE] Save error: {error}")


def request_page(url):
    return requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=15
    )


def get_meta_artwork():
    try:
        response = request_page(META_STORE_URL)
        print(f"[META] Artwork request: HTTP {response.status_code}")

        if response.status_code != 200:
            return None

        patterns = [
            r'https://[^"\']+oculuscdn\.com[^"\']+',
            r'https://scontent[^"\']+'
        ]

        for pattern in patterns:
            match = re.search(pattern, response.text)
            if match:
                url = match.group(0)
                url = url.replace("\\u0026", "&").replace("\\/", "/")
                print("[META] Artwork found.")
                return url

        print("[META] Artwork URL not found.")
        return None
    except Exception as error:
        print(f"[META] Artwork error: {error}")
        return None


def get_meta_version():
    try:
        response = request_page(META_STORE_URL)
        print(f"[META] Version request: HTTP {response.status_code}")

        if response.status_code != 200:
            return None

        patterns = [
            r'"version"\s*:\s*"(\d+\.\d+\.\d+\.\d+)"',
            r'"latestVersion"\s*:\s*"(\d+\.\d+\.\d+\.\d+)"',
            r'"latest_version"\s*:\s*"(\d+\.\d+\.\d+\.\d+)"',
            r'"versionName"\s*:\s*"(\d+\.\d+\.\d+\.\d+)"',
        ]

        for pattern in patterns:
            match = re.search(pattern, response.text, re.IGNORECASE)
            if match and valid_version(match.group(1)):
                return match.group(1)

        return None
    except Exception as error:
        print(f"[META] Version error: {error}")
        return None


def get_page_version(url, name):
    try:
        response = request_page(url)
        print(f"[{name}] HTTP {response.status_code}")

        if response.status_code != 200:
            return None

        versions = extract_versions(response.text)
        if not versions:
            print(f"[{name}] No version found.")
            return None

        newest = max(versions, key=version_tuple)
        print(f"[{name}] Version: {newest}")
        return newest
    except Exception as error:
        print(f"[{name}] Error: {error}")
        return None


def get_vrdb_version():
    return get_page_version(VRDB_URL, "VRDB")


def get_queststoredb_version():
    return get_page_version(QUEST_STORE_DB_URL, "QUEST STORE DB")


def get_best_version():
    meta = get_meta_version()
    vrdb = get_vrdb_version()
    quest = get_queststoredb_version()

    print(f"[RESULT] Meta={meta}")
    print(f"[RESULT] VRDB={vrdb}")
    print(f"[RESULT] Quest Store DB={quest}")

    if meta:
        try:
            if version_tuple(meta) >= version_tuple(KNOWN_GOOD_VERSION):
                return meta, "Meta Store"
        except Exception:
            pass

    candidates = []
    for version, source in [
        (vrdb, "VRDB"),
        (quest, "Quest Store DB")
    ]:
        if version:
            try:
                if version_tuple(version) >= version_tuple(KNOWN_GOOD_VERSION):
                    candidates.append((version, source))
            except Exception:
                pass

    if candidates:
        return max(candidates, key=lambda item: version_tuple(item[0]))

    return KNOWN_GOOD_VERSION, "Known Good"


def make_embed(title, description, version, source, artwork=None):
    code = version.split(".")[-1]

    embed = discord.Embed(
        title=title,
        description=description,
        color=discord.Color.orange()
    )

    embed.add_field(name="📦 Version", value=f"`{version}`", inline=False)
    embed.add_field(name="🔢 Version Code", value=f"`{code}`", inline=True)
    embed.add_field(name="📡 Source", value=f"`{source}`", inline=True)
    embed.add_field(
        name="🔗 Meta Store",
        value=f"[Open Animal Company page]({META_STORE_URL})",
        inline=False
    )

    if artwork:
        embed.set_image(url=artwork)

    embed.set_footer(text="Animal Company Update Watcher")
    return embed


async def send_update(old_version, new_version, source, test=False):
    channel = bot.get_channel(UPDATE_CHANNEL_ID)

    if channel is None:
        print("[DISCORD] Update channel not found.")
        return False

    artwork = get_meta_artwork()

    description = (
        "🧪 **TEST — New Animal Company Update!**"
        if test
        else "📦 **New Animal Company Update!**"
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
        value=f"`{new_version.split('.')[-1]}`",
        inline=True
    )
    embed.add_field(name="📡 Channel", value="`LIVE`", inline=True)
    embed.add_field(
        name="🔗 Meta Store",
        value=f"[Open Animal Company page]({META_STORE_URL})",
        inline=True
    )

    if artwork:
        embed.set_image(url=artwork)

    embed.set_footer(text=f"Detected from {source}")

    await channel.send(
        content=f"<@&{UPDATE_ROLE_ID}>",
        embed=embed
    )

    print(f"[DISCORD] Update sent: {new_version}")
    return True


@tasks.loop(seconds=20)
async def update_checker():
    try:
        version, source = get_best_version()
        state = load_state()

        saved = state.get("current_version")
        pending = state.get("pending_version")
        confirmations = int(state.get("confirmations", 0))

        if not saved:
            save_state({
                "current_version": version,
                "pending_version": None,
                "confirmations": 0
            })
            print(f"[CHECKER] Saved version: {version}")
            return

        if version == saved:
            if pending:
                save_state({
                    "current_version": saved,
                    "pending_version": None,
                    "confirmations": 0
                })
            print(f"[CHECKER] No update. Current version: {saved}")
            return

        if version_tuple(version) < version_tuple(saved):
            print(f"[CHECKER] Ignoring older version: {version}")
            return

        if pending == version:
            confirmations += 1
        else:
            confirmations = 1

        save_state({
            "current_version": saved,
            "pending_version": version,
            "confirmations": confirmations
        })

        print(
            f"[CHECKER] New version {version} "
            f"confirmation {confirmations}/{REQUIRED_CONFIRMATIONS}"
        )

        if confirmations >= REQUIRED_CONFIRMATIONS:
            sent = await send_update(saved, version, source)

            if sent:
                save_state({
                    "current_version": version,
                    "pending_version": None,
                    "confirmations": 0
                })
                print("[CHECKER] UPDATE CONFIRMED!")

    except Exception as error:
        print(f"[CHECKER] Error: {error}")


@bot.command()
async def checkversion(ctx):
    try:
        await ctx.send("🔎 Checking Animal Company version...")
        version, source = get_best_version()
        artwork = get_meta_artwork()

        embed = make_embed(
            "🦍 Animal Company",
            "🔎 **Animal Company Version Check**",
            version,
            source,
            artwork
        )

        await ctx.send(embed=embed)

    except Exception as error:
        print(f"[COMMAND] checkversion error: {error}")
        await ctx.send(f"❌ Version check failed: `{error}`")


@bot.command()
async def checkstate(ctx):
    state = load_state()

    await ctx.send(
        "📊 **Update Checker State**\n"
        f"📦 Current: `{state.get('current_version', 'None')}`\n"
        f"⏳ Pending: `{state.get('pending_version', 'None')}`\n"
        f"🔢 Confirmations: "
        f"`{state.get('confirmations', 0)}/{REQUIRED_CONFIRMATIONS}`"
    )


@bot.command()
@commands.has_permissions(administrator=True)
async def testupdate(ctx):
    sent = await send_update(
        KNOWN_GOOD_VERSION,
        "1.91.2.9999",
        "TEST",
        test=True
    )

    await ctx.send(
        "✅ Test update announcement sent."
        if sent
        else "❌ Update channel not found."
    )


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You need administrator permissions to use that command.")
        return

    if isinstance(error, commands.CommandNotFound):
        return

    print(f"[COMMAND] Error: {error}")


@bot.event
async def on_ready():
    print("================================")
    print(" Animal Company Update Bot")
    print("================================")
    print(f"Logged in as: {bot.user}")
    print(f"Known version: {KNOWN_GOOD_VERSION}")
    print("Artwork: Meta")
    print("Version sources: Meta -> VRDB -> Quest Store DB")
    print("================================")

    if not update_checker.is_running():
        update_checker.start()
        print("[CHECKER] Started.")


if not TOKEN:
    raise RuntimeError(
        "DISCORD_TOKEN environment variable is missing."
    )

bot.run(TOKEN)
