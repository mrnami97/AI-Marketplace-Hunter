from pathlib import Path

from playwright.sync_api import sync_playwright


PROJECT_ROOT = Path(__file__).resolve().parent
PROFILE_DIR = PROJECT_ROOT / "facebook-profile"


def main() -> None:
    PROFILE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    with sync_playwright() as playwright:
        context = (
            playwright.chromium
            .launch_persistent_context(
                user_data_dir=str(PROFILE_DIR),
                channel="chrome",
                headless=False,
                viewport={
                    "width": 1400,
                    "height": 900,
                },
                locale="en-MY",
                timezone_id="Asia/Kuala_Lumpur",
            )
        )

        page = (
            context.pages[0]
            if context.pages
            else context.new_page()
        )

        page.goto(
            (
                "https://www.facebook.com/"
                "marketplace/kotakinabalu/"
            ),
            wait_until="commit",
            timeout=60_000,
        )

        print()
        print("Log in to Facebook manually.")
        print(
            "Confirm Marketplace opens, "
            "then return here."
        )
        print()

        input(
            "Press Enter to save the login "
            "session and close Chrome..."
        )

        context.close()


if __name__ == "__main__":
    main()
