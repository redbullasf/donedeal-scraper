from playwright.sync_api import sync_playwright
import requests

def get_session_cookies_and_csrf():
    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://www.donedeal.ie/")
        page.wait_for_timeout(3000)  # Allow scripts to run and cookies to set

        cookies = context.cookies()
        csrf_cookie = next((c for c in cookies if c['name'] == '__Host-next-auth.csrf-token'), None)
        csrf_token = csrf_cookie['value'].split('|')[0] if csrf_cookie else None

        session_cookies = {c['name']: c['value'] for c in cookies}
        browser.close()
        return session_cookies, csrf_token

def search_donedeal(cookies, csrf_token):
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
            {"name": "sellerType", "values": ["pro"]}
        ],
        "andFilters": [],
        "ranges": [
            {"name": "price", "from": "7000", "to": "17500"},
            {"name": "year", "from": "2013", "to": "2025"},
            {"name": "mileage", "from": "20000", "to": "180000"}
        ],
        "paging": {"pageSize": 30, "from": 0},
        "sections": ["cars"],
        "makeModelFilters": [
            {"make": "BMW", "model": "3-Series", "trim": ""}
        ]
    }

    response = requests.post(
        "https://www.donedeal.ie/ddapi/v2/search",
        headers=headers,
        cookies=cookies,
        json=payload
    )

    if response.status_code == 200:
        ads = response.json().get("ads", [])
        for ad in ads:
            print(f"{ad.get('title')} - €{ad.get('price')} - {ad.get('year')} - {ad.get('mileage')}km")
            print(f"https://www.donedeal.ie/cars-for-sale/{ad.get('friendlyUrl')}\n")
    else:
        print(f"Search failed: {response.status_code} - {response.text}")

# Run everything
cookies, csrf = get_session_cookies_and_csrf()
search_donedeal(cookies, csrf)

input("\n[✓] Done! Press Enter to exit...")