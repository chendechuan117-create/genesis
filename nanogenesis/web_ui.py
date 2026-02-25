import streamlit as st
import asyncio
import sys
import json
import time
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent))

from genesis.core.factory import GenesisFactory

# Page config
st.set_page_config(page_title="Genesis OS", page_icon="🌌", layout="wide")

# Custom CSS for better aesthetics
st.markdown("""
<style>
    .stChatFloatingInputContainer { padding-bottom: 2rem; }
    .status-text { color: #888; font-style: italic; font-size: 0.9em; margin-bottom: 0.5rem; }
    .tool-call { background-color: #1E1E1E; padding: 10px; border-radius: 5px; border-left: 4px solid #00E5FF; font-family: monospace; white-space: pre-wrap; font-size: 0.85em; margin: 5px 0; color: #ddd;}
    .tool-result { background-color: #121212; padding: 10px; border-radius: 5px; border-left: 4px solid #00E676; font-family: monospace; white-space: pre-wrap; font-size: 0.85em; margin: 5px 0; color: #aaa;}
    .sys-thought { color: #BDBDBD; font-size: 0.9em; border-left: 3px solid #757575; padding-left: 10px; margin: 5px 0;}
</style>
""", unsafe_allow_html=True)

st.title("🌌 NanoGenesis 2.0 Web Terminal")
st.caption("A multi-dimensional agent execution environment. Paste anything you want in the box below; it natively supports multi-line text.")

# Initialize session state
if "agent" not in st.session_state:
    with st.spinner("Initializing Genesis Core Modules... (This might take a moment)"):
        try:
            st.session_state.agent = GenesisFactory.create_common(enable_optimization=True)
            # Boot background tasks
            if st.session_state.agent.scheduler:
                asyncio.run(st.session_state.agent.scheduler.start())
        except Exception as e:
            st.error(f"Failed to bootstrap Genesis: {e}")
            st.stop()

if "messages" not in st.session_state:
    st.session_state.messages = []

# Render chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Multi-line Chat Input
user_input = st.chat_input("Enter your complex multiline prompt or paste code here...")

if user_input:
    # 1. Show user message immediately
    with st.chat_message("user"):
        st.markdown(user_input)
    st.session_state.messages.append({"role": "user", "content": user_input})
    
    # 2. Assistant Response Placeholder
    with st.chat_message("assistant"):
        live_status = st.empty()
        live_logs = st.container()
        final_response_placeholder = st.empty()
        
        # Async wrapper for execution
        async def run_genesis():
            accumulated_log_html = ""
            log_box = live_logs.empty()
            
            async def step_callback(step_type, data):
                nonlocal accumulated_log_html
                
                if step_type == "reasoning":
                    accumulated_log_html += f"<div class='sys-thought'>{data}</div>"
                    live_status.markdown(f"**💭 Thinking...**")
                
                elif step_type == "tool":
                    name = data.get('name', 'unknown')
                    args_str = json.dumps(data.get('args', {}), ensure_ascii=False, indent=2)
                    accumulated_log_html += f"<div class='tool-call'>[EXECUTE] {name}<br/>{args_str}</div>"
                    live_status.markdown(f"**🛠️ Using Tool:** `{name}`")
                
                elif step_type == "tool_result":
                    res = str(data.get('result', ''))
                    if len(res) > 300: res = res[:300] + " ... [TRUNCATED]"
                    
                    # Escape HTML chunks safely for display
                    safe_res = res.replace('<', '&lt;').replace('>', '&gt;')
                    accumulated_log_html += f"<div class='tool-result'>[RESULT]<br/>{safe_res}</div>"
                    live_status.markdown("**✅ Tool Excution Complete**")
                
                elif step_type == "loop_start":
                    accumulated_log_html += f"<div class='status-text'>--- Ouroboros Loop Iteration {data} ---</div>"
                    live_status.markdown(f"**🔄 Starting Loop Iteration {data}...**")
                
                elif step_type == "strategy":
                    accumulated_log_html += f"<div class='status-text'>--- Strategy Phase ---</div>"
                    live_status.markdown("**🗺️ Formulating Strategy & Blueprints...**")
                
                # Update the log UI live
                log_box.markdown(accumulated_log_html, unsafe_allow_html=True)

            try:
                start_time = time.time()
                result = await st.session_state.agent.process(user_input, step_callback=step_callback)
                end_time = time.time()
                
                live_status.empty() # Clear the status spinner
                
                if result['success']:
                    response_text = result['response']
                    final_response_placeholder.markdown(response_text)
                    st.session_state.messages.append({"role": "assistant", "content": response_text})
                    
                    metrics = result.get('metrics')
                    if metrics:
                         st.caption(f"🏁 Task completed in {end_time - start_time:.1f}s | Tokens used: {metrics.total_tokens}")
                else:
                    st.error(f"Task Failed: {result['response']}")
                    
            except Exception as e:
                live_status.empty()
                st.error(f"System Error: {str(e)}")
        
        # Execute the agent securely within the Streamlit thread via asyncio
        asyncio.run(run_genesis())
