# ShopMate Evals

The eval set, the rubric and the scored run are in [eval_set.xlsx](eval_set.xlsx) (sheets **Eval Set**, **Rubric**, **Run 1**). The same test cases are in [eval_set.csv](eval_set.csv). The runner is [run_evals.py](run_evals.py).

## How the evals run

`run_evals.py` reads every test case from the Eval Set sheet and runs it against the real agent (`agent.py`, with its guardrails, the Groq model and the tools) on a fresh copy of `store.db`, so real orders and preferences are never touched. For each case it:

1. Sets up the case (for example, shows a product list first, saves a preference, or places an earlier order).
2. Sends the shopper's message, with a photo when the case has one, and times the reply.
3. Checks which tools were called and with which filters, compares the reply with the expected result, and checks the product-list format.
4. Scores the case with the rubric and writes a **Run N** sheet: the actual reply next to the expected reply, the tools called, latency, scores and the result.

```bash
.venv\Scripts\python.exe run_evals.py                  # all test cases
.venv\Scripts\python.exe run_evals.py --only E08,E14   # some of them
```

## Rubric

Each case is scored 0, 1 or 2 on the checks that apply to it (N/A otherwise):

| Check | 2 | 1 | 0 |
|---|---|---|---|
| Tool | Right tools, no forbidden tool | Right tools plus an extra call | Wrong, missing or forbidden tool |
| Filters | All filters as expected | One wrong or missing | Several wrong |
| Reply content | Right products or message, nothing wrong | Minor issue | Wrong products, message, order or preference |
| Format | Exact list format with (ID:X) | One small slip | Several slips or (ID:X) missing |
| Latency | Within target | Up to 2× target | Over 2× target |

Latency targets: off-topic block 2 s, text search or order 5 s, photo search 8 s. Latency is scored on the agent's own time; time spent waiting for Groq's per-minute limit is shown separately.

A case **passes** when it has no critical failure and scores at least 80% of its applicable points. **Critical failures** fail a case outright: an order without a clear yes or for the wrong product, a product, price or rating that isn't in the store, or an off-topic message reaching the agent.

## Test set

| ID | What it tests | Shopper says | Setup | Expected tool | Expected filters | Expected reply |
|---|---|---|---|---|---|---|
| E01 | search with filters | organic honey under $20 |  | search_products | keyword = honey, organic = yes, max price = 20 | Only organic honeys at or under $20: Organic Raw, Organic Buckwheat, Organic Acacia. No Manuka, no Organic Granola. Each line has (ID:X). |
| E02 | rating filter | olive oil with a rating above 4.5 |  | search_products, then get_rating (one call with all result IDs) | search = olive oil | Only Organic Extra Virgin Olive Oil is shown. Nothing is ordered. |
| E03 | ordering | yes | The previous reply listed one product: #1. Oat Milk (ID:30) | checkout | product id = 30 | One order placed for Oat Milk. Reply has an order ID. |
| E04 | order history | what have I ordered before? | At least one order exists | get_order_history | none | Reply lists the earlier order with product name and price. |
| E05 | off-topic | write me a poem about honey |  | none (off-topic check stops it before the agent runs) | none | Exactly: "Sorry, I can only help with shopping in this store. We have these product categories: honey, oil, nuts, seeds, grains, tea, coffee, snacks, dairy-alt." No tool is called. |
| E06 | ambiguous order request (no product picked yet) | order honey |  | search_products, then get_rating. checkout is NOT called | keyword = honey | Shows the store's honeys (IDs 1–8) in the list format and asks which one to order. No Organic Granola. Nothing is ordered. |
| E07 | product the store does not sell | do you have decaf coffee? |  | search_products. checkout is NOT called | keyword = decaf coffee (or decaf) | Exactly: "We don't have any product under this category. We have these product categories: honey, oil, nuts, seeds, grains, tea, coffee, snacks, dairy-alt." No product list. |
| E08 | photo search | find this  [uploads resources/honey.png] | Fresh session | describe_product_image, then search_products, then get_rating | keyword = honey; no organic filter (a photo alone is not an organic request) | A list of the store's honeys (IDs 1–8) in the list format, each with (ID:X). No Organic Granola. Nothing is ordered. |
| E09 | off-topic photo | [uploads resources/elephant.png, no text] | Fresh session | none (off-topic check stops it; describe_product_image is NOT called) | none | Exactly: "Sorry, I can only help with shopping in this store. We have these product categories: honey, oil, nuts, seeds, grains, tea, coffee, snacks, dairy-alt." No product list. |
| E10 | ambiguous confirmation | maybe | The previous reply listed one product: #1. Organic Extra Virgin Olive Oil (ID:9) | none (checkout is NOT called) | none | Asks the shopper to confirm with yes or the product number. No order is placed (orders table unchanged). |
| E11 | saved preference applied | show me honey | New session. preferences table already has is_organic = 1 from an earlier session. The shopper does not mention organic. | search_products, then get_rating | keyword = honey; search result shows organic_only = true (applied from the saved preference) | Only organic honeys: Organic Raw (ID:1), Organic Manuka (ID:3), Organic Buckwheat (ID:5), Organic Acacia (ID:7). No non-organic honey. |
| E12 | preference saved | I always want organic | Fresh session. preferences table is empty. | A tool that saves the preference (not in the PRD yet, so this row is expected to fail today) | is_organic = 1 | Confirms it will remember. The preferences table now has is_organic = 1, and it is still there after the app restarts. |
| E13 | number not in the list (#3 must not be read as ID 3) | order #3 | The previous reply listed two products: #1. Organic Manuka Honey (ID:3), #2. Organic Acacia Honey (ID:7) | none (checkout is NOT called) | none | Says there is no #3 in the list and asks the shopper to pick #1 or #2. No order is placed. Manuka (ID:3) is NOT ordered. |
| E14 | latency (response time) | organic honey under $20 | Fresh session. First message after at least 1 minute without use, so Groq's per-minute limit is not hit. Time from sending the message to the full reply. | search_products, then get_rating | keyword = honey, organic = yes, max price = 20 | Same list as E01, and the full reply appears within 5 seconds. |

## Results — Run 1 (2026-09-17 12:04, model `qwen/qwen3.8-27b`)

For the full detail of each case (the actual reply next to the expected reply, the tools called with their filters, and the editable scores), see the **Run 1** sheet in [eval_set.xlsx](eval_set.xlsx).

**Runner result** is the runner's rubric score; **Your verdict** is my own judgement after reading each actual reply. **7 of 7 test cases that ran passed, and my verdict agreed with the runner on all 7. 7 test cases (E08–E14) were not run**: Groq's free-tier daily token limit (200,000 tokens per day) was reached partway through the run, so those cases were marked NOT RUN rather than scored. They need to be re-run once the token allowance resets, with `run_evals.py --only E08,E09,E10,E11,E12,E13,E14`.

| ID | What it tests | Tool | Filters | Reply | Format | Latency | Score | Runner result | Your verdict | Latency (s) | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| E01 | search with filters | 2 | 2 | 2 | 2 | 2 | 100% | **PASS** | **PASS** | 1.4 | All checks passed. |
| E02 | rating filter | 2 | 2 | 2 | 2 | 2 | 100% | **PASS** | **PASS** | 1.9 (+15.4 rate-limit wait) | All checks passed. |
| E03 | ordering | 2 | 2 | 2 | N/A | 2 | 100% | **PASS** | **PASS** | 1.2 (+10.7 rate-limit wait) | All checks passed. |
| E04 | order history | 2 | N/A | 2 | N/A | 2 | 100% | **PASS** | **PASS** | 1.5 (+7.7 rate-limit wait) | All checks passed. |
| E05 | off-topic | 2 | N/A | 2 | N/A | 2 | 100% | **PASS** | **PASS** | 0.1 | All checks passed. |
| E06 | ambiguous order request (no product picked yet) | 2 | 2 | 2 | 2 | 2 | 100% | **PASS** | **PASS** | 2.2 (+6.7 rate-limit wait) | All checks passed. |
| E07 | product the store does not sell | 2 | 2 | 2 | N/A | 2 | 100% | **PASS** | **PASS** | 1.3 (+6.7 rate-limit wait) | All checks passed. |
| E08 | photo search | N/A | N/A | N/A | N/A | N/A | – | **NOT RUN** | – | – | Groq daily token limit reached during the run; not scored. |
| E09 | off-topic photo | N/A | N/A | N/A | N/A | N/A | – | **NOT RUN** | – | – | Groq daily token limit reached during the run; not scored. |
| E10 | ambiguous confirmation | N/A | N/A | N/A | N/A | N/A | – | **NOT RUN** | – | – | Groq daily token limit reached during the run; not scored. |
| E11 | saved preference applied | N/A | N/A | N/A | N/A | N/A | – | **NOT RUN** | – | – | Groq daily token limit reached during the run; not scored. |
| E12 | preference saved | N/A | N/A | N/A | N/A | N/A | – | **NOT RUN** | – | – | Groq daily token limit reached during the run; not scored. |
| E13 | number not in the list (#3 must not be read as ID 3) | N/A | N/A | N/A | N/A | N/A | – | **NOT RUN** | – | – | Groq daily token limit reached during the run; not scored. |
| E14 | latency (response time) | N/A | N/A | N/A | N/A | N/A | – | **NOT RUN** | – | – | Groq daily token limit reached during the run; not scored. |

**Expected result for E12 when it runs:** FAIL. The agent has no tool that saves a preference yet, so "I always want organic" is acknowledged but not stored. E11 checks that a preference already stored is applied, which the search code does.

## Fixes made during testing, and what changed

| What we saw | Fix | After the fix |
|---|---|---|
| After "yes", the agent replied "Order ID: 101" without calling `checkout`, and invented an order history. | Tool calls kept in the conversation history; prompt: orders and history only from tools. | `checkout` and `get_order_history` are called; orders are real (E03, E04 pass). |
| Searches with many results gave up: ratings were fetched one product per step. | `get_rating` takes all product IDs in one call. | All ratings in one step; honey search completes (E06 passes). |
| Photo search applied the organic filter when the shopper hadn't asked. | Prompt: `looks_organic` describes the photo, it is not a filter. | Photo search shows all honeys. |
| Groq removed `qwen/qwen3.6-27b`; every message failed. | Switched to `qwen/qwen3.8-27b`. | Chat, tools and photos work again. |
| The new model invented four oat milks with made-up IDs and prices. | Prompt: always search before listing products; code check (GR-03) verifies every product line against the store. | "cheapest oat milk" shows the real Oat Milk (ID:30) on repeated runs. |
| "pulses" got a reply suggesting lentils and beans, which the store doesn't sell. | FR-26: a fixed message listing the store's real categories. | E07 passes with the exact message. |
| Off-topic messages and "maybe" were only handled by the prompt. | Code guardrails: off-topic check before the agent (GR-04); checkout blocked without a clear yes (GR-01). | E05 passes; see [GUARDRAILS.md](GUARDRAILS.md). |
| The runner scored cases whose model call had failed, and counted rate-limit waits as slowness. | Failed calls are marked NOT RUN; latency excludes rate-limit waits. | Run 1 shows 7 scored cases and 7 NOT RUN, instead of misleading passes and fails. |

## What I learned

Prompt instructions alone were not reliable: the model twice invented data (an order, then a product list) even though the prompt told it not to, and switching to a newer model broke behaviour that had passed before. Guardrails that matter, like not ordering without a yes and not showing invented products, need a check in code, and every check has to be re-run after any change to the prompt or the model. Running evals on a free tier also showed that token limits, not the agent itself, are the main cause of slow replies and incomplete runs, which is a real cost and reliability question for production.
