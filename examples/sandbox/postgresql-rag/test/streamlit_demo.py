#!/usr/bin/env python3
"""
Enhanced Streamlit Demo for ORBIT Database Chat PoC
Clean, user-friendly interface with conversation features
"""

import streamlit as st
import pandas as pd
from datetime import datetime
import json
import os
from typing import Dict, List
from dotenv import load_dotenv
import markdown

# Import the new domain-agnostic RAG system components
from base_rag_system import RAGSystem
from domain_configuration import DomainConfiguration, DomainEntity, DomainField, DomainRelationship
from domain_configuration import DataType, EntityType, RelationType
from template_library import TemplateLibrary
from domain_plugin import DomainSpecificPlugin, DomainAnalyticsPlugin
from template_generator import DomainTemplateGenerator
from plugin_system import PluginManager
from shared_domain_config import create_customer_order_domain
from shared_template_loader import load_or_generate_templates

# Import the actual implementations
from clients import (
    OllamaEmbeddingClient, 
    OllamaInferenceClient, 
    PostgreSQLDatabaseClient
)

# Import plugins
from plugin_system import (
    SecurityPlugin,
    QueryNormalizationPlugin,
    ResultFilteringPlugin,
    DataEnrichmentPlugin,
    ResponseEnhancementPlugin,
    LoggingPlugin
)

# Import example plugins if available
try:
    from examples.example_plugins import (
        CustomerSegmentationPlugin,
        RevenueAnalyticsPlugin,
        TimeBasedInsightsPlugin,
        GeographicInsightsPlugin,
        BusinessRulesPlugin
    )
    EXAMPLE_PLUGINS_AVAILABLE = True
except ImportError:
    EXAMPLE_PLUGINS_AVAILABLE = False


class StreamlitRAGDemo:
    """Enhanced Streamlit demo with conversation features"""
    
    def __init__(self):
        self.example_queries = {
            "🛍️ Customer Queries": [
                "What did customer 123 buy last week?",
                "Show me orders from John Smith",
                "Give me a summary for customer 5",
                "Find customers with more than 5 orders"
            ],
            "💰 Order Value": [
                "Show me all orders over $500",
                "Find orders between $100 and $500",
                "What are the biggest orders this month?",
                "Average order value by customer"
            ],
            "📦 Order Status": [
                "Show me all pending orders",
                "Which orders are delivered?",
                "Find cancelled orders from last week",
                "Orders that need attention"
            ],
            "🌍 International": [
                "Show orders shipped to the United States",
                "Orders delivered to European countries",
                "International orders over $200",
                "Canadian customers shipping abroad"
            ],
            "📍 Location-Based": [
                "Show orders from Toronto customers",
                "Orders from customers in Canada",
                "Which cities are ordering the most?",
                "Customers from Vancouver"
            ],
            "💳 Payment Analysis": [
                "How are customers paying?",
                "Show me credit card orders",
                "PayPal transactions from last month",
                "Payment method distribution"
            ],
            "📈 Analytics": [
                "Who are our top 10 customers?",
                "Show me new customers this week",
                "How are sales trending?",
                "Show inactive customers"
            ]
        }
    
    def suggest_followup(self, result: Dict) -> List[str]:
        """Generate follow-up suggestions based on query result"""
        if not result.get('success'):
            return []
        
        template_id = result.get('template_id', '').lower()
        
        if 'customer' in template_id:
            return [
                "Show their lifetime value",
                "What's their average order size?",
                "When was their last order?"
            ]
        elif 'orders' in template_id:
            return [
                "Show top customers from these results",
                "What's the average order value?",
                "Break this down by payment method"
            ]
        elif 'payment' in template_id:
            return [
                "Which payment method is most popular?",
                "Show trends over time",
                "Compare with last month"
            ]
        elif 'international' in template_id or 'shipping' in template_id:
            return [
                "Show revenue by shipping destination",
                "Which countries order the most?",
                "International payment methods used"
            ]
        elif 'location' in template_id or 'city' in template_id:
            return [
                "Show international shipping from this location",
                "Compare with other cities",
                "Revenue by geographic region"
            ]
        
        return []
    
    
# Domain creation function moved to shared_domain_config.py for consistency


# Template loading function moved to shared_template_loader.py for consistency


def initialize_system():
    """Initialize the RAG system with proper error handling"""
    try:
        with st.spinner("🚀 Initializing RAG system with domain configuration..."):
            # Create domain configuration
            domain = create_customer_order_domain()
            
            # Initialize clients
            embedding_client = OllamaEmbeddingClient()
            inference_client = OllamaInferenceClient()
            db_client = PostgreSQLDatabaseClient()
            
            # Load or generate templates
            template_library = load_or_generate_templates(domain)
            
            # Initialize the RAG system
            rag_system = RAGSystem(
                domain=domain,
                template_library=template_library,
                embedding_client=embedding_client,
                inference_client=inference_client,
                db_client=db_client
            )
            
            # Register plugins
            plugin_manager = PluginManager()
            
            # Register default plugins
            default_plugins = [
                SecurityPlugin(),
                QueryNormalizationPlugin(),
                ResultFilteringPlugin(max_results=50),
                DataEnrichmentPlugin(),
                ResponseEnhancementPlugin(),
                LoggingPlugin()
            ]
            
            for plugin in default_plugins:
                plugin_manager.register_plugin(plugin)
            
            # Register domain-specific plugin
            domain_plugin = DomainSpecificPlugin(domain, inference_client)
            plugin_manager.register_plugin(domain_plugin)
            
            analytics_plugin = DomainAnalyticsPlugin(domain)
            plugin_manager.register_plugin(analytics_plugin)
            
            # Register example plugins if available
            if EXAMPLE_PLUGINS_AVAILABLE:
                example_plugins = [
                    CustomerSegmentationPlugin(),
                    RevenueAnalyticsPlugin(),
                    TimeBasedInsightsPlugin(),
                    GeographicInsightsPlugin(),
                    BusinessRulesPlugin()
                ]
                for plugin in example_plugins:
                    plugin_manager.register_plugin(plugin)
            
            # Attach plugin manager to RAG system
            rag_system.plugin_manager = plugin_manager
            
            # Populate ChromaDB
            rag_system.populate_chromadb_from_library(clear_first=True)
            
            return rag_system, None
    except Exception as e:
        error_msg = f"System initialization failed: {str(e)}\n\n"
        error_msg += "**Troubleshooting:**\n"
        error_msg += f"1. Ensure Ollama is running at {os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')}\n"
        error_msg += f"2. Pull required models:\n"
        error_msg += f"   - `ollama pull {os.getenv('OLLAMA_EMBEDDING_MODEL', 'nomic-embed-text')}`\n"
        error_msg += f"   - `ollama pull {os.getenv('OLLAMA_INFERENCE_MODEL', 'gemma3:1b')}`\n"
        error_msg += "3. Check PostgreSQL connection settings in ../.env file"
        return None, error_msg


def main():
    """Main Streamlit application"""
    st.set_page_config(
        page_title="ORBIT Database Chat PoC",
        page_icon="🤖",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Initialize demo helper
    demo = StreamlitRAGDemo()
    
    # Custom CSS for light blue theme with Mona Sans
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Mona+Sans:wght@300;400;500;600;700&display=swap');
    
    /* Global font and theme */
    .stApp {
        font-family: 'Mona Sans', -apple-system, BlinkMacSystemFont, sans-serif;
        background: #ffffff;
        color: #1f2937;
    }
    
    /* Main header */
    .main-header {
        font-size: 2.5rem;
        font-weight: 600;
        color: #1e40af;
        text-align: center;
        margin-bottom: 1rem;
        font-family: 'Mona Sans', sans-serif;
        width: 100%;
        display: block;
        margin-left: auto;
        margin-right: auto;
    }
    
    /* Sub header */
    .sub-header {
        font-size: 1.2rem;
        color: #374151;
        text-align: center;
        margin-bottom: 1.5rem;
        margin-top: 0.5rem;
        font-family: 'Mona Sans', sans-serif;
        font-weight: 400;
        width: 100%;
        display: block;
        margin-left: auto;
        margin-right: auto;
    }
    
    /* Example categories */
    .example-category {
        background: #ffffff;
        padding: 1rem;
        border-radius: 12px;
        margin: 0.5rem 0;
        border-left: 4px solid #3b82f6;
        box-shadow: 0 2px 8px rgba(59, 130, 246, 0.1);
        font-family: 'Mona Sans', sans-serif;
        color: #1f2937;
    }
    
    /* Followup suggestions */
    .followup-suggestion {
        background: #eff6ff;
        padding: 0.8rem;
        border-radius: 8px;
        margin: 0.3rem 0;
        border-left: 3px solid #3b82f6;
        font-family: 'Mona Sans', sans-serif;
        color: #1f2937;
    }
    
    /* Response container */
    .response-container {
        background: #ffffff;
        padding: 1.5rem;
        border-radius: 12px;
        border-left: 4px solid #10b981;
        margin: 1rem 0;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
        font-family: 'Mona Sans', sans-serif;
        color: #1f2937;
    }
    
    /* Error container */
    .error-container {
        background: #fef2f2;
        padding: 1.5rem;
        border-radius: 12px;
        border-left: 4px solid #ef4444;
        margin: 1rem 0;
        box-shadow: 0 4px 12px rgba(239, 68, 68, 0.1);
        font-family: 'Mona Sans', sans-serif;
        color: #1f2937;
    }
    
    /* Stats container */
    .stats-container {
        background: #ffffff;
        padding: 1rem;
        border-radius: 8px;
        margin: 0.5rem 0;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
        font-family: 'Mona Sans', sans-serif;
        color: #1f2937;
    }
    
    /* Custom button styling */
    .stButton > button {
        background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%);
        color: white;
        border: none;
        border-radius: 8px;
        padding: 0.5rem 1.5rem;
        font-family: 'Mona Sans', sans-serif;
        font-weight: 500;
        transition: all 0.2s ease;
        box-shadow: 0 2px 8px rgba(59, 130, 246, 0.3);
        width: auto !important;
        min-width: 120px !important;
        max-width: 200px !important;
    }
    
    .stButton > button:hover {
        background: linear-gradient(135deg, #2563eb 0%, #1e40af 100%);
        box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4);
        transform: translateY(-1px);
    }
    
    /* Sidebar styling - Light theme */
    .css-1d391kg, .css-1lcbmhc, .css-1d391kg > div {
        background: #ffffff !important;
        border-right: 1px solid #e2e8f0 !important;
        color: #1f2937 !important;
    }
    
    /* Sidebar text styling */
    .css-1d391kg h1, .css-1d391kg h2, .css-1d391kg h3, 
    .css-1d391kg p, .css-1d391kg div, .css-1d391kg span {
        color: #1f2937 !important;
        font-family: 'Mona Sans', sans-serif !important;
    }
    
    /* Sidebar success message */
    .css-1d391kg .stSuccess {
        background: #d1fae5 !important;
        color: #065f46 !important;
        border: 1px solid #10b981 !important;
    }
    
    /* Input fields */
    .stTextInput > div > div > input {
        border-radius: 8px;
        border: 2px solid #e2e8f0;
        font-family: 'Mona Sans', sans-serif;
        color: #1f2937;
        background-color: #ffffff !important;
        caret-color: #3b82f6 !important;
        caret-shape: block !important;
    }
    
    .stTextInput > div > div > input:focus {
        border-color: #3b82f6;
        box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
        background-color: #ffffff !important;
        outline: none !important;
        caret-color: #3b82f6 !important;
        caret-shape: block !important;
    }
    
    /* Ensure cursor is visible and blinking */
    .stTextInput input {
        caret-color: #3b82f6 !important;
        caret-shape: block !important;
    }
    
    .stTextInput input:focus {
        caret-color: #3b82f6 !important;
        caret-shape: block !important;
    }
    
    /* Dataframe styling */
    .stDataFrame {
        border-radius: 8px;
        overflow: hidden;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
    }
    
    /* General text color override */
    .stMarkdown, .stText, .stWrite {
        color: #1f2937 !important;
    }
    
    /* Expander styling */
    .streamlit-expanderHeader {
        background: #ffffff !important;
        color: #1f2937 !important;
        font-family: 'Mona Sans', sans-serif !important;
        border-radius: 8px !important;
        border: 1px solid #e2e8f0 !important;
    }
    
    .streamlit-expanderContent {
        background: #f8fafc !important;
        color: #1f2937 !important;
        font-family: 'Mona Sans', sans-serif !important;
    }
    
    /* Dataframe/Table styling - Light theme */
    .stDataFrame, .stDataFrame > div, .stDataFrame table {
        background: #ffffff !important;
        color: #1f2937 !important;
    }
    
    .stDataFrame th {
        background: #f8fafc !important;
        color: #1f2937 !important;
        border: 1px solid #e2e8f0 !important;
        font-family: 'Mona Sans', sans-serif !important;
        font-weight: 600 !important;
    }
    
    .stDataFrame td {
        background: #ffffff !important;
        color: #1f2937 !important;
        border: 1px solid #e2e8f0 !important;
        font-family: 'Mona Sans', sans-serif !important;
    }
    
    .stDataFrame tr:nth-child(even) {
        background: #f8fafc !important;
    }
    
    .stDataFrame tr:hover {
        background: #eff6ff !important;
    }
    
    /* Comprehensive sidebar and menu styling */
    .css-1d391kg, .css-1lcbmhc, .css-1d391kg > div, 
    .css-1d391kg section, .css-1d391kg .block-container,
    .css-1d391kg .main .block-container {
        background: #ffffff !important;
        color: #1f2937 !important;
    }
    
    /* Sidebar headers and text */
    .css-1d391kg h1, .css-1d391kg h2, .css-1d391kg h3,
    .css-1d391kg h4, .css-1d391kg h5, .css-1d391kg h6,
    .css-1d391kg p, .css-1d391kg div, .css-1d391kg span,
    .css-1d391kg label, .css-1d391kg strong, .css-1d391kg em {
        color: #1f2937 !important;
        font-family: 'Mona Sans', sans-serif !important;
    }
    
    /* Sidebar success button */
    .css-1d391kg .stSuccess, .css-1d391kg .stSuccess > div {
        background: #d1fae5 !important;
        color: #065f46 !important;
        border: 1px solid #10b981 !important;
        font-family: 'Mona Sans', sans-serif !important;
        font-weight: 600 !important;
    }
    
    /* Make System Ready text darker and more readable */
    .css-1d391kg .stSuccess, .css-1d391kg .stSuccess > div,
    .css-1d391kg .stSuccess p, .css-1d391kg .stSuccess span,
    .css-1d391kg .stSuccess div, .stSuccess, .stSuccess > div,
    .stSuccess p, .stSuccess span, .stSuccess div,
    .stSuccess strong, .stSuccess em {
        color: #064e3b !important;
        font-weight: 600 !important;
        font-size: 1.1rem !important;
    }
    
    /* Override any Streamlit success styling */
    .stSuccess, .stSuccess * {
        color: #064e3b !important;
        font-weight: 600 !important;
    }
    
    /* Sidebar button styling */
    .css-1d391kg .stButton > button {
        background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%) !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        padding: 0.5rem 1.5rem !important;
        font-family: 'Mona Sans', sans-serif !important;
        font-weight: 500 !important;
        transition: all 0.2s ease !important;
        box-shadow: 0 2px 8px rgba(59, 130, 246, 0.3) !important;
    }
    
    .css-1d391kg .stButton > button:hover {
        background: linear-gradient(135deg, #2563eb 0%, #1e40af 100%) !important;
        box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4) !important;
        transform: translateY(-1px) !important;
    }
    
    /* Override any remaining dark elements */
    [data-testid="stSidebar"], [data-testid="stSidebar"] > div,
    [data-testid="stSidebar"] section, [data-testid="stSidebar"] .block-container {
        background: #ffffff !important;
        color: #1f2937 !important;
    }
    
    /* Main content area styling */
    .main .block-container {
        background: transparent !important;
    }
    
    /* Ensure the main content starts at the top without header interference */
    .main .block-container > div:first-child {
        margin-top: 0 !important;
        padding-top: 0 !important;
    }
    
    /* Remove any top margin/padding that might be causing spacing issues */
    .stApp > div > div > div > div > div:first-child {
        margin-top: 0 !important;
        padding-top: 0 !important;
    }
    
    /* Override any Streamlit default dark themes */
    .stApp > div > div > div > div {
        background: transparent !important;
    }
    
    /* Fix the dark header bar at the top */
    .stApp > header {
        background: transparent !important;
        background-color: transparent !important;
    }
    
    /* Override Streamlit's default header styling */
    .stApp > header > div {
        background: transparent !important;
        background-color: transparent !important;
    }
    
    /* Remove any header background */
    header, header * {
        background: transparent !important;
        background-color: transparent !important;
    }
    
    /* Ensure all text elements are dark */
    .stMarkdown, .stText, .stWrite, .stHeader, .stSubheader {
        color: #1f2937 !important;
    }
    
    /* Make example dropdown text bigger */
    .streamlit-expanderHeader, .streamlit-expanderHeader *,
    [data-testid="stExpander"] .streamlit-expanderHeader {
        font-size: 1.1rem !important;
        font-weight: 500 !important;
        color: #1f2937 !important;
    }
    
    /* Example query buttons - make text bigger and equal width */
    .css-1d391kg .stButton > button,
    .main .stButton > button,
    .stButton > button,
    [data-testid="stButton"] > button {
        font-size: 1rem !important;
        font-weight: 500 !important;
        width: 100% !important;
        min-width: 280px !important;
        max-width: 320px !important;
        text-align: center !important;
        white-space: normal !important;
        word-wrap: break-word !important;
        padding: 0.75rem 1rem !important;
    }
    
    /* Force all expander content to have larger text */
    .streamlit-expanderContent, .streamlit-expanderContent *,
    [data-testid="stExpander"] .streamlit-expanderContent {
        font-size: 1rem !important;
        font-weight: 400 !important;
        color: #1f2937 !important;
    }
    
    /* Force table to be light with dark text - Enhanced styling */
    .stDataFrame, .stDataFrame > div, .stDataFrame table,
    .stDataFrame thead, .stDataFrame tbody, .stDataFrame tr,
    .stDataFrame th, .stDataFrame td,
    [data-testid="stDataFrame"], [data-testid="stDataFrame"] > div,
    [data-testid="stDataFrame"] table, [data-testid="stDataFrame"] thead,
    [data-testid="stDataFrame"] tbody, [data-testid="stDataFrame"] tr,
    [data-testid="stDataFrame"] th, [data-testid="stDataFrame"] td {
        background: #ffffff !important;
        background-color: #ffffff !important;
        color: #1f2937 !important;
        border-color: #e2e8f0 !important;
        font-family: 'Mona Sans', sans-serif !important;
    }
    
    /* Table header styling - Light background with dark text */
    .stDataFrame thead th,
    [data-testid="stDataFrame"] thead th {
        background: #f1f5f9 !important;
        background-color: #f1f5f9 !important;
        color: #0f172a !important;
        font-weight: 600 !important;
        border: 1px solid #cbd5e1 !important;
        font-family: 'Mona Sans', sans-serif !important;
        font-size: 0.95rem !important;
    }
    
    /* Table body styling - White background with dark text */
    .stDataFrame tbody tr,
    [data-testid="stDataFrame"] tbody tr {
        background: #ffffff !important;
        background-color: #ffffff !important;
    }
    
    .stDataFrame tbody tr:nth-child(even),
    [data-testid="stDataFrame"] tbody tr:nth-child(even) {
        background: #f8fafc !important;
        background-color: #f8fafc !important;
    }
    
    .stDataFrame tbody tr:hover,
    [data-testid="stDataFrame"] tbody tr:hover {
        background: #e2e8f0 !important;
        background-color: #e2e8f0 !important;
    }
    
    .stDataFrame tbody td,
    [data-testid="stDataFrame"] tbody td {
        background: inherit !important;
        color: #1f2937 !important;
        border: 1px solid #e2e8f0 !important;
        font-family: 'Mona Sans', sans-serif !important;
        font-size: 0.9rem !important;
    }
    
    /* Override any Streamlit dark table themes */
    .stDataFrame [data-testid="stDataFrame"],
    [data-testid="stDataFrame"] {
        background: #ffffff !important;
        background-color: #ffffff !important;
        color: #1f2937 !important;
    }
    
    /* Additional overrides for table container */
    .stDataFrame > div:first-child,
    [data-testid="stDataFrame"] > div:first-child {
        background: #ffffff !important;
        background-color: #ffffff !important;
        border-radius: 8px !important;
        border: 1px solid #e2e8f0 !important;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05) !important;
    }
    
    /* Comprehensive table overrides to force light theme */
    .stDataFrame table tbody tr td,
    .stDataFrame div[data-testid="stDataFrame"] table tbody tr td,
    div[data-testid="stDataFrame"] table tbody tr td,
    .stDataFrame .dataframe tbody tr td,
    .stDataFrame .dataframe thead tr th,
    .dataframe tbody tr td,
    .dataframe thead tr th {
        background-color: #ffffff !important;
        background: #ffffff !important;
        color: #1f2937 !important;
        border: 1px solid #e2e8f0 !important;
        font-family: 'Mona Sans', sans-serif !important;
    }
    
    /* Header cells specific styling */
    .stDataFrame table thead tr th,
    .stDataFrame div[data-testid="stDataFrame"] table thead tr th,
    div[data-testid="stDataFrame"] table thead tr th,
    .dataframe thead tr th {
        background-color: #f1f5f9 !important;
        background: #f1f5f9 !important;
        color: #0f172a !important;
        font-weight: 600 !important;
        border: 1px solid #cbd5e1 !important;
        font-family: 'Mona Sans', sans-serif !important;
    }
    
    /* Table container and wrapper overrides */
    .stDataFrame,
    .stDataFrame > div,
    .stDataFrame > div > div,
    div[data-testid="stDataFrame"],
    div[data-testid="stDataFrame"] > div,
    div[data-testid="stDataFrame"] > div > div {
        background: #ffffff !important;
        background-color: #ffffff !important;
    }
    
    /* Override any dark theme classes */
    .stDataFrame .stDataFrame,
    .stDataFrame [class*="dark"],
    div[data-testid="stDataFrame"] [class*="dark"],
    .stDataFrame [class*="Dark"],
    div[data-testid="stDataFrame"] [class*="Dark"] {
        background: #ffffff !important;
        background-color: #ffffff !important;
        color: #1f2937 !important;
    }
    
    /* Force alternating row colors */
    .stDataFrame table tbody tr:nth-child(odd),
    div[data-testid="stDataFrame"] table tbody tr:nth-child(odd),
    .dataframe tbody tr:nth-child(odd) {
        background: #ffffff !important;
        background-color: #ffffff !important;
    }
    
    .stDataFrame table tbody tr:nth-child(even),
    div[data-testid="stDataFrame"] table tbody tr:nth-child(even),
    .dataframe tbody tr:nth-child(even) {
        background: #f8fafc !important;
        background-color: #f8fafc !important;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Header
    st.markdown('<h1 class="main-header">🤖 ORBIT Database Chat PoC</h1>', unsafe_allow_html=True)
    st.markdown('<h3 class="sub-header">Natural Language Database Queries</h3>', unsafe_allow_html=True)
    
    # Initialize system
    if 'rag_system' not in st.session_state:
        rag_system, error = initialize_system()
        if rag_system:
            st.session_state.rag_system = rag_system
            st.session_state.initialization_error = None
        else:
            st.session_state.rag_system = None
            st.session_state.initialization_error = error
    
    # Show initialization error if any
    if st.session_state.initialization_error:
        st.error("❌ **System Initialization Failed**")
        st.markdown(f'<div class="error-container">{st.session_state.initialization_error}</div>', 
                   unsafe_allow_html=True)
        return
    
    # Initialize session state
    if 'query_history' not in st.session_state:
        st.session_state.query_history = []
    if 'last_result' not in st.session_state:
        st.session_state.last_result = None
    if 'selected_query' not in st.session_state:
        st.session_state.selected_query = ""
    
    # Sidebar
    with st.sidebar:
        st.header("⚙️ System Control")
        
        # System status
        st.markdown("""
        <div style="background-color: transparent; color: #1f2937; padding: 0.5rem 0; font-family: 'Mona Sans', sans-serif; font-weight: 600; font-size: 1.1rem; border: none;">
            ✅ System Ready
        </div>
        """, unsafe_allow_html=True)
        
        # Plugin information removed as requested
        
        # System configuration
        st.subheader("🔧 Configuration")
        st.write(f"**Inference:** {os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')}")
        st.write(f"**Embedding:** {os.getenv('OLLAMA_EMBEDDING_MODEL', 'nomic-embed-text')}")
        st.write(f"**Inference:** {os.getenv('OLLAMA_INFERENCE_MODEL', 'gemma3:1b')}")
        
        # Session statistics
        if st.session_state.query_history:
            st.subheader("📊 Session Stats")
            total_queries = len(st.session_state.query_history)
            successful_queries = sum(1 for q in st.session_state.query_history if q['success'])
            
            st.write(f"**Total Queries:** {total_queries}")
            st.write(f"**Successful:** {successful_queries}")
            st.write(f"**Success Rate:** {(successful_queries/total_queries)*100:.1f}%")
        

    
    # Main content
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.header("💬 Ask Your Question")
        
        # Query input
        user_query = st.text_input(
            "Enter your question:",
            value=st.session_state.selected_query,
            placeholder="e.g., 'Show me orders from John Smith'",
            key="main_query_input"
        )
        
        # Process query button and clear history button - left aligned and shorter with separation
        col_btn1, col_gap, col_btn2, col_spacer = st.columns([1, 0.5, 1, 2.5])  # Left align buttons with gap between them
        
        with col_btn1:
            process_clicked = st.button("🚀 Process Query", type="primary", use_container_width=True)
        
        with col_btn2:
            clear_clicked = st.button("🔄 Clear History", use_container_width=True)
        
        # Handle clear history button
        if clear_clicked:
            # Clear all session state variables
            st.session_state.query_history = []
            st.session_state.last_result = None
            st.session_state.selected_query = ""
            
            # Clear the input field by resetting its key
            if 'main_query_input' in st.session_state:
                del st.session_state['main_query_input']
            
            # Clear RAG system conversation if available
            if st.session_state.rag_system:
                try:
                    st.session_state.rag_system.clear_conversation()
                except:
                    pass  # Ignore if method doesn't exist
            
            # Force a complete page rerun
            st.rerun()
        
        # Handle process query button
        if process_clicked:
            # Clear selected query after button is clicked
            st.session_state.selected_query = ""
            
            if user_query.strip():
                with st.spinner("⏳ Processing your query..."):
                    result = st.session_state.rag_system.process_query(user_query)
                
                # Store in history
                st.session_state.query_history.append({
                    'timestamp': datetime.now().isoformat(),
                    'query': user_query,
                    'result': result,
                    'success': result['success']
                })
                
                st.session_state.last_result = result
                
                # Display result
                if result['success']:
                    # Success response with custom styling for better readability
                    st.markdown("""
                    <div style="background-color: #d1fae5; color: #065f46; padding: 0.75rem 1rem; border-radius: 8px; border: 1px solid #10b981; font-family: 'Mona Sans', sans-serif; font-weight: 500; margin-bottom: 1.5rem;">
                        ✅ <strong>Query Processed Successfully!</strong>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # Show confidence with extra spacing
                    confidence = result['similarity']
                    confidence_emoji = "🟢" if confidence > 0.8 else "🟡" if confidence > 0.6 else "🔴"
                    st.markdown(f"""
                    <div style="margin-top: 1rem; margin-bottom: 1rem; font-family: 'Mona Sans', sans-serif; font-size: 1.1rem; color: #1f2937;">
                        {confidence_emoji} <strong>Confidence:</strong> {confidence:.1%}
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # Show query details
                    col_a, col_b = st.columns(2)
                    with col_a:
                        st.write(f"📋 **Query Type:** {result['template_id']}")
                    with col_b:
                        st.write(f"📊 **Results Found:** {result['result_count']} records")
                    
                    # Show plugins used
                    plugins_used = result.get('plugins_used', [])
                    if plugins_used:
                        st.write(f"🔌 **Plugins Used:** {', '.join(plugins_used)}")
                    
                    # Show parameters
                    if result.get('parameters'):
                        params_text = ", ".join([f"{k}={v}" for k, v in result['parameters'].items()])
                        st.write(f"🔍 **Parameters:** {params_text}")
                    
                    # Show enhanced data indicators
                    if result.get('results'):
                        first_result = result['results'][0]
                        enhanced_fields = []
                        
                        if 'customer_segment' in first_result:
                            enhanced_fields.append("Customer Segment")
                        if 'revenue_analytics' in first_result:
                            enhanced_fields.append("Revenue Analytics")
                        if 'time_insights' in first_result:
                            enhanced_fields.append("Time Insights")
                        if 'geographic_insights' in first_result:
                            enhanced_fields.append("Geographic Insights")
                        if 'business_flags' in first_result:
                            enhanced_fields.append("Business Rules")
                        
                        if enhanced_fields:
                            st.write(f"🎯 **Enhanced Data:** {', '.join(enhanced_fields)}")
                    
                    # Show the main LLM response
                    st.subheader("💬 Answer:")
                    
                    # Convert markdown to HTML and display with proper styling
                    html_content = markdown.markdown(result['response'])
                    st.markdown(f"""
                    <div style="background-color: #ffffff; color: #1f2937; padding: 1.5rem; border-radius: 12px; border-left: 4px solid #10b981; margin: 1rem 0; line-height: 1.6; border: 1px solid #e5e7eb; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05); font-family: 'Mona Sans', sans-serif;">
                        {html_content}
                    </div>
                    """, unsafe_allow_html=True)
                    

                else:
                    # Error response
                    st.error("❌ **Query Failed**")
                    st.write(f"**Error:** {result.get('error', 'Unknown error')}")
                    
                    if result.get('verification_failed'):
                        st.warning("⚠️ **Template verification failed**")
                        if result.get('verification_reason'):
                            st.write(f"**Reason:** {result['verification_reason']}")
                    
                    if 'validation_errors' in result:
                        st.write("**Missing information:**")
                        for error in result['validation_errors']:
                            st.write(f"• {error}")
                    
                    if 'response' in result:
                        st.info(f"💡 **Suggestion:** {result['response']}")
            else:
                st.warning("Please enter a question to process.")
        
        # Follow-up suggestions
        if st.session_state.last_result and st.session_state.last_result.get('success'):
            suggestions = demo.suggest_followup(st.session_state.last_result)
            if suggestions:
                st.subheader("💭 Follow-up Suggestions")
                
                cols = st.columns(len(suggestions))
                for i, suggestion in enumerate(suggestions):
                    with cols[i]:
                        if st.button(suggestion, key=f"followup_{i}"):
                            st.session_state.selected_query = suggestion
                            st.rerun()
    
    with col2:
        st.header("💡 Example Queries")
        
        # Categorized examples
        for category, queries in demo.example_queries.items():
            with st.expander(category):
                for query in queries:
                    if st.button(query, key=f"example_{hash(query)}"):
                        st.session_state.selected_query = query
                        st.rerun()
        
        # Recent queries
        if st.session_state.query_history:
            st.subheader("📝 Recent Queries")
            
            for i, entry in enumerate(reversed(st.session_state.query_history[-5:])):
                with st.expander(f"Query {len(st.session_state.query_history) - i}"):
                    st.write(f"**Question:** {entry['query']}")
                    status_emoji = "✅" if entry['success'] else "❌"
                    st.write(f"**Status:** {status_emoji} {'Success' if entry['success'] else 'Failed'}")
                    
                    if entry['success']:
                        result = entry['result']
                        st.write(f"**Results:** {result['result_count']} records")
                        st.write(f"**Template:** {result['template_id']}")
                        
                        plugins_used = result.get('plugins_used', [])
                        if plugins_used:
                            st.write(f"**Plugins:** {', '.join(plugins_used)}")
                    
                    # Rerun button
                    if st.button("🔄 Run Again", key=f"rerun_{i}"):
                        st.session_state.selected_query = entry['query']
                        st.rerun()
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style="text-align: center; color: #666; margin-top: 2rem;">
        <strong>ORBIT Database Chat PoC</strong> - Natural Language Database Queries.
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main() 