"""
Diagnostic script: scrape SACI clipping with all names from nomes.csv
and print which names matched which articles. Run with:

    uv run python scripts/diagnose_matches.py
"""
import asyncio
import csv
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.scraper import build_name_variants, scrape_news
from app.core.settings import settings

NAMES_FILE = Path(__file__).parent.parent / "assets" / "nomes.csv"
SOURCE_URL = "https://www.ccs.ufscar.br/clipping"


def load_names(path: Path) -> list[str]:
    names = []
    with path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames and any(
            h.strip().lower() in ("nome", "name") for h in reader.fieldnames
        ):
            col = next(
                h for h in reader.fieldnames
                if h.strip().lower() in ("nome", "name")
            )
            for row in reader:
                val = (row.get(col) or "").strip()
                if val:
                    names.append(val)
        else:
            f.seek(0)
            for line in f:
                line = line.strip()
                if line:
                    names.append(line)
    return names


async def main() -> None:
    names = load_names(NAMES_FILE)
    print(f"Loaded {len(names)} names from {NAMES_FILE.name}")
    print()
    print("Name variants (showing potential matches):")
    print("-" * 60)
    for name in names:
        variants = sorted(build_name_variants(name))
        print(f"  {name}: {variants}")
    print()
    print("=" * 60)
    print(f"Scraping {SOURCE_URL} ...")
    print(f"Settings: timeout={settings.request_timeout}s, "
          f"delay={settings.request_delay_seconds}s, "
          f"max_article_fetches={settings.max_article_fetches}, "
          f"max_listing_pages={settings.max_listing_pages}")
    print("=" * 60)
    print()

    items = await scrape_news(
        names=names,
        source_url=SOURCE_URL,
        limit=200,
        timeout=settings.request_timeout,
        request_delay_seconds=settings.request_delay_seconds,
        max_article_fetches=settings.max_article_fetches,
        max_listing_pages=settings.max_listing_pages,
    )

    if not items:
        print("No matching news items found.")
        return

    print(f"Found {len(items)} news items:")
    print()

    # Group by matched names
    by_person: dict[str, list] = {}
    for item in items:
        for matched_name in item.matched_names:
            by_person.setdefault(matched_name, []).append(item)

    for person_name in sorted(by_person.keys()):
        person_items = by_person[person_name]
        print(f"[{person_name}] → {len(person_items)} article(s)")
        for art in person_items:
            print(f"    - {art.title}")
            print(f"      {art.url}")
        print()

    no_match = [n for n in names if n not in by_person]
    if no_match:
        print(f"Names with NO matches ({len(no_match)}):")
        for n in no_match:
            print(f"  - {n}")


if __name__ == "__main__":
    asyncio.run(main())
