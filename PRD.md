# Product Requirements Document — ShopMate

**Date:** 2026-09-11
**Author:** alkabansal@rediffmail.com

---

## 1. Overview

ShopMate is a conversational shopping assistant for a small online pantry store that stocks 32 products across honey, oils, nuts and seeds, grains, tea and coffee, snacks, and dairy alternatives. It is for a busy shopper who already knows roughly what they want and does not want to browse. The shopper describes what they want in plain language, or shows a photo. ShopMate finds matching products, shows how other customers rated them, and places the order once the shopper says yes.

---

## 2. Problem

- Finding a product today means clicking through category pages and filter menus.
- A busy shopper who already knows what they want, and what their constraints are, does not want to browse.
- Shoppers have to repeat themselves: their constraints and standing preferences are not remembered.

---

## 3. Goals

| Goal | How we know |
|------|-------------|
| Stated constraints are respected | No product shown breaks a stated price cap, organic-only request, or minimum rating. |
| Shown data is real | Every product name, price, and rating shown matches the store data and the reviews API. |
| Product lists are consistent | Every product list matches the format in 6.3 exactly, with `(ID:X)` on every entry. |
| No unconfirmed or wrong orders | `checkout` is called only after explicit confirmation, and only with the product ID from the list shown. |
| Off-topic requests are redirected | An off-topic request gets a polite redirect and no product list. |
| Preferences are honoured | A preference stated in one session is applied in the next session without being stated again. |
| Done in two messages | A shopper with a clear request (e.g. "organic honey under $20 with at least a 4.5 rating") can go from request to placed order in two messages. |

---

## 4. Non-Goals

- No shopping cart with multiple items or quantities. One product per order.
- No payments, returns, cancellations, or delivery tracking.
- No login or multi-user support. A single shopper is assumed.
- No document retrieval (RAG). The store data is structured, and that is enough.

---

## 5. Users

A single busy shopper who already knows roughly what they want and what their constraints are. They want to state it once, for example *"organic honey under $20 with at least a 4.5 rating"*, and be done.

---

## 6. Functional Requirements

### 6.1 Search

| ID | Requirement |
|----|-------------|
| FR-01 | When the shopper describes what they want in plain language, the agent calls `search_products` and presents matching products from the store. |
| FR-02 | `search_products` performs a keyword search across product name, description, and category. |
| FR-03 | When the shopper states a price cap, the search uses `max_price` and no product priced above the cap is shown. |
| FR-04 | When the shopper asks for organic only, the search uses `is_organic` and only products with `is_organic = 1` are shown. |
| FR-05 | The browsing flow never places an order. |
| FR-26 | If the store sells nothing matching the request, the reply is exactly: "We don't have any product under this category. We have these product categories: X." X is the list of categories in the `products` table, read at the time of the request. If the store sells that kind of product but none match the shopper's filters, the reply says no products match the filters instead. |

### 6.2 Ratings

| ID | Requirement |
|----|-------------|
| FR-06 | The agent fetches the average rating and review count for every candidate product via `get_rating`, which is backed by `initial_setup/reviews_api.py`. |
| FR-07 | When the shopper states a minimum rating, the agent applies it after fetching ratings, and no product rated below the minimum is shown. |
| FR-08 | Every product shown comes with its average customer rating, exactly as returned by the reviews API. |
| FR-09 | The agent never queries the `reviews` table directly. |

### 6.3 Output format

| ID | Requirement |
|----|-------------|
| FR-10 | Every product list uses one line per product: `#<position>. <name> (ID:<id>) — $<price> ★<average rating> — organic`, as in the example below. (The brief does not show a line for a non-organic product.) |
| FR-11 | The `(ID:X)` part is mandatory on every entry. |
| FR-12 | The list is plain text, with one blank line between entries. |
| FR-13 | If exactly one product qualifies, it is still shown as a list, followed by: *"Would you like to order it? Just say yes or give me the number."* |

```
#1. Organic Raw Honey (ID:1) — $14.99 ★4.62 — organic

#2. Organic Buckwheat Honey (ID:5) — $18.99 ★4.62 — organic
```

### 6.4 Ordering

| ID | Requirement |
|----|-------------|
| FR-14 | The agent places an order only after explicit confirmation from the shopper. |
| FR-15 | Confirmation is the shopper picking a product from the list the agent showed, e.g. "the second one", "order #3", or "yes". |
| FR-16 | A request to search or browse is not a confirmation. |
| FR-17 | The agent takes the product ID from the list it showed earlier and calls `checkout` with it. It never guesses an ID. |
| FR-18 | `checkout` places an order for one product in the `orders` table and returns a confirmation with the order ID. |

### 6.5 Photo search

| ID | Requirement |
|----|-------------|
| FR-19 | When the shopper provides a photo, the agent calls `describe_product_image`, which returns what the product is, a search keyword, and whether it looks organic. |
| FR-20 | After identifying the product, the agent continues with the browsing flow (FR-01 to FR-13). |
| FR-21 | A photo that is not a product the store sells is stopped by the off-topic check (GR-04) before the agent runs, so `describe_product_image` is not called. |

### 6.6 Memory and preferences

| ID | Requirement |
|----|-------------|
| FR-22 | "What have I ordered before?" is answered by `get_order_history` from the `orders` table. |
| FR-23 | Preferences stated by the shopper, such as "I always want organic" or "never show me anything over $20", are stored in a `preferences` table in `store.db`. |
| FR-24 | Stored preferences persist across sessions. Re-running `initial_setup/setup_db.py` does not remove them. |
| FR-25 | Stored preferences are applied to later searches without the shopper stating them again: "always organic" applies the `is_organic` filter, and "nothing over $20" applies `max_price` = 20. |

The `preferences` table is created by the agent, not by `setup_db.py`:

| Column | Type | Purpose | Example |
|--------|------|---------|---------|
| `key` | TEXT, primary key | Which preference this is. One row per preference, so stating it again overwrites rather than duplicates. | `is_organic`, `max_price` |
| `value` | TEXT | The setting to apply. | `1`, `20` |
| `updated_at` | TEXT | When the shopper last stated it. | `2026-09-12 14:03:00` |

Only `is_organic` and `max_price` are stored, matching the two `search_products` filters in FR-03 and FR-04.

---

## 7. Tools

| Tool | What it does | Backed by |
|------|--------------|-----------|
| `search_products` | Keyword search across name, description, and category, with optional `max_price` and `is_organic` filters. | `products` table |
| `get_rating` | Average rating and review count for a product. | `initial_setup/reviews_api.py` |
| `checkout` | Places an order for one product and returns a confirmation with the order ID. | `orders` table |
| `describe_product_image` | Takes an image, returns what the product is, a search keyword, and whether it looks organic. | Vision-capable model |
| `get_order_history` | Returns what the shopper has ordered before. | `orders` table |

---

## 8. Guardrails

| ID | Guardrail | Enforced by |
|----|-----------|-------------|
| GR-01 | Never place an order without explicit confirmation from the shopper. A hedged reply such as "maybe" is never a confirmation, and one confirmation allows one order. | Code (`checkout` is blocked unless the shopper's latest message is a clear confirmation, e.g. "yes", "order #3", "the second one") and prompt |
| GR-02 | Never guess a product ID. The ID passed to `checkout` must come from the list shown earlier. | Code (`checkout` rejects an ID that was not in the list shown) and prompt |
| GR-03 | Never invent a product, price, or rating that is not in the store data. | Code (every `(ID:X)` line in a reply is checked against the `products` table and the reviews API; on a mismatch the model redoes the reply once, and if it is still wrong a safe message replaces it) and prompt |
| GR-04 | Off-topic check. Before the agent runs, every message and photo is checked for whether it is about shopping in this store. Off-topic input (e.g. "write me a poem", "what's the weather", `resources/elephant.png`) gets a polite redirect listing the store's product categories and never reaches the agent, so no tool is called. | Code (a separate check that runs before the agent) |
| GR-05 | Ratings come only from the reviews API, never from the `reviews` table. | Code (no tool reads the `reviews` table) |

---

## 9. Demonstration Scenarios

### Scenario 1 — Browsing with filters

User: `Show me organic honey with at least a 4.7 rating`

Expected:

```text
→ search_products(keyword="honey", is_organic=true)
→ get_rating for each candidate; products rated below 4.7 are dropped
→ checkout is not called
→ shopper sees:

#1. Organic Manuka Honey (ID:3) — $29.99 ★4.83 — organic

#2. Organic Acacia Honey (ID:7) — $17.99 ★4.75 — organic
```

### Scenario 2 — Single result with price cap, organic, and rating

User: `Organic honey under $20 with at least a 4.7 rating`

Expected:

```text
→ search_products(keyword="honey", max_price=20, is_organic=true)
→ get_rating for each candidate; products rated below 4.7 are dropped
→ Organic Manuka Honey (ID:3, $29.99) is not shown
→ shopper sees:

#1. Organic Acacia Honey (ID:7) — $17.99 ★4.75 — organic

Would you like to order it? Just say yes or give me the number.
```

### Scenario 3 — Ordering from the list

User (after the Scenario 1 list): `the second one`

Expected:

```text
→ checkout(product_id=7), the ID shown at #2
→ a row for Organic Acacia Honey (ID 7, $17.99) is added to the orders table
→ shopper sees a confirmation with the order ID
```

### Scenario 4 — No guessing an ID

User (after the two-entry Scenario 1 list): `order #3`

Expected:

```text
→ there is no #3 in the list shown, so checkout is not called
→ no row is added to the orders table
```

### Scenario 5 — Photo search

User: uploads `resources/honey.png`

Expected:

```text
→ describe_product_image identifies honey, returns search keyword "honey" and whether it looks organic
→ browsing flow: search_products(keyword="honey", ...), get_rating for each candidate
→ shopper sees honeys from the store in the 6.3 list format
→ checkout is not called
```

### Scenario 6 — Off-topic input

User: `write me a poem about honey`

User (separately): uploads `resources/elephant.png`

Expected, for each:

```text
→ the off-topic check (GR-04) stops the input before the agent runs
→ no tool is called
→ shopper sees a polite redirect to shopping in this store, and no product list
```

### Scenario 7 — Order history

User (after Scenario 3): `What have I ordered before?`

Expected:

```text
→ get_order_history
→ shopper sees their past orders from the orders table, including Organic Acacia Honey (ID 7), $17.99
```

### Scenario 8 — Preference remembered in a new session

User (session 1): `Never show me anything over $20`

User (session 2, new session): `Show me organic honey with at least a 4.7 rating`

Expected:

```text
→ session 1: the preference is stored in the preferences table
→ session 2: search_products(keyword="honey", is_organic=true, max_price=20), without the shopper restating the cap
→ Organic Manuka Honey (ID:3, $29.99) is not shown
→ shopper sees:

#1. Organic Acacia Honey (ID:7) — $17.99 ★4.75 — organic

Would you like to order it? Just say yes or give me the number.
```

---

## 10. Acceptance Criteria

- [ ] "Organic honey under $20 with at least a 4.5 rating" shows no product above $20, no non-organic product, and no product rated below 4.5.
- [ ] Every rating shown matches the value from `get_product_rating` in the reviews API.
- [ ] Every product list matches the 6.3 format exactly, with `(ID:X)` on every entry and one blank line between entries.
- [ ] When exactly one product qualifies, it is shown as a list followed by "Would you like to order it? Just say yes or give me the number."
- [ ] A browsing request never adds a row to the `orders` table.
- [ ] After a list is shown, "the second one", "order #3", or "yes" orders the product whose ID was shown at that position, and the new `orders` row matches it.
- [ ] Picking a number that is not in the list shown places no order.
- [ ] "maybe" after a list places no order, and ShopMate asks the shopper to confirm.
- [ ] `resources/honey.png` returns honeys; `resources/oats.png` returns oats.
- [ ] `resources/elephant.png` and off-topic text requests (e.g. "write me a poem about honey") get a polite redirect, no product list, and no tool is called.
- [ ] "What have I ordered before?" matches the contents of the `orders` table.
- [ ] After "I always want organic" in one session, a search in a new session shows only organic products without the shopper repeating it.
- [ ] After "never show me anything over $20" in one session, a search in a new session shows nothing over $20 without the shopper repeating it.
- [ ] No agent code reads the `reviews` table directly, and `initial_setup/` is unchanged.

---

## 11. Technology and Build Instructions

| Component | Choice |
|-----------|--------|
| Language | Python 3.10+ |
| LLM provider and model | qwen/qwen3.8-27b |
| Vision model | qwen/qwen3.8-27b (same model, used for photo search) |
| UI | Streamlit web chat. Each reply has a collapsible "Tools used" panel listing the tools called, in order, with their arguments and results. |
| Preferences stored in | `preferences` table in `store.db` |

Rules for Claude Code:

1. Read `SETUP.md` first. Build on top of `initial_setup/`; do not modify it.
2. Ratings come only from `initial_setup/reviews_api.py`.
3. Keep API keys in `.env`.
4. Do not add anything outside this PRD.
