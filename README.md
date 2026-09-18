# ShopMate — AI Shopping Agent

A conversational shopping assistant for a small online pantry store. Tell it what you want in plain language, or upload a photo, and it finds matching products with their customer ratings and places the order once you confirm. The spec is [PRD.md](PRD.md).

**Demo video:** https://www.loom.com/share/4a685ab925c940eb8bae2c921beb6d94

## Run it

From this folder, on Windows:

```bash
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe initial_setup/setup_db.py
.venv\Scripts\python.exe -m streamlit run app.py --server.headless true
```

Then open http://localhost:8501 in your browser. Keep the terminal open while you use the app; closing it or pressing Ctrl+C stops the app.

Running `setup_db.py` is only needed once; it is safe to run again. The commands call the virtual environment's Python directly, so they work even where PowerShell blocks the `activate` script. `--server.headless true` skips Streamlit's first-run email prompt, which otherwise waits silently in the terminal.

Put your Groq API key in `.env` as `GROQ_API_KEY=...` (free key: https://console.groq.com/keys).

## What's in here

| File | What it is |
|------|------------|
| `app.py` | Streamlit chat interface with photo upload. |
| `agent.py` | The agent: system prompt, tool definitions, the model loop, and the photo tool. |
| `guardrails.py` | The code guardrails: off-topic check, order confirmation check, and store data check. See [GUARDRAILS.md](GUARDRAILS.md). |
| `tools.py` | The store tools: `search_products`, `get_rating`, `checkout`, `get_order_history`, and the `preferences` table. |
| `initial_setup/` | Store database and reviews API. Provided; not modified. |

Under every reply, open **Tools used** to see which tools the agent called, in order, with their arguments and results. The terminal also prints each call, e.g.
`TOOL [step 1] search_products({"keyword":"honey","max_price":20})`.

## Model

`qwen/qwen3.8-27b` on Groq, used for both chat and photo search, with the model's reasoning mode turned off.

On Groq's free tier this model has per-minute limits and a daily cap of 200,000 tokens. Each message also makes one small off-topic check call. Long chats use more tokens per message, because the whole conversation is resent each time. A search takes two or three model calls, so if you send several messages quickly the app may pause while it waits for the limit to reset.

## Guardrails and evals

- **Guardrails:** see [GUARDRAILS.md](GUARDRAILS.md). The code is in `guardrails.py`.
- **Evals:** see [EVALS.md](EVALS.md). Test cases are in `eval_set.csv` and `eval_set.xlsx`; the rubric and scored runs are in `eval_set.xlsx`. Run them with:

```bash
.venv\Scripts\python.exe run_evals.py
```

## Known gaps

- Nothing saves a preference yet, so "I always want organic" is acknowledged but not remembered (eval E12). A preference already stored in the `preferences` table is applied to searches (eval E11).
- Eval run 1 scored E01–E07 only. E08–E14 were not run because Groq's free-tier daily token limit was reached; they need a re-run once the allowance resets.

## DEMO Link
https://www.loom.com/share/4a685ab925c940eb8bae2c921beb6d94