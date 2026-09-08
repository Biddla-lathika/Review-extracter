import os
import re
import time
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl

from browserbase import Browserbase
from playwright.sync_api import sync_playwright


app = FastAPI(
    title="Google Maps Review Scraper API",
    version="1.0.0"
)


class ReviewRequest(BaseModel):
    url: HttpUrl
    max_reviews: int = 500


def extract_reviews(page, max_reviews: int):

    reviews = {}

    no_new_rounds = 0
    previous_count = 0

    print("Looking for review cards...")

    for scroll_number in range(1, 3001):

        # Expand "More" buttons
        try:
            more_buttons = page.locator(
                'button:has-text("More")'
            )

            count = min(await_count(more_buttons), 30)

            for i in range(count):
                try:
                    more_buttons.nth(i).click(
                        timeout=1000
                    )
                except Exception:
                    pass

        except Exception:
            pass

        # Find review cards
        cards = page.locator(
            'div[data-review-id], div.jftiEf'
        )

        card_count = await_count(cards)

        for i in range(card_count):

            if len(reviews) >= max_reviews:
                break

            try:

                card = cards.nth(i)

                review_id = (
                    card.get_attribute("data-review-id")
                    or f"review-{i}-{scroll_number}"
                )

                # Reviewer name
                name = ""

                try:
                    name = card.locator(
                        "a.d4r55"
                    ).first.text_content(
                        timeout=1000
                    ) or ""
                except Exception:
                    pass

                # Rating
                rating = None

                try:
                    rating_element = card.locator(
                        'span.kvMYJc'
                    ).first

                    aria = rating_element.get_attribute(
                        "aria-label"
                    )

                    if aria:
                        match = re.search(
                            r"([0-5](?:\.[0-9])?)",
                            aria
                        )

                        if match:
                            rating = float(
                                match.group(1)
                            )

                except Exception:
                    pass

                # Review text
                text = ""

                try:
                    text = card.locator(
                        "span.wiI7pd"
                    ).first.text_content(
                        timeout=1000
                    ) or ""
                except Exception:
                    pass

                # Date
                date = ""

                try:
                    date = card.locator(
                        "span.rsqaWe"
                    ).first.text_content(
                        timeout=1000
                    ) or ""
                except Exception:
                    pass

                name = name.strip()
                text = text.strip()
                date = date.strip()

                # Only save actual review data
                if text or rating is not None:

                    reviews[review_id] = {
                        "review_id": review_id,
                        "reviewer": name,
                        "rating": rating,
                        "review_text": text,
                        "review_date": date,
                    }

            except Exception:
                continue

        current_count = len(reviews)

        print(
            f"Scroll {scroll_number}: "
            f"{current_count} reviews"
        )

        if current_count >= max_reviews:
            break

        if current_count == previous_count:
            no_new_rounds += 1
        else:
            no_new_rounds = 0

        previous_count = current_count

        if no_new_rounds >= 15:
            print(
                "No new reviews detected. "
                "Stopping."
            )
            break

        # Find scrollable containers
        try:

            scroll_result = page.evaluate(
                """
                () => {

                    const elements =
                        Array.from(document.querySelectorAll('*'));

                    const candidates = elements.filter(el => {

                        const style =
                            window.getComputedStyle(el);

                        return (
                            (style.overflowY === 'auto' ||
                             style.overflowY === 'scroll') &&
                            el.scrollHeight >
                            el.clientHeight + 100
                        );
                    });

                    if (!candidates.length) {
                        return false;
                    }

                    const target =
                        candidates
                        .sort(
                            (a, b) =>
                                b.scrollHeight -
                                a.scrollHeight
                        )[0];

                    target.scrollTop =
                        target.scrollHeight;

                    return true;
                }
                """
            )

            if not scroll_result:

                # Fallback
                page.mouse.wheel(
                    0,
                    5000
                )

        except Exception:

            page.mouse.wheel(
                0,
                5000
            )

        time.sleep(1.2)

    return list(reviews.values())


def await_count(locator):

    try:
        return locator.count()
    except Exception:
        return 0


def scrape_google_maps(
    url: str,
    max_reviews: int
):

    api_key = os.getenv(
        "BROWSERBASE_API_KEY"
    )

    if not api_key:
        raise Exception(
            "BROWSERBASE_API_KEY is not configured"
        )

    bb = Browserbase(
        api_key=api_key
    )

    session = bb.sessions.create()

    print(
        f"Browserbase session: {session.id}"
    )

    with sync_playwright() as playwright:

        browser = None

        try:

            browser = playwright.chromium.connect_over_cdp(
                session.connect_url
            )

            context = browser.contexts[0]

            page = (
                context.pages[0]
                if context.pages
                else context.new_page()
            )

            print(
                f"Opening: {url}"
            )

            page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=60000
            )

            page.wait_for_timeout(5000)

            # Try to click Reviews
            review_clicked = False

            selectors = [
                'button[aria-label*="Reviews"]',
                'button:has-text("Reviews")',
                '[role="button"]:has-text("Reviews")',
            ]

            for selector in selectors:

                try:

                    locator = page.locator(
                        selector
                    ).first

                    if locator.is_visible(
                        timeout=2000
                    ):

                        locator.click(
                            timeout=5000
                        )

                        review_clicked = True

                        print(
                            "Reviews button clicked."
                        )

                        break

                except Exception:
                    pass

            if not review_clicked:

                print(
                    "Could not explicitly click "
                    "Reviews button."
                )

            page.wait_for_timeout(3000)

            reviews = extract_reviews(
                page,
                max_reviews
            )

            return {
                "success": True,
                "session_id": session.id,
                "source_url": url,
                "review_count": len(reviews),
                "reviews": reviews
            }

        finally:

            if browser:

                try:
                    browser.close()
                except Exception:
                    pass


@app.get("/")
def home():

    return {
        "status": "ok",
        "service": "Google Maps Review Scraper",
        "message": "API is running"
    }


@app.get("/health")
def health():

    return {
        "status": "healthy"
    }


@app.post("/api/scrape-reviews")
def scrape_reviews(request: ReviewRequest):

    if request.max_reviews < 1:
        raise HTTPException(
            status_code=400,
            detail="max_reviews must be at least 1"
        )

    if request.max_reviews > 5000:
        raise HTTPException(
            status_code=400,
            detail="max_reviews cannot exceed 5000"
        )

    try:

        result = scrape_google_maps(
            str(request.url),
            request.max_reviews
        )

        return result

    except Exception as e:

        print(
            f"Scraping error: {e}"
        )

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )