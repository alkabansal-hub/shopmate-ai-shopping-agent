# ShopMate Guardrails

Five guardrails, matching PRD section 8. The code for GR-01, GR-03 and GR-04 is in [guardrails.py](guardrails.py). GR-02 is in `checkout` in [tools.py](tools.py). GR-05 is enforced by how the tools are built.

When a guardrail steps in, the **Tools used** panel under the reply shows a 🛡️ line saying which one and why.

---

## GR-04 — Off-topic check

**What it blocks:** Messages and photos that have nothing to do with shopping in this store. The shopper gets a polite redirect that lists the store's product categories.

**Where it sits:** In code, **before the agent runs**. A small, separate call asks the model one question, "ON or OFF topic?", about the text and, if there is one, the photo. If the answer is OFF, the message never reaches the agent, so no tool is called and nothing is added to the conversation. If the check itself fails (for example, a rate limit), the message is let through and the agent's prompt rule is the fallback.

| Trips it | Does not trip it |
|---|---|
| "write me a poem about honey" | "pulses" (a product the store doesn't sell is still shopping) |
| `resources/elephant.png` | `resources/honey.png` |

Also tested: "what's the weather" and "tell me a joke" are blocked. "Add 2 kg basmati rice", "yes", "maybe", "hi" and `oats.png` are let through.

---

## GR-01 — No order without a clear yes

**What it blocks:** Placing an order when the shopper hasn't clearly confirmed. A hedged reply is never a yes, even if it also contains "yes" or a number. One confirmation allows one order.

**Where it sits:** In two places.
1. **Prompt:** the agent is told to call `checkout` only after a clear confirmation, and to ask again when the reply is unclear.
2. **Code:** before `checkout` runs, the shopper's latest message is checked with simple word rules. If it isn't a clear confirmation, `checkout` is refused and no order is placed, whatever the model decided.

| Counts as a yes | Never counts |
|---|---|
| "yes", "sure", "ok", "go ahead" | "maybe", "not sure", "I think so", "hmm" |
| "order #3", "the second one", "2", "I'll take the first one" | "maybe the second one", "yes but not now", "no thanks" |

| Trips it | Does not trip it |
|---|---|
| "maybe" after a product list: no order, ShopMate asks the shopper to confirm | "yes" after a product list: one order is placed |

**Limitation:** the rules are word-based, so they're strict on purpose. A reply like "no, the second one" is treated as unclear and the shopper is asked again rather than risking a wrong order.

---

## GR-02 — Never guess a product ID

**What it blocks:** Ordering a product that wasn't in the most recent list shown to the shopper.

**Where it sits:** In code, inside `checkout`. The app remembers the `(ID:X)` values in the last list it showed, and `checkout` refuses any other ID.

| Trips it | Does not trip it |
|---|---|
| The list showed IDs 3 and 7, and checkout is attempted for ID 5 | The list showed ID 9, and the shopper says "yes" (checkout for ID 9) |

---

## GR-03 — No invented products, prices or ratings

**What it blocks:** A reply that lists a product, price or rating that doesn't match the store. We saw this really happen once, when the model invented four oat milks.

**Where it sits:** In two places.
1. **Prompt:** the agent must search before showing any product, and use only values from tool results.
2. **Code:** after the agent writes its reply, every `(ID:X)` line is checked against the `products` table (name, price) and the reviews API (rating). On a mismatch, the model is told what was wrong and redoes the reply once. If it is still wrong, the reply is replaced with *"Sorry, I couldn't verify those product details against the store. Please ask again."*

| Trips it | Does not trip it |
|---|---|
| `#1. Oat Milk (ID:10) — $3.99 ★4.2` (ID 10 is Coconut Oil, $12.49, ★3.67) | `#1. Oat Milk (ID:30) — $4.49 ★4.33` |

---

## GR-05 — Ratings only from the reviews API

**What it blocks:** Reading ratings straight from the `reviews` table, which the brief treats as another company's data.

**Where it sits:** In the design of the tools. `get_rating` calls `initial_setup/reviews_api.py`, and no tool queries the `reviews` table. No shopper input can trip it, because there is no code path that reads that table.

| Trips it | Does not trip it |
|---|---|
| (No input can; there is no code path to the `reviews` table) | "honey with 4.5+ rating": ratings come from `get_rating`, i.e. the reviews API |
