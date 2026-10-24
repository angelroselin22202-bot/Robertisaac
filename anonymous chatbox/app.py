import html
import os
import random
import re
import time
import uuid
from datetime import datetime

import streamlit as st
from supabase import create_client,client

st.set_page_config(
    page_title="Anonymous chatbox",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# -------------------- DARK THEME --------------------

DARK_CSS = """
<style>
.stApp {
    background:
        radial-gradient(ellipse at 10% 0%, #21153e, transparent 40%),
        #0b1020;
    color: #f1f5f9;
}
[data-testid="stHeader"] { background: #0b1020; }
[data-testid="stSidebar"] { background: #10172a; }

.hero {
    padding: 28px;
    border: 1px solid #43336a;
    border-radius: 20px;
    background: linear-gradient(135deg, #251648, #10172a);
    margin-bottom: 20px;
}
.hero h1 { color: #f5f3ff; margin: 0; }
.hero p { color: #cbd5e1; }

.chat-card {
    background: #111b30;
    border: 1px solid #27334b;
    border-radius: 14px;
    padding: 12px 16px;
    margin: 8px 0;
}
.chat-meta { color: #a5b4fc; font-size: 0.85rem; }
.chat-body {
    color: #f1f5f9;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
    margin-top: 5px;
}
div.stButton > button[kind="primary"] {
    background: #7c3aed;
    color: white;
    border: 0;
}
.small-note { color: #94a3b8; font-size: 0.82rem; }

textarea {
    background: #0f1729 !important;
    color: #f1f5f9 !important;
    -webkit-text-fill-color: #f1f5f9 !important;
    caret-color: #f1f5f9 !important;
    border: 1px solid #43336a !important;
}
textarea::placeholder {
    color: #64748b !important;
}
</style>
"""

HERO_HTML = """
<div class="hero">
    <h1>💬 Anonymous chatbox</h1>
    <p>Your public anonymous chat room. Meet people and talk freely.</p>
</div>
"""

COMMUNITY_RULES = """
- Respect other people.
- Do not share personal information.
- No threats, harassment or spam.
- Report inappropriate messages.
"""

st.markdown(DARK_CSS, unsafe_allow_html=True)
st.markdown(HERO_HTML, unsafe_allow_html=True)


# -------------------- CONFIGURATION --------------------

def get_config(name):
    try:
        value = st.secrets.get(name)
        if value:
            return str(value)
    except Exception:
        pass
    return os.getenv(name, "")


SUPABASE_URL = get_config("SUPABASE_URL")
SUPABASE_ANON_KEY = get_config("SUPABASE_ANON_KEY")
SERVICE_KEY = get_config("SUPABASE_SERVICE_ROLE_KEY")
MODERATOR_PASSWORD = get_config("MODERATOR_PASSWORD")

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    st.error(
        "Supabase is not configured. Add SUPABASE_URL and "
        "SUPABASE_ANON_KEY to .streamlit/secrets.toml."
    )
    st.stop()

try:
    db = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
except Exception as exc:
    st.error(f"Could not connect to Supabase: {exc}")
    st.stop()

admin_db = None
if SERVICE_KEY:
    try:
        admin_db = create_client(SUPABASE_URL, SERVICE_KEY)
    except Exception:
        admin_db = None


# -------------------- ANONYMOUS PROFILE --------------------

ADJECTIVES = [
    "Quiet", "Silver", "Cosmic", "Gentle", "Hidden",
    "Misty", "Brave", "Sunny", "Clever", "Velvet",
    "Lucky", "Pixel", "Calm", "Nova", "Curious",
]
ANIMALS = [
    "Fox", "Panda", "Owl", "Tiger", "Otter",
    "Falcon", "Koala", "Dolphin", "Wolf", "Robin",
    "Rabbit", "Penguin", "Turtle", "Hawk", "Whale",
]


def new_nickname():
    return (
        f"{random.choice(ADJECTIVES)}"
        f"{random.choice(ANIMALS)}"
        f"{random.randint(10, 99)}"
    )


if "nickname" not in st.session_state:
    st.session_state.nickname = new_nickname()

if "sender_token" not in st.session_state:
    st.session_state.sender_token = str(uuid.uuid4())

if "last_sent" not in st.session_state:
    st.session_state.last_sent = 0.0

if "last_report" not in st.session_state:
    st.session_state.last_report = 0.0

if "moderator" not in st.session_state:
    st.session_state.moderator = False


# -------------------- SIDEBAR --------------------

with st.sidebar:
    st.subheader("🕶️ Your anonymous profile")
    st.markdown(f"### {st.session_state.nickname}")
    st.caption("This nickname is visible to other visitors.")

    if st.button("🎲 New random nickname", use_container_width=True):
        st.session_state.nickname = new_nickname()
        st.rerun()

    st.divider()
    st.subheader("Community rules")
    st.markdown(COMMUNITY_RULES)

    st.divider()
    st.subheader("🛡️ Moderator")

    if not admin_db or not MODERATOR_PASSWORD:
        st.caption("Moderator tools are not configured.")
    elif not st.session_state.moderator:
        with st.form("moderator_login"):
            password = st.text_input(
                "Moderator password", type="password"
            )
            login = st.form_submit_button("Sign in")

        if login:
            if password == MODERATOR_PASSWORD:
                st.session_state.moderator = True
                st.rerun()
            else:
                st.error("Incorrect password.")
    else:
        st.success("Moderator mode enabled")
        if st.button("Sign out"):
            st.session_state.moderator = False
            st.rerun()


# -------------------- SEND MESSAGE --------------------

MAX_LENGTH = 1000


def send_message(raw_text):
    body = raw_text.strip()
    body = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", body)

    if not body:
        return False, "Please enter a message."

    if len(body) > MAX_LENGTH:
        return False, "Your message is too long."

    # Basic per-session cooldown, not server-side anti-spam.
    if time.time() - st.session_state.last_sent < 2.5:
        return False, "Please wait before sending another message."

    try:
        db.table("chat_messages").insert({
            "sender_token": st.session_state.sender_token,
            "nickname": st.session_state.nickname,
            "body": body,
        }).execute()

        st.session_state.last_sent = time.time()
        return True, "Message sent."
    except Exception as exc:
        return False, f"Could not send message: {exc}"


def report_message(message_id, reason):
    if time.time() - st.session_state.last_report < 5:
        return False, "Please wait before submitting another report."

    try:
        db.table("chat_reports").insert({
            "message_id": int(message_id),
            "reporter_token": st.session_state.sender_token,
            "reason": reason,
        }).execute()

        st.session_state.last_report = time.time()
        return True, "Thank you. Your report was submitted."
    except Exception as exc:
        return False, f"Could not submit report: {exc}"


# -------------------- CHAT DISPLAY --------------------

st.subheader("🌐 Public Lounge")
st.caption("All visitors share this room. Messages are saved.")


@st.fragment(run_every="3s")
def show_messages():
    try:
        result = (
            db.table("chat_messages")
            .select("id,nickname,body,created_at,sender_token")
            .order("created_at", desc=True)
            .limit(100)
            .execute()
        )
        messages = list(reversed(result.data or []))
    except Exception as exc:
        st.error(f"Could not load messages: {exc}")
        st.info("Check your Supabase settings and schema.sql.")
        return

    if not messages:
        st.info("No messages yet. Be the first to say hello!")
        return

    st.caption(
        f"{len(messages)} recent messages · refreshes automatically"
    )

    for message in messages:
        nickname = html.escape(str(message.get("nickname", "Anonymous")))
        body = html.escape(str(message.get("body", "")))
        created = message.get("created_at", "")

        try:
            dt = datetime.fromisoformat(
                created.replace("Z", "+00:00")
            ).astimezone()
            time_text = dt.strftime("%I:%M %p")
        except Exception:
            time_text = "recently"

        safe_time = html.escape(time_text)

        card_html = (
            '<div class="chat-card">'
            f'<div class="chat-body">{body}</div>'
            '</div>'
        )
        st.markdown(card_html, unsafe_allow_html=True)

        if (
            message.get("sender_token")
            != st.session_state.sender_token
        ):
            with st.expander("🚩 Report this message"):
                with st.form(f"report_{message['id']}"):
                    reason = st.selectbox(
                        "Reason",
                        [
                            "Harassment or bullying",
                            "Threat or hateful content",
                            "Spam or scam",
                            "Personal information",
                            "Other",
                        ],
                        key=f"reason_{message['id']}",
                    )
                    submitted = st.form_submit_button("Submit report")

                if submitted:
                    ok, note = report_message(message["id"], reason)
                    if ok:
                        st.success(note)
                    else:
                        st.warning(note)


show_messages()


# -------------------- MESSAGE INPUT --------------------

st.subheader("✍️ Send a message")

with st.form("send_form", clear_on_submit=True):
    draft = st.text_area(
        "Message",
        placeholder="Say hello... Please protect your privacy.",
        max_chars=MAX_LENGTH,
        height=100,
    )
    send = st.form_submit_button(
        "Send message ➤",
        type="primary",
        use_container_width=True,
    )

if send:
    ok, note = send_message(draft)
    if ok:
        st.toast(note, icon="✅")
        st.rerun()
    else:
        st.warning(note)


# -------------------- MODERATOR CONSOLE --------------------

if st.session_state.moderator and admin_db:
    st.divider()
    st.subheader("🛡️ Moderator Console")
    st.caption("Review reports before removing messages.")

    try:
        reports = (
            admin_db.table("chat_reports")
            .select("id,message_id,reason,created_at")
            .order("created_at", desc=True)
            .limit(100)
            .execute()
        ).data or []

        if not reports:
            st.info("No reports have been submitted.")

        for report in reports:
            with st.container(border=True):
                st.markdown(
                    f"**Report #{report['id']}** · "
                    f"Message #{report['message_id']}"
                )
                st.write(f"Reason: {report['reason']}")

                target = (
                    admin_db.table("chat_messages")
                    .select("nickname,body")
                    .eq("id", report["message_id"])
                    .limit(1)
                    .execute()
                ).data or []

                if not target:
                    st.caption("The reported message no longer exists.")
                    continue

                st.write(
                    f"**{target[0]['nickname']}**: {target[0]['body']}"
                )

                confirm = st.checkbox(
                    "I reviewed this message and want to delete it",
                    key=f"confirm_{report['id']}",
                )

                if st.button(
                    "Delete reported message",
                    key=f"delete_{report['id']}",
                    disabled=not confirm,
                ):
                    admin_db.table("chat_messages").delete().eq(
                        "id", report["message_id"]
                    ).execute()
                    st.success("Message deleted.")
                    st.rerun()

    except Exception as exc:
        st.error(f"Moderator error: {exc}")


# -------------------- PRIVACY NOTICE --------------------

st.divider()
st.caption(
    "Privacy: other visitors see your nickname, not your real name. "
    "This does not guarantee complete anonymity from the website host, "
    "database provider, or network operators. Avoid sharing passwords, "
    "phone numbers, addresses, or other sensitive information."
)
