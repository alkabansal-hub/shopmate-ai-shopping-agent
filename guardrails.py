"""ShopMate's code guardrails (PRD section 8).

GR-04  is_off_topic             runs before the agent; off-topic messages and photos never reach it.
GR-01  is_clear_confirmation    decides whether the shopper's latest message unlocks one checkout.
GR-03  find_unverified_products checks every product line in a reply against the store data.
"""

import base64
import re

from groq import APIError

import tools
from initial_setup.reviews_api import get_ratings_for_products

# --- GR-04: off-topic check ---------------------------------------------------------------

TEXT_CHECK_PROMPT = """You are the gatekeeper for ShopMate, the shopping assistant of a small online pantry store (honey, oils, nuts and seeds, grains, tea and coffee, snacks, dairy alternatives).
Decide whether the shopper's message is about shopping in this store.
ON: looking for or asking about any food or grocery product (even one the store may not sell), prices, ratings, ordering, order history, shopping preferences, a greeting, or a short reply to the assistant such as "yes", "maybe", "no", "the second one" or a number.
OFF: anything else, such as poems, stories, jokes, weather, news, coding, homework or general knowledge, even if it mentions a product.
Answer with one word: ON or OFF."""

PHOTO_CHECK_PROMPT = """A shopper uploaded this photo to a pantry store's shopping assistant.
Is it a photo of a food or grocery product?
Answer with one word: ON if it is, OFF if it is not."""


def is_off_topic(client, model, text, image_bytes=None, image_mime=None):
    """True if the message or the photo is not about shopping in this store.

    If the check itself fails (for example a rate limit), the message is let through and the
    agent's own prompt rule is the fallback.
    """
    try:
        if text.strip() and _verdict(client, model, [
            {"role": "system", "content": TEXT_CHECK_PROMPT},
            {"role": "user", "content": text},
        ]) == "OFF":
            return True
        if image_bytes:
            data_url = f"data:{image_mime or 'image/png'};base64,{base64.b64encode(image_bytes).decode()}"
            if _verdict(client, model, [{"role": "user", "content": [
                {"type": "text", "text": PHOTO_CHECK_PROMPT},
                {"type": "image_url", "image_url": {"url": data_url}},
            ]}]) == "OFF":
                return True
    except APIError as e:
        print(f"Off-topic check failed, letting the message through: {e}", flush=True)
    return False


def off_topic_reply():
    return ("Sorry, I can only help with shopping in this store. "
            f"We have these product categories: {', '.join(tools.list_categories())}.")


def _verdict(client, model, messages):
    response = client.chat.completions.create(
        model=model, messages=messages, reasoning_effort="none", max_tokens=5, temperature=0,
    )
    return "OFF" if (response.choices[0].message.content or "").strip().upper().startswith("OFF") else "ON"


# --- GR-01: no order without a clear yes --------------------------------------------------

HEDGE = re.compile(r"\b(maybe|perhaps|might|not sure|unsure|don'?t|do not|no|not|nope|nah|wait|hold on|later|cancel|think about|i guess|probably)\b")
YES = re.compile(r"\b(yes|yeah|yep|yup|sure|ok|okay|confirm|confirmed|go ahead|please do)\b")
ORDINAL = r"(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|last)"
PICK_WITH_VERB = re.compile(rf"\b(order|buy|purchase|take|get|want|choose|pick|go with)\b.*(#\s*\d+|number\s*\d+|\b{ORDINAL}\b)")
ORDER_NUMBER = re.compile(r"\b(order|buy|take|get|choose|pick)\s+#?\s*\d+\b")
JUST_A_PICK = re.compile(rf"^\s*(#?\s*\d+|number\s*\d+|(the\s+)?{ORDINAL}(\s+one)?)\s*[.!]?\s*$")


def is_clear_confirmation(text):
    """True if the shopper's message clearly confirms an order: "yes", "order #3", "the second one", "2".

    Anything hedged ("maybe", "not sure", "no") is never a confirmation, even if it also contains "yes".
    """
    t = text.lower()
    if HEDGE.search(t):
        return False
    return bool(YES.search(t) or PICK_WITH_VERB.search(t) or ORDER_NUMBER.search(t) or JUST_A_PICK.match(t))


# --- GR-03: no invented products, prices or ratings ---------------------------------------

PRODUCT_LINE = re.compile(r"^[ \t]*(?:#\d+\.|\d+\.|[-•])?[ \t]*(?P<name>[^\n]+?)[ \t]+\(ID:(?P<id>\d+)\)(?P<rest>[^\n]*)$", re.MULTILINE)


def find_unverified_products(reply):
    """Problems found when checking each "(ID:X)" line of a reply against the store; empty if all match."""
    lines = list(PRODUCT_LINE.finditer(reply))
    if not lines:
        return []

    ids = sorted({int(m["id"]) for m in lines})
    products = tools.get_products_by_id(ids)
    ratings = {r["product_id"]: r["average_rating"] for r in get_ratings_for_products(ids)}

    problems = []
    for m in lines:
        pid = int(m["id"])
        product = products.get(pid)
        if product is None:
            problems.append(f"There is no product with ID {pid}.")
            continue
        if m["name"].strip() != product["name"]:
            problems.append(f"ID {pid} is {product['name']}, not {m['name'].strip()}.")
        price = re.search(r"\$\s*(\d+(?:\.\d+)?)", m["rest"])
        if price and abs(float(price[1]) - product["price"]) > 0.005:
            problems.append(f"{product['name']} costs ${product['price']}, not ${price[1]}.")
        stars = re.search(r"★\s*(\d+(?:\.\d+)?)", m["rest"])
        if stars and abs(float(stars[1]) - ratings[pid]) > 0.005:
            problems.append(f"{product['name']} is rated {ratings[pid]}, not {stars[1]}.")
    return problems
