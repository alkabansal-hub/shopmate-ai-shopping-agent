"""ShopMate chat interface. Run from this folder with: streamlit run app.py"""

import streamlit as st

from agent import ShopMateAgent

st.set_page_config(page_title="ShopMate", page_icon="🛒")
st.title("🛒 ShopMate")
st.caption("Tell me what you're looking for, or upload a photo of a product.")

if "agent" not in st.session_state:
    st.session_state.agent = ShopMateAgent()
    st.session_state.turns = []  # (role, text, image_bytes, tool_trace, guardrail_events) for redrawing the chat


def show_text(text):
    # Escape $ so Streamlit doesn't render prices as maths.
    st.markdown(text.replace("$", "\\$"))


def show_trace(trace, guardrail_events):
    """Collapsible list of the tools the agent called for this reply, in order, and any guardrail that stepped in."""
    label = f"Tools used ({len(trace)})" if trace else "Tools used (none)"
    if guardrail_events:
        label += " · 🛡️ guardrail"
    with st.expander(label):
        for event in guardrail_events:
            st.markdown(f"🛡️ {event}".replace("$", "\\$"))
        if not trace:
            st.caption("No tools were called for this reply.")
        for call in trace:
            st.markdown(f"**Step {call['step']}** · `{call['tool']}({call['arguments']})`")
            st.json(call["result"], expanded=False)


for role, text, image, trace, guardrail_events in st.session_state.turns:
    with st.chat_message(role):
        if image:
            st.image(image, width=200)
        if text:
            show_text(text)
        if role == "assistant":
            show_trace(trace, guardrail_events)

prompt = st.chat_input("Ask ShopMate…", accept_file=True, file_type=["png", "jpg", "jpeg", "webp"])

if prompt:
    text = prompt.text or ""
    upload = prompt.files[0] if prompt.files else None
    image_bytes = upload.getvalue() if upload else None

    with st.chat_message("user"):
        if image_bytes:
            st.image(image_bytes, width=200)
        if text:
            show_text(text)
    st.session_state.turns.append(("user", text, image_bytes, None, None))

    agent = st.session_state.agent
    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            reply = agent.chat(text, image_bytes, upload.type if upload else None)
        show_text(reply)
        show_trace(agent.last_trace, agent.last_guardrail_events)
    st.session_state.turns.append(("assistant", reply, None, agent.last_trace, agent.last_guardrail_events))
