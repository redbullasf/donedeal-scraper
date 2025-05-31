import discord
from discord.ext import commands, tasks
from playwright.async_api import async_playwright
import requests
import asyncio

TOKEN = "MTM3ODM5Njc5OTIxOTQwNDg4Mg.GI1rpz.3lfHNpoAlvXQAMr493KaETIvWN3pwIYlMqOHtw"
GUILD_ID = 1254120973096059021  # Replace with your server's guild ID
CHANNEL_NAME = "car-bargains-2"

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

tracked_searches = {}  # {user_id: [search_params_dicts]}

# --------------- HELPERS ---------------

async def get_session_cookies_and_csrf():
    async with async_playwright() as p:
        browser = await p.firefox.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto("https://www.donedeal.ie/")
        await page.wait_for_timeout(3000)

        cookies = await context.cookies()
        csrf_cookie = next((c for c in cookies if c['name'] == '__Host-next-auth.csrf-token'), None)
        csrf_token = csrf_cookie['value'].split('|')[0] if csrf_cookie else None

        session_cookies = {c['name']: c['value'] for c in cookies}
        await browser.close()
        return session_cookies, csrf_token

def get_price_year_mileage(ad):
    price = ad.get('priceInfo', {}).get('price', 'N/A')
    meta = ad.get('metaInfo', [])
    year = next((x for x in meta if x.isdigit() and len(x) == 4), 'N/A')
    mileage = next((x for x in meta if 'km' in x.lower() or 'mi' in x.lower()), 'N/A')
    return price, year, mileage

def search_donedeal(cookies, csrf_token, params):
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": "https://www.donedeal.ie",
        "Referer": "https://www.donedeal.ie/cars",
        "Brand": "donedeal",
        "Platform": "web",
        "Version": "2025.5.29-143006.production"
    }

    payload = {
        "filters": [
            {"name": "country", "values": ["Ireland"]},
            {"name": "sellerType", "values": params.get("seller_types", ["pro", "private"])}
        ],
        "andFilters": [],
        "ranges": [
            {"name": "price", "from": params["price_from"], "to": params["price_to"]},
            {"name": "year", "from": params["year_from"], "to": params["year_to"]},
            {"name": "mileage", "from": params["mileage_from"], "to": params["mileage_to"]}
        ],
        "paging": {"pageSize": 5, "from": 0},
        "sections": ["cars"],
        "makeModelFilters": [
            {"make": params["make"], "model": params["model"], "trim": ""}
        ]
    }

    response = requests.post("https://www.donedeal.ie/ddapi/v2/search", headers=headers, cookies=cookies, json=payload)

    results = []
    if response.status_code == 200:
        ads = response.json().get("ads", [])
        for ad in ads:
            title = ad.get("title", "No title")
            url = ad.get("friendlyUrl", "https://www.donedeal.ie/")
            price, year, mileage = get_price_year_mileage(ad)

            embed = discord.Embed(title=title, url=url, color=0x00ff00)
            embed.add_field(name="Price", value=f"€{price}", inline=True)
            embed.add_field(name="Year", value=year, inline=True)
            embed.add_field(name="Mileage", value=f"{mileage}", inline=True)
            results.append(embed)
    return results

# --------------- COMMANDS ---------------

@bot.command()
async def donedeal(ctx):
    def check(m): return m.author == ctx.author and m.channel == ctx.channel

    await ctx.send("What car make? (e.g., Audi)")
    make = (await bot.wait_for("message", check=check)).content

    await ctx.send("What model? (e.g., A4)")
    model = (await bot.wait_for("message", check=check)).content

    await ctx.send("Price from?")
    price_from = (await bot.wait_for("message", check=check)).content

    await ctx.send("Price to?")
    price_to = (await bot.wait_for("message", check=check)).content

    await ctx.send("Year from?")
    year_from = (await bot.wait_for("message", check=check)).content

    await ctx.send("Year to?")
    year_to = (await bot.wait_for("message", check=check)).content

    await ctx.send("Mileage from?")
    mileage_from = (await bot.wait_for("message", check=check)).content

    await ctx.send("Mileage to?")
    mileage_to = (await bot.wait_for("message", check=check)).content

    await ctx.send("Seller type? (pro/private/both)")
    seller_type = (await bot.wait_for("message", check=check)).content.strip().lower()
    if seller_type == "pro":
        seller_types = ["pro"]
    elif seller_type == "private":
        seller_types = ["private"]
    else:
        seller_types = ["pro", "private"]

    params = {
        "make": make,
        "model": model,
        "price_from": price_from,
        "price_to": price_to,
        "year_from": year_from,
        "year_to": year_to,
        "mileage_from": mileage_from,
        "mileage_to": mileage_to,
        "seller_types": seller_types
    }

    user_id = str(ctx.author.id)
    if user_id not in tracked_searches:
        tracked_searches[user_id] = []
    tracked_searches[user_id].append(params)

    cookies, csrf = await get_session_cookies_and_csrf()
    initial_results = search_donedeal(cookies, csrf, params)
    if initial_results:
        for embed in initial_results:
            await ctx.send(embed=embed)
    else:
        await ctx.send("❌ No results found.")

    await ctx.send("🔍 Now tracking that search. You'll get alerts in #car-bargains-2!")

@bot.command()
async def list(ctx):
    user_id = str(ctx.author.id)
    if user_id in tracked_searches:
        listings = tracked_searches[user_id]
        msg = "\n".join([f"{i+1}. {entry['make']} {entry['model']} {entry['year_from']}-{entry['year_to']} €{entry['price_from']}-{entry['price_to']}" for i, entry in enumerate(listings)])
        await ctx.send(f"📋 Your tracked searches:\n{msg}")
    else:
        await ctx.send("ℹ️ You aren't tracking any searches.")

@bot.command()
async def cancel(ctx):
    user_id = str(ctx.author.id)
    if user_id in tracked_searches:
        tracked_searches.pop(user_id)
        await ctx.send("✅ All your tracked searches have been removed.")
    else:
        await ctx.send("ℹ️ You have no active tracked searches.")

# --------------- PERIODIC ALERTS ---------------

@tasks.loop(minutes=30)
async def check_all_searches():
    cookies, csrf = await get_session_cookies_and_csrf()
    channel = discord.utils.get(bot.get_all_channels(), name=CHANNEL_NAME)
    if not channel:
        return

    for user_id, searches in tracked_searches.items():
        for params in searches:
            results = search_donedeal(cookies, csrf, params)
            for embed in results:
                await channel.send(f"<@{user_id}>", embed=embed)

@bot.event
async def on_ready():
    print(f"Bot is ready. Logged in as {bot.user}")
    check_all_searches.start()

bot.run(TOKEN)
