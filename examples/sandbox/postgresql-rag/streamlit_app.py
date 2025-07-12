#!/usr/bin/env python3
"""
Enhanced Streamlit Chat UI for Semantic RAG System
A conversational chat interface for querying databases with natural language
"""

import streamlit as st
import sys
import os
from datetime import datetime
from dotenv import load_dotenv, find_dotenv
from semantic_rag_system import SemanticRAGSystem
import json
from typing import Dict, List

# Load environment variables
env_file = find_dotenv()
if env_file:
    load_dotenv(env_file, override=True)

# Page configuration
st.set_page_config(
    page_title="ORBIT Chat - Database Assistant",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for chat interface
st.markdown("""
<style>
    /* Main container */
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        background: linear-gradient(90deg, #1f77b4 0%, #ff7f0e 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        margin-bottom: 1rem;
    }
    
    /* Chat messages */
    .user-message {
        background-color: #007AFF;
        color: white;
        padding: 0.75rem 1rem;
        border-radius: 18px;
        margin: 0.5rem 0;
        max-width: 70%;
        margin-left: auto;
        word-wrap: break-word;
    }
    
    .assistant-message {
        background-color: #f0f0f0;
        color: #333;
        padding: 0.75rem 1rem;
        border-radius: 18px;
        margin: 0.5rem 0;
        max-width: 70%;
        word-wrap: break-word;
    }
    
    .message-metadata {
        font-size: 0.75rem;
        color: #666;
        margin-top: 0.25rem;
    }
    
    /* Status indicators */
    .status-indicator {
        display: inline-block;
        width: 8px;
        height: 8px;
        border-radius: 50%;
        margin-right: 0.5rem;
    }
    
    .status-online {
        background-color: #4CAF50;
    }
    
    .status-error {
        background-color: #f44336;
    }
    
    /* Chat input area */
    .chat-input-container {
        position: fixed;
        bottom: 0;
        left: 0;
        right: 0;
        background-color: white;
        border-top: 1px solid #e0e0e0;
        padding: 1rem;
        z-index: 1000;
    }
    
    /* Sidebar styling */
    .sidebar-section {
        background-color: #f8f9fa;
        padding: 1rem;
        border-radius: 8px;
        margin-bottom: 1rem;
    }
    
    /* Query suggestions */
    .suggestion-pill {
        display: inline-block;
        background-color: #e3f2fd;
        color: #1976d2;
        padding: 0.4rem 0.8rem;
        border-radius: 16px;
        margin: 0.2rem;
        cursor: pointer;
        font-size: 0.875rem;
        transition: all 0.2s;
    }
    
    .suggestion-pill:hover {
        background-color: #1976d2;
        color: white;
    }
    
    /* Metrics cards */
    .metric-card {
        background-color: #ffffff;
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 1rem;
        text-align: center;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    .metric-value {
        font-size: 2rem;
        font-weight: bold;
        color: #1f77b4;
    }
    
    .metric-label {
        font-size: 0.875rem;
        color: #666;
    }
    
    /* Typing indicator */
    .typing-indicator {
        display: flex;
        align-items: center;
        padding: 0.5rem;
    }
    
    .typing-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background-color: #999;
        margin: 0 2px;
        animation: typing 1.4s infinite;
    }
    
    .typing-dot:nth-child(2) {
        animation-delay: 0.2s;
    }
    
    .typing-dot:nth-child(3) {
        animation-delay: 0.4s;
    }
    
    @keyframes typing {
        0%, 60%, 100% {
            opacity: 0.3;
        }
        30% {
            opacity: 1;
        }
    }
    
    /* Make chat scrollable */
    .chat-container {
        height: calc(100vh - 250px);
        overflow-y: auto;
        padding-bottom: 100px;
    }
</style>
""", unsafe_allow_html=True)

@st.cache_resource
def initialize_rag_system():
    """Initialize the RAG system (cached to avoid reinitializing)"""
    try:
        rag_system = SemanticRAGSystem()
        rag_system.populate_chromadb("query_templates.yaml", clear_first=True)
        return rag_system, None
    except Exception as e:
        return None, str(e)

def format_message_time(timestamp):
    """Format timestamp for display"""
    dt = datetime.fromisoformat(timestamp)
    return dt.strftime("%I:%M %p")

def render_chat_message(message: Dict, is_user: bool = True):
    """Render a single chat message"""
    # Escape any potential HTML/markdown issues in the content
    content = message["content"]
    
    # For assistant messages, ensure proper formatting
    if not is_user:
        # Fix common formatting issues
        content = content.replace("$", "\\$")  # Escape dollar signs for markdown
    
    if is_user:
        # User messages in a speech bubble
        st.markdown(f"""
        <div style="display: flex; justify-content: flex-end; margin: 0.5rem 0;">
            <div class="user-message">{content}</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        # Assistant messages
        st.markdown(f'<div class="assistant-message">{content}</div>', unsafe_allow_html=True)
        
        # Metadata below the message
        if message.get("metadata"):
            metadata = message["metadata"]
            if metadata.get("template_id"):
                st.caption(
                    f'📋 {metadata["template_id"]} • '
                    f'🎯 {metadata.get("confidence", 0):.0%} confidence • '
                    f'📊 {metadata.get("result_count", 0)} results'
                )

def get_suggested_queries(last_result: Dict = None) -> List[str]:
    """Get contextual query suggestions"""
    default_suggestions = [
        "Show me top customers",
        "Recent orders over $500",
        "Orders from New York",
        "Payment method breakdown",
        "Customer lifetime values"
    ]
    
    if not last_result or not last_result.get('success'):
        return default_suggestions
    
    template_id = last_result.get('template_id', '')
    
    # Context-aware suggestions
    if 'customer' in template_id:
        return [
            "Show their order history",
            "What's their average order size?",
            "Compare with other customers",
            "Show their payment preferences",
            "When was their first order?"
        ]
    elif 'orders' in template_id:
        return [
            "Group by customer",
            "Show payment methods used",
            "What's the average order value?",
            "Show order trends",
            "Find similar orders"
        ]
    elif 'payment' in template_id:
        return [
            "Compare with last month",
            "Show trends over time",
            "Which method is growing fastest?",
            "Customer preferences by location",
            "Average order size by payment type"
        ]
    else:
        return default_suggestions

def render_sidebar():
    """Render the sidebar with system info and controls"""
    with st.sidebar:
        # System Status
        st.markdown("### 🟢 System Status")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown('<span class="status-indicator status-online"></span>**Online**', unsafe_allow_html=True)
        with col2:
            if st.button("🔄 Restart"):
                st.cache_resource.clear()
                st.rerun()
        
        # Configuration
        with st.expander("⚙️ Configuration", expanded=False):
            st.markdown("**Database:**")
            st.code(os.getenv('DATASOURCE_POSTGRES_DATABASE', 'orbit'))
            
            st.markdown("**Models:**")
            st.code(f"Embedding: {os.getenv('OLLAMA_EMBEDDING_MODEL', 'nomic-embed-text')}")
            st.code(f"Inference: {os.getenv('OLLAMA_INFERENCE_MODEL', 'gemma3:1b')}")
        
        # Quick Stats
        st.markdown("### 📊 Session Stats")
        if 'messages' in st.session_state:
            user_messages = [m for m in st.session_state.messages if m['role'] == 'user']
            assistant_messages = [m for m in st.session_state.messages if m['role'] == 'assistant']
            
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f'<div class="metric-card"><div class="metric-value">{len(user_messages)}</div>'
                          f'<div class="metric-label">Queries</div></div>', unsafe_allow_html=True)
            with col2:
                success_count = sum(1 for m in assistant_messages if m.get('metadata', {}).get('success', False))
                st.markdown(f'<div class="metric-card"><div class="metric-value">{success_count}</div>'
                          f'<div class="metric-label">Successful</div></div>', unsafe_allow_html=True)
        
        # Help Section
        with st.expander("❓ How to Use", expanded=False):
            st.markdown("""
            **Natural Language Queries:**
            - Ask questions in plain English
            - Be specific with names, dates, amounts
            - Use relative time (yesterday, last week)
            
            **Example Patterns:**
            - "What did [customer] buy [time period]?"
            - "Show orders over $[amount]"
            - "Find [status] orders"
            - "Orders from [location]"
            - "How are customers paying?"
            
            **Tips:**
            - Click suggested queries for ideas
            - The system maintains context
            - Ask follow-up questions
            """)
        
        # Clear Chat
        if st.button("🗑️ Clear Chat", use_container_width=True):
            st.session_state.messages = []
            st.session_state.last_result = None
            if 'rag_system' in st.session_state:
                st.session_state.rag_system.clear_conversation()
            st.rerun()

def main():
    """Main chat application"""
    # Header
    st.markdown('<h1 class="main-header">💬 ORBIT Chat Assistant</h1>', unsafe_allow_html=True)
    st.markdown("*Your conversational database interface*")
    
    # Initialize session state
    if 'messages' not in st.session_state:
        st.session_state.messages = []
        # Add welcome message
        st.session_state.messages.append({
            "role": "assistant",
            "content": "👋 Hello! I'm your database assistant. I can help you query your customer and order data using natural language. What would you like to know?",
            "timestamp": datetime.now().isoformat()
        })
    
    if 'last_result' not in st.session_state:
        st.session_state.last_result = None
    
    # Initialize RAG system
    if 'rag_system' not in st.session_state:
        with st.spinner("🚀 Initializing system..."):
            rag_system, error = initialize_rag_system()
            if error:
                st.error(f"❌ System initialization failed: {error}")
                st.stop()
            st.session_state.rag_system = rag_system
    
    # Render sidebar
    render_sidebar()
    
    # Chat container
    chat_container = st.container()
    
    # Display chat messages
    with chat_container:
        for message in st.session_state.messages:
            render_chat_message(message, is_user=(message["role"] == "user"))
    
    # Suggested queries
    suggestions = get_suggested_queries(st.session_state.last_result)
    st.markdown("**💡 Suggested queries:**")
    cols = st.columns(len(suggestions))
    for i, (col, suggestion) in enumerate(zip(cols, suggestions)):
        with col:
            if st.button(suggestion, key=f"suggestion_{i}", use_container_width=True):
                # Process suggested query
                st.session_state.pending_query = suggestion
                st.rerun()
    
    # Chat input
    st.markdown("---")
    
    # Create a form for better input handling
    with st.form(key="chat_form", clear_on_submit=True):
        col1, col2 = st.columns([6, 1])
        
        with col1:
            user_input = st.text_input(
                "Ask a question:",
                placeholder="e.g., Show me orders from Maria Smith",
                key="user_input_field",
                label_visibility="collapsed"
            )
        
        with col2:
            send_button = st.form_submit_button("Send 📤", type="primary", use_container_width=True)
    
    # Process pending query from suggestions
    if hasattr(st.session_state, 'pending_query'):
        user_input = st.session_state.pending_query
        del st.session_state.pending_query
        send_button = True
    
    # Process user input
    if send_button and user_input:
        # Add user message
        st.session_state.messages.append({
            "role": "user",
            "content": user_input,
            "timestamp": datetime.now().isoformat()
        })
        
        # Show typing indicator
        with st.spinner(""):
            # Process query
            result = st.session_state.rag_system.process_query(user_input)
            
            # Prepare assistant message
            assistant_message = {
                "role": "assistant",
                "content": result.get('response', 'I encountered an error processing your request.'),
                "timestamp": datetime.now().isoformat(),
                "metadata": {
                    "success": result.get('success', False),
                    "template_id": result.get('template_id'),
                    "confidence": result.get('similarity', 0),
                    "result_count": result.get('result_count', 0),
                    "parameters": result.get('parameters', {})
                }
            }
            
            # Add assistant message
            st.session_state.messages.append(assistant_message)
            st.session_state.last_result = result
        
        # Clear input and rerun
        st.rerun()
    
    # Auto-scroll to bottom
    st.markdown("""
    <script>
        var chatContainer = document.querySelector('.chat-container');
        if (chatContainer) {
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }
    </script>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()