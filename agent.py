"""ShopMate agent: sends the conversation to the model, runs the tools it asks for, and returns its reply."""

import base64
import json
import os
import re

from dotenv import load_dotenv
from groq import APIError, Groq

import guardrails
import tools

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, ".env"))

MODEL = "qwen/qwen3.8-27b"
MAX_TOOL_ROUNDS = 8

SYSTEM_PROMPT = """You are ShopMate, the shopping assistant for a small online pantry store. The store sells honey, oils, nuts and seeds, grains, tea and coffee, snacks, and dairy alternatives. Reply in plain text, never Markdown.

BROWSING
- You do not know the store's products, prices or ratings. Every time the shopper asks about products, including "cheapest", "best" or "do you have", you must call search_products and get_rating first. Never write a product list without calling them in this same turn.
- When the shopper describes what they want, call search_products. Use a short product keyword such as "honey", "olive oil" or "oat milk". Put a price cap in max_price and an organic-only request in is_organic="yes"; never put them in the keyword.
- Then call get_rating once, with the IDs of every product returned.
- If the shopper stated a minimum rating, leave out every product whose average_rating is below it.
- Browsing never places an order.
- If search_products returns no products and store_sells_this_kind_of_product is false, reply with exactly this and nothing else, listing available_categories in the order given:
  We don't have any product under this category. We have these product categories: <available_categories, separated by commas>.
- If store_sells_this_kind_of_product is true, or products were found but none meet the minimum rating, say that no products match the shopper's filters. Do not suggest other products.
- Never mention a product, price or rating that did not come from a tool result.

PRODUCT LIST FORMAT
Every product list uses exactly this format, plain text, one blank line between entries:

#1. Organic Raw Honey (ID:1) — $14.99 ★4.62 — organic

#2. Clover Honey (ID:4) — $8.99 ★3.5

- Number the entries #1, #2, #3 in the order shown.
- Use the exact name, ID, price and average_rating from the tool results. The (ID:X) is mandatory.
- End the line with " — organic" only when the product is organic.
- If exactly one product qualifies, still show it as a list, then ask: "Would you like to order it? Just say yes or give me the number."

ORDERING
- Call checkout only after the shopper explicitly confirms, by picking a product from the list you showed (for example "the second one" or "order #3") or by saying "yes". A request to search or browse is not a confirmation.
- If the shopper's reply is unclear, such as "maybe" or "I think so", do not call checkout. Ask them to confirm with yes or the product number.
- If checkout returns an error, tell the shopper that no order was placed and why.
- Take the product_id from the list you showed earlier. Never guess an ID. If the shopper picks a number that is not in the list, do not call checkout.
- Only checkout places an order. Never say an order was placed, and never give an order ID, unless checkout returned it in this conversation.
- After checkout, confirm the order with its order ID, the product name and the price.

PHOTOS
- When the shopper has uploaded a photo, call describe_product_image, then continue with browsing using its search_keyword.
- looks_organic is only a description of the photo. Do not use it as a filter: set is_organic="yes" only if the shopper asked for organic.

ORDER HISTORY
- For questions about past orders, always call get_order_history and list only what it returns. Never answer from memory.

OFF-TOPIC
- If a request has nothing to do with shopping in this store, politely say you can only help with shopping in this store, and do not call any tool."""

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": "Keyword search across product name, description and category, with optional price cap and organic filter.",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "A short product keyword, e.g. 'honey' or 'olive oil'."},
                    "max_price": {"type": "number", "description": "Only return products at or below this price."},
                    "is_organic": {"type": "string", "enum": ["yes", "no"], "description": "'yes' to return only organic products."},
                },
                "required": ["keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_rating",
            "description": "Average customer rating and review count for products, from the reviews API. Pass every candidate product ID in one call.",
            "parameters": {
                "type": "object",
                "properties": {"product_ids": {"type": "array", "items": {"type": "integer"}}},
                "required": ["product_ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "checkout",
            "description": "Places an order for one product and returns a confirmation with the order ID. Only call after the shopper explicitly confirms.",
            "parameters": {
                "type": "object",
                "properties": {"product_id": {"type": "integer", "description": "The ID from the product list you showed."}},
                "required": ["product_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "describe_product_image",
            "description": "Looks at the photo the shopper uploaded and returns what the product is, a search keyword, and whether it looks organic.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_order_history",
            "description": "Returns what the shopper has ordered before.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

IMAGE_PROMPT = """A shopper uploaded this photo to a pantry store's shopping assistant.
Reply with JSON only, in this shape:
{"product": "what the photo shows, in a few words", "search_keyword": "one or two words to search the store with, e.g. honey", "looks_organic": true or false}"""


class ShopMateAgent:
    def __init__(self):
        self.client = Groq(max_retries=6)
        self.history = []            # the whole conversation, tool calls included, across turns
        self.shown_product_ids = []  # IDs in the most recent product list shown (used by checkout, GR-02)
        self.image = None            # (bytes, mime type) of the most recent photo uploaded
        self.last_trace = []         # tool calls made while answering the latest message, shown in the UI
        self.last_guardrail_events = []  # guardrails that stepped in while answering the latest message
        self.checkout_allowed = False    # GR-01: set only by a clear confirmation, used up by one order

    def chat(self, text, image_bytes=None, image_mime=None):
        self.last_trace = []
        self.last_guardrail_events = []

        # GR-04: the off-topic check runs before the agent. A blocked message never reaches it.
        if guardrails.is_off_topic(self.client, MODEL, text, image_bytes, image_mime):
            self.last_guardrail_events.append("GR-04 off-topic check: message blocked before the agent ran.")
            return guardrails.off_topic_reply()

        # GR-01: only a clear confirmation in this message can unlock checkout.
        self.checkout_allowed = guardrails.is_clear_confirmation(text)

        if image_bytes:
            self.image = (image_bytes, image_mime or "image/png")
            text = f"[The shopper uploaded a photo.] {text}".strip()

        messages = [{"role": "system", "content": SYSTEM_PROMPT}, *self.history, {"role": "user", "content": text}]

        try:
            reply = self._run(messages)

            # GR-03: every product line must match the store data. One retry, then a safe reply.
            problems = guardrails.find_unverified_products(reply)
            if problems:
                self.last_guardrail_events.append("GR-03 store data check: reply did not match the store, asked the model to redo it. " + " ".join(problems))
                retry_messages = messages + [
                    {"role": "assistant", "content": reply},
                    {"role": "user", "content": "[Store data check] Your last reply does not match the store data: " + " ".join(problems)
                     + " Call search_products and get_rating again and rewrite the reply using only values from the tool results."},
                ]
                retry_start = len(retry_messages)
                reply = self._run(retry_messages)
                messages += retry_messages[retry_start:]  # keep the retry's tool calls; drop the wrong reply and the correction
                if guardrails.find_unverified_products(reply):
                    self.last_guardrail_events.append("GR-03 store data check: the retry still did not match, so the reply was replaced.")
                    reply = "Sorry, I couldn't verify those product details against the store. Please ask again."
        except APIError as e:
            print(f"Model call failed: {e}", flush=True)
            reply = f"Sorry, I couldn't reach the model just now ({e.__class__.__name__}). Please try again in a moment."

        shown = [int(i) for i in re.findall(r"\(ID:(\d+)\)", reply)]
        if shown:
            self.shown_product_ids = shown

        # Keep tool calls in the history so the model sees that orders and ratings come from tools.
        self.history = messages[1:] + [{"role": "assistant", "content": reply}]
        return reply

    def _run(self, messages):
        for round_number in range(1, MAX_TOOL_ROUNDS + 1):
            response = self.client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=TOOL_SCHEMAS,
                reasoning_effort="none",
                max_tokens=800,
                temperature=0.2,
            )
            message = response.choices[0].message
            if not message.tool_calls:
                return (message.content or "").strip()

            messages.append({
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [
                    {"id": c.id, "type": "function", "function": {"name": c.function.name, "arguments": c.function.arguments}}
                    for c in message.tool_calls
                ],
            })
            for call in message.tool_calls:
                result = self._call_tool(call.function.name, call.function.arguments)
                self.last_trace.append({
                    "step": round_number,
                    "tool": call.function.name,
                    "arguments": call.function.arguments or "{}",
                    "result": result,
                })
                print(f"TOOL [step {round_number}] {call.function.name}({call.function.arguments}) -> {json.dumps(result)[:300]}", flush=True)
                messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result, separators=(",", ":"))})

        return "Sorry, I couldn't finish that request. Please try rephrasing it."

    def _call_tool(self, name, arguments):
        try:
            args = json.loads(arguments or "{}")
        except json.JSONDecodeError:
            return {"error": "Arguments were not valid JSON."}
        try:
            if name == "search_products":
                return tools.search_products(args["keyword"], args.get("max_price"), args.get("is_organic"))
            if name == "get_rating":
                return tools.get_rating(args["product_ids"])
            if name == "checkout":
                # GR-01 in code: whatever the model decided, no clear yes means no order.
                if not self.checkout_allowed:
                    self.last_guardrail_events.append("GR-01 confirmation check: checkout blocked, the shopper's latest message is not a clear yes.")
                    return {"error": "No order was placed: the shopper has not clearly confirmed. Ask them to confirm with yes or the product number."}
                result = tools.checkout(args["product_id"], self.shown_product_ids)
                if "error" in result:
                    self.last_guardrail_events.append(f"GR-02 list check: {result['error']}")
                else:
                    self.checkout_allowed = False  # one order per confirmation
                return result
            if name == "describe_product_image":
                return self.describe_product_image()
            if name == "get_order_history":
                return tools.get_order_history()
            return {"error": f"Unknown tool {name}."}
        except (KeyError, ValueError, TypeError) as e:
            return {"error": f"Bad arguments for {name}: {e}"}

    def describe_product_image(self):
        """Vision tool: what the product is, a search keyword, and whether it looks organic (FR-19)."""
        if self.image is None:
            return {"error": "The shopper has not uploaded a photo."}
        image_bytes, mime = self.image
        data_url = f"data:{mime};base64,{base64.b64encode(image_bytes).decode()}"
        response = self.client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": IMAGE_PROMPT},
                {"type": "image_url", "image_url": {"url": data_url}},
            ]}],
            reasoning_effort="none",
            max_tokens=200,
            temperature=0,
        )
        content = response.choices[0].message.content or ""
        match = re.search(r"\{.*\}", content, re.DOTALL)
        try:
            return json.loads(match.group(0)) if match else {"error": f"Could not read the photo: {content}"}
        except json.JSONDecodeError:
            return {"error": f"Could not read the photo: {content}"}


tools.ensure_preferences_table()
