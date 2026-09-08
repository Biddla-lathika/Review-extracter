
import os
from dotenv import load_dotenv
from browserbase import Browserbase
from playwright.sync_api import sync_playwright

load_dotenv()


def main():

    api_key = os.getenv("BROWSERBASE_API_KEY")

    if not api_key:
        raise Exception("BROWSERBASE_API_KEY is missing")

    bb = Browserbase(api_key=api_key)

    session = bb.sessions.create()

    print("Session ID:")
    print(session.id)

    print("\nBrowserbase session:")
    print(f"https://browserbase.com/sessions/{session.id}")

    with sync_playwright() as playwright:

        browser = playwright.chromium.connect_over_cdp(
            session.connect_url
        )

        context = browser.contexts[0]

        page = context.pages[0]

        page.goto(
            "https://www.google.com/maps",
            wait_until="domcontentloaded",
            timeout=60000
        )

        print("\nPage title:")
        print(page.title())

        print("\nCurrent URL:")
        print(page.url)

        browser.close()

    print("\nBrowser test completed.")


if __name__ == "__main__":
    main()