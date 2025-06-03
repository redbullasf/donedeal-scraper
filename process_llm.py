import argparse
import csv
import json
import urllib.request


def call_llm(url: str, prompt: str) -> str:
    data = json.dumps({"prompt": prompt}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        try:
            result = json.load(resp)
        except Exception:
            result = {}
    return result.get("result", "")


def main() -> None:
    parser = argparse.ArgumentParser(description="Process scraped car data with a local LLM")
    parser.add_argument("csv", help="Cleaned CSV file from scraper")
    parser.add_argument("--url", default="http://localhost:8000/generate", help="Local LLM endpoint")
    parser.add_argument("--out", default="llm_results.json", help="Output JSON file")
    args = parser.parse_args()

    results = []
    with open(args.csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            prompt = (
                f"{row['Year']} {row['Brand']} {row['Mileage (km)']} km "
                f"{row['Price (€)']} euro in {row['Town']} {row['County']}"
            )
            row["llm_response"] = call_llm(args.url, prompt)
            results.append(row)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
