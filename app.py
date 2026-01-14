import os
import re
import fitz  # PyMuPDF
import streamlit as st
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, ToolMessage, AIMessage

load_dotenv()

# --- 0. UI Configuration ---
st.set_page_config(page_title="🎯 Job Application Assistant", page_icon="🤖", layout="wide")

# --- 1. State Management ---
if "application_info" not in st.session_state:
    st.session_state.application_info = {"name": None, "email": None, "skills": None}
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# --- 2. Tools & Regex Helpers ---
@tool
def extract_application_info(name: str = None, email: str = None, skills: str = None) -> str:
    """Save user information found in the text."""
    res = []
    if name: res.append(f"SET_NAME:{name.title()}")
    if email: res.append(f"SET_EMAIL:{email.lower()}")
    if skills: res.append(f"SET_SKILLS:{skills.strip()}")
    return " | ".join(res) if res else "ℹ️ No info parsed."

def extract_info_from_cv(text: str):
    """Local regex pass for fast extraction."""
    extracted = {"name": None, "email": None, "skills": None}
    name_m = re.search(r"(?:Full Name:|Name:)\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)", text, re.IGNORECASE)
    email_m = re.search(r"\b[\w\.-]+@[\w\.-]+\.\w+\b", text)
    skills_m = re.search(r"Skills\s*[:\-]*\s*(.*?)(?:\n\s*\n|Projects|Certifications|Education|$)", text, re.DOTALL | re.IGNORECASE)

    if name_m: extracted["name"] = name_m.group(1).strip()
    if email_m: extracted["email"] = email_m.group(0).strip()
    if skills_m:
        s = skills_m.group(1).replace("\n", ", ").replace("-", "").strip()
        extracted["skills"] = re.sub(r"\s+", " ", s)
    return extracted

# --- 3. Agent & State Sync ---
llm = ChatGoogleGenerativeAI(
    model=os.getenv("AI_MODEL", "gemini-flash-latest"), 
    google_api_key=os.getenv("GOOGLE_API_KEY"),
    temperature=0
)

def get_system_prompt():
    info = st.session_state.application_info
    missing = [k for k, v in info.items() if not v]
    status = f"Status: {info}. Missing: {missing}."
    return f"""You are a helpful job assistant. Collect name, email, and skills.
{status}

**Rules for Ambiguity:**
- If you find multiple potential values for a field (e.g., two different emails in a CV), DO NOT guess.
- Instead, point them out to the user and ask: "I found multiple emails: [Email A] and [Email B]. Which one should I use?"
- Only call extract_application_info once the user confirms or if the value is unambiguous.

Use extract_application_info to save data. Once all 3 fields are present, congratulate the user!
"""

def sync_info_from_messages(messages):
    updated = False
    for msg in messages:
        if isinstance(msg, ToolMessage):
            content = str(msg.content)
            if "SET_NAME:" in content:
                st.session_state.application_info["name"] = content.split("SET_NAME:")[1].split(" | ")[0].strip()
                updated = True
            if "SET_EMAIL:" in content:
                st.session_state.application_info["email"] = content.split("SET_EMAIL:")[1].split(" | ")[0].strip()
                updated = True
            if "SET_SKILLS:" in content:
                st.session_state.application_info["skills"] = content.split("SET_SKILLS:")[1].split(" | ")[0].strip()
                updated = True
    return updated

# --- 4. Streamlit UI Layout ---
st.title("Job Application Assistant")

st.markdown("""
### 🎯 Showcase: Goal-Based AI Agent
This application demonstrates a **Goal-Based AI Agent** built with **LangGraph** and **Google Gemini 2.0**. 

**The Agent's Goal:** To persistently collect and verify three specific pieces of information—**Name, Email, and Skills**—before certifying the application as complete.

**Technical Highlights:**
- **Autonomous Reasoning**: The agent decides which tools to call based on your input.
- **Dual-Pass Extraction**: Combines high-speed Regex patterns with deep LLM reasoning for accurate resume parsing.
- **Thread-Safe State**: Uses a custom synchronization layer to manage agent "thoughts" within the Streamlit UI safely.
---
""")

# Sidebar
with st.sidebar:
    st.header("📊 Application Tracker")
    for key, val in st.session_state.application_info.items():
        if val: st.success(f"**{key.capitalize()}:** {val}")
        else: st.error(f"**{key.capitalize()}:** Missing")
    
    st.divider()
    
    # Resume Upload
    res_file = st.file_uploader("Upload Resume (PDF)", type="pdf")
    if res_file and st.button("Parse Resume"):
        with st.spinner("Analyzing PDF..."):
            with fitz.open(stream=res_file.read(), filetype="pdf") as doc:
                text = "".join([p.get_text() for p in doc])
            if text.strip():
                # Regex Pass
                reg = extract_info_from_cv(text)
                for k, v in reg.items():
                    if v and not st.session_state.application_info[k]: st.session_state.application_info[k] = v
                # AI Pass
                agent = create_react_agent(model=llm, tools=[extract_application_info], prompt=get_system_prompt())
                res = agent.invoke({"messages": [HumanMessage(content=f"Extract info from: {text[:3000]}")]})
                sync_info_from_messages(res["messages"])
                st.session_state.chat_history.append(("assistant", res["messages"][-1].content))
                st.rerun()

    # Reset Button
    if st.button("🔄 Reset Application"):
        st.session_state.application_info = {"name": None, "email": None, "skills": None}
        st.session_state.chat_history = []
        st.rerun()

    # Download Button
    if all(st.session_state.application_info.values()):
        summary = f"RESUME SUMMARY\n---\nName: {st.session_state.application_info['name']}\nEmail: {st.session_state.application_info['email']}\nSkills: {st.session_state.application_info['skills']}"
        st.download_button("📥 Download Summary", data=summary, file_name="application_summary.txt")

# Chat UI
for role, content in st.session_state.chat_history:
    avatar = "🧑" if role == "user" else "🤖"
    with st.chat_message(role, avatar=avatar):
        st.markdown(content)

if user_input := st.chat_input("Tell me about yourself..."):
    st.session_state.chat_history.append(("user", user_input))
    with st.chat_message("user", avatar="🧑"):
        st.markdown(user_input)

    with st.spinner("Thinking..."):
        msg_ctx = [HumanMessage(content=c) if r=="user" else AIMessage(content=c) for r,c in st.session_state.chat_history]
        agent = create_react_agent(model=llm, tools=[extract_application_info], prompt=get_system_prompt())
        response = agent.invoke({"messages": msg_ctx})
        
        state_changed = sync_info_from_messages(response["messages"])
        bot_msg = response["messages"][-1].content
        st.session_state.chat_history.append(("assistant", bot_msg))
        
        if state_changed: st.rerun()
        else:
            with st.chat_message("assistant", avatar="🤖"):
                st.markdown(bot_msg)
                if all(st.session_state.application_info.values()):
                    st.balloons()
                    st.success("🎉 Ready to apply!")