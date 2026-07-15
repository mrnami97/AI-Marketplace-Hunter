import asyncio

from crawler.facebook import (
    search_facebook_marketplace,
)


async def main() -> None:
    listings = await search_facebook_marketplace(
        query="RTX 3070",
        max_price=1200,
        max_results=10,
    )

    print()
    print(
        f"Found {len(listings)} Facebook Marketplace listings."
    )

    for number, listing in enumerate(
        listings,
        start=1,
    ):
        print()
        print(f"#{number}")
        print(f"Title: {listing.title}")
        print(f"Price: {listing.price}")
        print(f"Location: {listing.location}")
        print(f"URL: {listing.url}")


if __name__ == "__main__":
    asyncio.run(main())
