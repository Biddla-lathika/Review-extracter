def extract_reviews(page, max_reviews: int):
    """Collect Google Maps reviews by scrolling the reviews panel."""
    reviews = {}
    stable_rounds = 0
    previous_count = 0

    # Google Maps commonly uses this class for the reviews panel.
    scroll_container = page.locator("div.m6QErb").last

    if not scroll_container.count():
        print("Reviews scroll container not found.")
        return []

    for scroll_number in range(1, 2001):

        # Expand visible More buttons.
        try:
            more_buttons = page.locator(
                'button:has-text("More")'
            )

            for i in range(min(more_buttons.count(), 50)):
                try:
                    more_buttons.nth(i).click(timeout=800)
                except Exception:
                    pass

        except Exception:
            pass

        # Google Maps review cards.
        review_cards = page.locator(
            'div[data-review-id], div.jftiEf'
        )

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
                            'span[role="img"]'
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

        # Scroll the actual reviews container.
        try:
            did_scroll = scroll_container.evaluate("""
                el => {
                    const before = el.scrollTop;

                    el.scrollTop = Math.min(
                        el.scrollTop +
                        Math.max(700, el.clientHeight * 0.85),
                        el.scrollHeight
                    );

                    el.dispatchEvent(
                        new Event("scroll", {bubbles: true})
                    );

                    return el.scrollTop > before;
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
            print("Reached the end of the reviews list.")
            break

    return list(reviews.values())