import time
import re
import json
import csv
import argparse
import logging
import requests
from pathlib import Path

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException, NoSuchWindowException

CURRENT_YEAR = 2025
# Discord webhook URL hardcoded
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1378065115919814758/2eg0ewmeVJIFpEbln5xRnFKJgWW4313CFKD1TDBSDyy0oRA4uof8PrFJxavNf_QvLEUt"

def parse_ad(ad):
    """
    Extracts Title, Brand, Year, Fuel, Mileage, and Price from one ad dict.
    """
    title = (ad.get("title") or "").strip()
    brand = title.split()[0] if title else ""

    year = None
    for m in re.finditer(r"\b(19\d{2}|20\d{2})\b", title):
        y = int(m.group(0))
        if 1900 <= y <= CURRENT_YEAR:
            year = y
            break

    price_str = (ad.get("priceInfo", {}).get("price") or "")
    try:
        price = float(re.sub(r"[^\d.]", "", price_str))
    except (ValueError, TypeError):
        price = 0.0

    fuel = ""
    mileage = None
    for mi in ad.get("metaInfo", []) or []:
        if not isinstance(mi, str):
            continue
        if any(ft in mi for ft in ("Diesel", "Petrol", "Electric", "Hybrid")):
            fuel = mi
        if "km" in mi.lower():
            num = re.sub(r"[^\d]", "", mi)
            try:
                mileage = int(num)
            except ValueError:
                mileage = None

    return {
        "Title": title,
        "Brand": brand,
        "Year": year or 0,
        "Fuel": fuel,
        "Mileage (km)": mileage or 0,
        "Price (€)": price,
    }

def fetch_ads(driver, url, wait_timeout=15):
    logging.info(f"Fetching: {url}")
    try:
        driver.get(url)
        WebDriverWait(driver, wait_timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "script#__NEXT_DATA__"))
        )
    except (WebDriverException, NoSuchWindowException) as e:
        logging.error(f"Failed to load page {url}: {e}")
        return []
    html = driver.page_source
    m = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        logging.warning("__NEXT_DATA__ not found; skipping page.")
        return []
    data = json.loads(m.group(1))
    return data.get("props", {}).get("pageProps", {}).get("ads", []) or []

def send_discord(bargains, high_bargains, top_list):
    content = ["**🔔 New DoneDeal Car Scraper Update**"]
    if high_bargains:
        content.append("**🟢 High-Level Bargains:**")
        for c in high_bargains:
            content.append(f"{c['Year']} {c['Brand']} - {c['Mileage (km)']} km - €{c['Price (€)']:.0f}")
    if bargains:
        content.append("**🔵 General Bargains:**")
        for c in bargains:
            content.append(f"{c['Year']} {c['Brand']} - {c['Mileage (km)']} km - €{c['Price (€)']:.0f}")
    content.append("**⭐ Top 10 Listings (by Price):**")
    for c in top_list:
        content.append(f"{c['Year']} {c['Brand']} - {c['Mileage (km)']} km - €{c['Price (€)']:.0f}")

    payload = {"content": "\n".join(content)}
    try:
        resp = requests.post(DISCORD_WEBHOOK_URL, json=payload)
        resp.raise_for_status()
        logging.info("Discord notification sent successfully.")
    except Exception as e:
        logging.error(f"Failed to send Discord notification: {e}")

def main():
    parser = argparse.ArgumentParser(description="Scrape diesel car bargains and notify Discord.")
    parser.add_argument("--min-price", type=int, default=6000, help="Minimum price (€) to include (default: 6000)")
    parser.add_argument("--bargain-price", type=int, default=14000, help="Max price (€) to flag as bargain (default: 14000)")
    parser.add_argument("--max-mileage", type=int, default=100000, help="Max mileage (km) for bargains (default: 100000)")
    parser.add_argument("--min-year", type=int, default=2017, help="Min year for bargains (default: 2017)")
    parser.add_argument("--high-price", type=int, default=13000, help="Max price (€) for high-level bargains (default: 13000)")
    parser.add_argument("--high-mileage", type=int, default=80000, help="Max mileage (km) for high-level bargains (default: 80000)")
    parser.add_argument("--high-year", type=int, default=2018, help="Min year for high-level bargains (default: 2018)")
    parser.add_argument("--pages", type=int, default=3, help="Number of pages to scrape (default: 3)")
    parser.add_argument("--output", default="diesel_bargains.csv", help="Output CSV filename")
    parser.add_argument("--headless", action="store_true", help="Run Chrome in headless mode")
    args = parser.parse_args()

    logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)

    options = uc.ChromeOptions()
    if args.headless:
        options.headless = True
    driver = uc.Chrome(options=options)

    try:
        all_ads = []
        base_url = "https://www.donedeal.ie/cars"
        for page in range(1, args.pages + 1):
            url = base_url + (f"?page={page}" if page > 1 else "")
            ads = fetch_ads(driver, url)
            if not ads:
                break
            all_ads.extend(ads)
            time.sleep(1)
        logging.info(f"Fetched {len(all_ads)} raw ads.")

        cars = [parse_ad(ad) for ad in all_ads]
        seen = set()
        unique = []
        for car in cars:
            key = (car["Title"], car["Year"], car["Mileage (km)"], car["Price (€)"])
            if key not in seen:
                seen.add(key)
                unique.append(car)
        logging.info(f"{len(unique)} unique ads after dedupe.")

        bargains, high_bargains = [], []
        for c in unique:
            if (c["Fuel"].startswith("Diesel") and
                args.min_price <= c["Price (€)"] <= args.bargain_price and
                c["Mileage (km)"] <= args.max_mileage and
                c["Year"] >= args.min_year):
                bargains.append(c)
                if (c["Price (€)"] <= args.high_price and
                    c["Mileage (km)"] <= args.high_mileage and
                    c["Year"] >= args.high_year):
                    high_bargains.append(c)
        logging.info(f"{len(bargains)} bargains; {len(high_bargains)} high-level bargains.")

        top_list = sorted(unique, key=lambda x: x["Price (€)"])[:10]

        # Console output
        print("🟢 High-Level Bargains:")
        for i, car in enumerate(high_bargains, 1):
            print(f"{i}. {car['Year']} {car['Brand']} — {car['Mileage (km)']} km — €{car['Price (€)']:.0f}")
        print("\n🔵 General Bargains:")
        for i, car in enumerate(bargains, 1):
            print(f"{i}. {car['Year']} {car['Brand']} — {car['Mileage (km)']} km — €{car['Price (€)']:.0f}")
        print("\n⭐ Top 10 Listings (by Price):")
        for i, car in enumerate(top_list, 1):
            print(f"{i}. {car['Year']} {car['Brand']} — {car['Mileage (km)']} km — €{car['Price (€)']:.0f}")

        # Write CSV
        with open(args.output, "w", newline="", encoding="utf-8") as f:
            fieldnames = ["Title", "Brand", "Year", "Fuel", "Mileage (km)", "Price (€)", "Category"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for c in unique:
                if c in high_bargains:
                    cat = "High-Level"
                elif c in bargains:
                    cat = "General"
                else:
                    continue
                row = c.copy()
                row["Category"] = cat
                writer.writerow(row)
        logging.info(f"Wrote {len(bargains)} bargain records to {args.output}")

        # Notify Discord
        send_discord(bargains, high_bargains, top_list)

    finally:
        driver.quit()

if __name__ == "__main__":
    main()