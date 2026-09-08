import os
import re
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
    """Collect reviews by scrolling the Google Maps reviews dialog."""
    reviews = {}
    stable_rounds = 0
    previous_count = 0

    dialog = page.locator('div[role="dialog"]').last
    review_cards = dialog.locator(
        'div[data-review-id], div.jftiEf'
    )

    for scroll_number in range(1, 2001):

        # Expand visible "More" buttons.
        try:
            more_buttons = dialog.locator(
                'button:has-text("More")'
            )

            for i in range(min(more_buttons.count(), 50)):
                try:
                    more_buttons.nth(i).click(timeout=800)
                except Exception:
                    pass

        except Exception:
            pass

        card_count = review_cards.count()

        for i in range(card_count):

            if len(reviews) >= max_reviews:
                break

            try:
                card = review_cards.nth(i)

                review_id = card.get_attribute(
                    "data-review-id"
                )

                if not review_id:
                    review_id = f"fallback-{i}-{card_count}"

                # Reviewer name
                name = ""

                for selector in [
                    "a.d4r55",
                    "div.d4r55"
                ]:
                    try:
                        name = (
                            card.locator(selector)
                            .first
                            .text_content(timeout=800)
                            or ""
                        ).strip()

                        if name:
                            break

                    except Exception:
                        pass

                # Rating
                rating = None

                try:
                    aria = (
                        card.locator(
                            'span.kvMYJc, span[role="img"]'
                        )
                        .first
                        .get_attribute("aria-label")
                    )

                    if aria:
                        match = re.search(
                            r"([0-5](?:[.,][0-9])?)",
                            aria
                        )

                        if match:
                            rating = float(
                                match.group(1).replace(",", ".")
                            )

                except Exception:
                    pass

                # Review text
                text = ""

                for selector in [
                    "span.wiI7pd",
                    "div.MyEned"
                ]:
                    try:
                        text = (
                            card.locator(selector)
                            .first
                            .text_content(timeout=800)
                            or ""
                        ).strip()

                        if text:
                            break

                    except Exception:
                        pass

                # Review date
                date = ""

                try:
                    date = (
                        card.locator("span.rsqaWe")
                        .first
                        .text_content(timeout=800)
                        or ""
                    ).strip()

                except Exception:
                    pass

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

        # Scroll the reviews container.
        try:
            did_scroll = dialog.evaluate("""
                dialog => {
                    const all = [
                        dialog,
                        ...dialog.querySelectorAll('*')
                    ];

                    const candidates = all.filter(el => {
                        const s = getComputedStyle(el);

                        return /(auto|scroll)/.test(s.overflowY) &&
                               el.scrollHeight > el.clientHeight + 20;
                    });

                    const target = candidates.sort(
                        (a, b) =>
                            b.scrollHeight - a.scrollHeight
                    )[0];

                    if (!target) return false;

                    const before = target.scrollTop;

                    target.scrollTop = Math.min(
                        target.scrollTop +
                        Math.max(700, target.clientHeight * 0.85),
                        target.scrollHeight
                    );

                    target.dispatchEvent(
                        new Event("scroll", {bubbles: true})
                    );

                    return target.scrollTop > before;
                }
            """)

        except Exception:
            did_scroll = False

        page.wait_for_timeout(1800)

        if current_count == previous_count:
            stable_rounds += 1
        else:
            stable_rounds = 0

        previous_count = current_count

        if stable_rounds >= 12:
            print(
                "Reached the end of the reviews list."
            )
            break

    return list(reviews.values())


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

            # Try to click Reviews.
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


@app.post("/scrape-reviews")
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