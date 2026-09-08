import time
import re
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


# ============================================================
# CONFIGURATION
# ============================================================

HEADLESS = False

PAGE_TIMEOUT = 60000
WAIT_AFTER_OPEN = 5

SCROLL_WAIT = 2
MAX_SCROLLS = 2000
NO_NEW_LIMIT = 8

# Maximum number of review blocks returned by this step.
# Set to None if you don't want a limit.
MAX_REVIEWS = None


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def clean_text(text):
    """Clean unnecessary whitespace."""
    if not text:
        return ""

    text = re.sub(r"\s+", " ", text)
    return text.strip()


def find_reviews_button(page):
    """
    Try several selectors because Google Maps can change
    its HTML structure.
    """

    selectors = [
        'button[aria-label*="Reviews"]',
        'button[aria-label*="reviews"]',
        'button:has-text("Reviews")',
        '[role="button"]:has-text("Reviews")',
        'text=Reviews'
    ]

    for selector in selectors:
        try:
            locator = page.locator(selector)

            count = locator.count()

            for i in range(min(count, 10)):
                element = locator.nth(i)

                try:
                    if element.is_visible():
                        print("Reviews button found:", selector)
                        return element
                except Exception:
                    continue

        except Exception:
            continue

    return None


def find_review_cards(page):
    """
    Find currently loaded review cards.
    Google Maps DOM selectors can change, so several
    selectors are tried.
    """

    selectors = [
        'div.jftiEf',
        'div[data-review-id]',
        'div[jsaction*="review"]'
    ]

    for selector in selectors:
        try:
            cards = page.locator(selector)

            if cards.count() > 0:
                return cards

        except Exception:
            continue

    return None


def get_card_text(card):
    """Extract all visible text from a review card."""

    try:
        return clean_text(card.inner_text())
    except Exception:
        return ""


def expand_more_buttons(page):
    """
    Expand visible 'More' / 'See more' buttons inside
    review cards.
    """

    selectors = [
        'button:has-text("More")',
        'button:has-text("See more")',
        'text=More',
        'text=See more'
    ]

    expanded = 0

    for selector in selectors:
        try:
            buttons = page.locator(selector)

            count = buttons.count()

            for i in range(min(count, 100)):
                try:
                    button = buttons.nth(i)

                    if button.is_visible():
                        button.click(timeout=1000)
                        expanded += 1
                        time.sleep(0.2)

                except Exception:
                    continue

        except Exception:
            continue

    return expanded


def find_scroll_container(page):
    """
    Locate the internal scrollable container used by
    Google Maps reviews.

    We first check known Google Maps selectors.
    Then we use JavaScript to search for an element whose
    scrollHeight is larger than its clientHeight.
    """

    known_selectors = [
        'div.m6QErb',
        'div[role="main"]',
        'div[role="region"]'
    ]

    # --------------------------------------------------------
    # Try known selectors first
    # --------------------------------------------------------

    for selector in known_selectors:

        try:
            elements = page.locator(selector)

            count = elements.count()

            for i in range(count):

                try:
                    element = elements.nth(i)

                    if not element.is_visible():
                        continue

                    is_scrollable = element.evaluate(
                        """
                        el => {
                            return el.scrollHeight >
                                   el.clientHeight + 100;
                        }
                        """
                    )

                    if is_scrollable:
                        print(
                            "Scrollable container found:",
                            selector
                        )

                        return element

                except Exception:
                    continue

        except Exception:
            continue

    # --------------------------------------------------------
    # Generic JavaScript search
    # --------------------------------------------------------

    try:

        handle = page.evaluate_handle(
            """
            () => {

                const elements =
                    Array.from(document.querySelectorAll('*'));

                for (const el of elements) {

                    const style =
                        window.getComputedStyle(el);

                    const overflowY =
                        style.overflowY;

                    const scrollable =
                        el.scrollHeight >
                        el.clientHeight + 150;

                    const correctOverflow =
                        overflowY === 'auto' ||
                        overflowY === 'scroll';

                    if (scrollable && correctOverflow) {
                        return el;
                    }
                }

                return null;
            }
            """
        )

        element = handle.as_element()

        if element:
            print("Scrollable container found using JavaScript.")
            return element

    except Exception as e:
        print("JavaScript container search failed:", e)

    return None


def scroll_container(container):
    """
    Scroll the review container downward.
    """

    try:

        container.evaluate(
            """
            el => {
                el.scrollTop =
                    el.scrollTop +
                    Math.floor(el.clientHeight * 0.85);
            }
            """
        )

        return True

    except Exception as e:
        print("Container scroll error:", e)
        return False


def collect_visible_reviews(page):
    """
    Collect currently visible review blocks.

    We return raw text at this stage.
    AI extraction happens later.
    """

    reviews = []

    cards = find_review_cards(page)

    if not cards:
        return reviews

    try:
        count = cards.count()
    except Exception:
        return reviews

    for i in range(count):

        try:

            card = cards.nth(i)

            if not card.is_visible():
                continue

            text = get_card_text(card)

            if not text:
                continue

            # Try to get Google review ID.
            review_id = ""

            try:
                review_id = card.get_attribute(
                    "data-review-id"
                ) or ""
            except Exception:
                pass

            reviews.append({
                "review_id": review_id,
                "raw_text": text
            })

        except Exception:
            continue

    return reviews


# ============================================================
# MAIN SCRAPER
# ============================================================

def scrape_reviews(url):
    """
    Main browser automation function.

    Flow:

    URL
      ↓
    Open Google Maps
      ↓
    Find Reviews
      ↓
    Click Reviews
      ↓
    Find review container
      ↓
    Scroll
      ↓
    Collect review blocks
    """

    if not url:
        raise ValueError("Google Maps URL is required.")

    all_reviews = []

    # Fingerprints prevent collecting the same visible
    # review repeatedly while scrolling.
    seen = set()

    with sync_playwright() as p:

        print("\nStarting Chromium...")

        browser = p.chromium.launch(
            headless=HEADLESS
        )

        context = browser.new_context(
            viewport={
                "width": 1400,
                "height": 900
            },
            locale="en-US"
        )

        page = context.new_page()

        page.set_default_timeout(PAGE_TIMEOUT)

        # ----------------------------------------------------
        # STEP 1: OPEN URL
        # ----------------------------------------------------

        print("\nOpening Google Maps URL:")
        print(url)

        try:
            page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=PAGE_TIMEOUT
            )
        except PlaywrightTimeoutError:
            print(
                "Page load timeout occurred, "
                "but continuing..."
            )

        time.sleep(WAIT_AFTER_OPEN)

        print("\nPage title:")
        print(page.title())

        print("\nCurrent URL:")
        print(page.url)

        # ----------------------------------------------------
        # STEP 2: FIND REVIEWS BUTTON
        # ----------------------------------------------------

        print("\nSearching for Reviews button...")

        reviews_button = find_reviews_button(page)

        if not reviews_button:

            print(
                "\nERROR: Reviews button was not found."
            )

            print(
                "Current page URL:",
                page.url
            )

            browser.close()

            return {
                "success": False,
                "message": "Reviews button not found.",
                "reviews": []
            }

        # ----------------------------------------------------
        # STEP 3: CLICK REVIEWS
        # ----------------------------------------------------

        print("\nClicking Reviews...")

        try:

            reviews_button.click(
                timeout=10000
            )

        except Exception as e:

            print(
                "Normal click failed:",
                e
            )

            try:

                reviews_button.click(
                    force=True,
                    timeout=10000
                )

            except Exception as e2:

                print(
                    "Forced click failed:",
                    e2
                )

                browser.close()

                return {
                    "success": False,
                    "message": "Could not click Reviews.",
                    "reviews": []
                }

        time.sleep(4)

        # ----------------------------------------------------
        # STEP 4: FIND REVIEW CONTAINER
        # ----------------------------------------------------

        print("\nSearching for review scroll container...")

        container = find_scroll_container(page)

        if not container:

            print(
                "\nERROR: Review scroll container "
                "was not found."
            )

            browser.close()

            return {
                "success": False,
                "message": "Review scroll container not found.",
                "reviews": []
            }

        # ----------------------------------------------------
        # STEP 5: COLLECT INITIAL REVIEWS
        # ----------------------------------------------------

        print("\nCollecting initial review blocks...")

        initial_reviews = collect_visible_reviews(page)

        for review in initial_reviews:

            review_id = review["review_id"]
            raw_text = review["raw_text"]

            fingerprint = (
                review_id
                if review_id
                else raw_text
            )

            if fingerprint not in seen:

                seen.add(fingerprint)

                all_reviews.append(review)

        print(
            "Initial reviews:",
            len(all_reviews)
        )

        # ----------------------------------------------------
        # STEP 6: SCROLL + COLLECT
        # ----------------------------------------------------

        no_new_count = 0

        previous_count = len(all_reviews)

        for scroll_number in range(1, MAX_SCROLLS + 1):

            print(
                f"\nScroll {scroll_number}/{MAX_SCROLLS}"
            )

            # Expand visible review text.
            expanded = expand_more_buttons(page)

            if expanded:
                print(
                    "Expanded review text:",
                    expanded
                )

            # Scroll the actual review container.
            success = scroll_container(container)

            if not success:
                print("Could not scroll container.")
                break

            time.sleep(SCROLL_WAIT)

            # Collect newly visible review blocks.
            visible_reviews = collect_visible_reviews(page)

            new_reviews = 0

            for review in visible_reviews:

                review_id = review["review_id"]
                raw_text = review["raw_text"]

                fingerprint = (
                    review_id
                    if review_id
                    else raw_text
                )

                if fingerprint in seen:
                    continue

                seen.add(fingerprint)

                all_reviews.append(review)

                new_reviews += 1

                if (
                    MAX_REVIEWS is not None
                    and len(all_reviews) >= MAX_REVIEWS
                ):
                    break

            print(
                "New reviews:",
                new_reviews
            )

            print(
                "Total unique review blocks:",
                len(all_reviews)
            )

            # ------------------------------------------------
            # MAX REVIEW CHECK
            # ------------------------------------------------

            if (
                MAX_REVIEWS is not None
                and len(all_reviews) >= MAX_REVIEWS
            ):

                print(
                    "\nMaximum review limit reached."
                )

                break

            # ------------------------------------------------
            # NO NEW REVIEW CHECK
            # ------------------------------------------------

            if len(all_reviews) == previous_count:

                no_new_count += 1

                print(
                    "No new reviews count:",
                    no_new_count,
                    "/",
                    NO_NEW_LIMIT
                )

            else:

                no_new_count = 0

            previous_count = len(all_reviews)

            # ------------------------------------------------
            # STOP CONDITION
            # ------------------------------------------------

            if no_new_count >= NO_NEW_LIMIT:

                print(
                    "\nNo new reviews found after "
                    f"{NO_NEW_LIMIT} consecutive scrolls."
                )

                break

        # ----------------------------------------------------
        # FINAL EXPANSION
        # ----------------------------------------------------

        print("\nFinal review text expansion...")

        expand_more_buttons(page)

        # ----------------------------------------------------
        # FINAL RESULT
        # ----------------------------------------------------

        print(
            "\n======================================"
        )

        print(
            "TOTAL UNIQUE REVIEW BLOCKS:",
            len(all_reviews)
        )

        print(
            "======================================"
        )

        browser.close()

        return {
            "success": True,
            "message": "Review collection completed.",
            "total_reviews": len(all_reviews),
            "reviews": all_reviews
        }


# ============================================================
# LOCAL TEST
# ============================================================

if __name__ == "__main__":

    test_url = input(
        "\nEnter Google Maps business URL: "
    ).strip()

    result = scrape_reviews(test_url)

    print("\nRESULT:")
    print(
        "Success:",
        result.get("success")
    )

    print(
        "Total reviews:",
        result.get("total_reviews")
    )

    if result.get("reviews"):

        print("\nFirst 5 review blocks:\n")

        for i, review in enumerate(
            result["reviews"][:5],
            start=1
        ):

            print(
                f"--- REVIEW {i} ---"
            )

            print(
                review["raw_text"]
            )

            print()