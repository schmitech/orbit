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

# Import the RAG system
from customer_order_rag import SemanticRAGSystem


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
    
    
def initialize_system():
    """Initialize the RAG system with proper error handling"""
    try:
        with st.spinner("🚀 Initializing RAG system with plugins..."):
            rag_system = SemanticRAGSystem(
                enable_default_plugins=True,
                enable_postgresql_plugins=True
            )
            rag_system.populate_chromadb("query_templates.yaml", clear_first=True)
            return rag_system, None
    except Exception as e:
        error_msg = f"System initialization failed: {str(e)}\n\n"
        error_msg += "**Troubleshooting:**\n"
        error_msg += f"1. Ensure Ollama is running at {os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')}\n"
        error_msg += f"2. Pull required models:\n"
        error_msg += f"   - `ollama pull {os.getenv('OLLAMA_EMBEDDING_MODEL', 'nomic-embed-text')}`\n"
        error_msg += f"   - `ollama pull {os.getenv('OLLAMA_INFERENCE_MODEL', 'gemma3:1b')}`\n"
        error_msg += "3. Check PostgreSQL connection settings in .env file"
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
    
    # Custom CSS for better styling
    st.markdown("""
    <style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 1rem;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #666;
        text-align: center;
        margin-bottom: 2rem;
    }
    .example-category {
        background: #f8f9fa;
        padding: 1rem;
        border-radius: 8px;
        margin: 0.5rem 0;
        border-left: 4px solid #1f77b4;
    }
    .followup-suggestion {
        background: #e8f4f8;
        padding: 0.8rem;
        border-radius: 6px;
        margin: 0.3rem 0;
        border-left: 3px solid #17a2b8;
    }
    .response-container {
        background: #f8f9fa;
        padding: 1.5rem;
        border-radius: 10px;
        border-left: 4px solid #28a745;
        margin: 1rem 0;
    }
    .error-container {
        background: #fff5f5;
        padding: 1.5rem;
        border-radius: 10px;
        border-left: 4px solid #dc3545;
        margin: 1rem 0;
    }
    .stats-container {
        background: #f8f9fa;
        padding: 1rem;
        border-radius: 8px;
        margin: 0.5rem 0;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Header
    st.markdown('<h1 class="main-header">🤖 ORBIT Database Chat PoC</h1>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Natural Language Database Queries with AI-Powered Insights</p>', unsafe_allow_html=True)
    
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
        st.success("✅ System Ready")
        
        # Plugin information
        if st.session_state.rag_system:
            plugins = st.session_state.rag_system.list_plugins()
            enabled_plugins = [p['name'] for p in plugins if p['enabled']]
            
            st.subheader("🔌 Active Plugins")
            for plugin in enabled_plugins:
                st.write(f"• {plugin}")
        
        # System configuration
        st.subheader("🔧 Configuration")
        st.write(f"**Ollama:** {os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')}")
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
        
        # Clear history button
        if st.button("🗑️ Clear History"):
            st.session_state.query_history = []
            st.session_state.last_result = None
            if st.session_state.rag_system:
                st.session_state.rag_system.clear_conversation()
            st.rerun()
    
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
        
        # Process query button
        if st.button("🚀 Process Query", type="primary"):
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
                    # Success response with native Streamlit components
                    st.success("✅ **Query Processed Successfully!**")
                    
                    # Show confidence
                    confidence = result['similarity']
                    confidence_emoji = "🟢" if confidence > 0.8 else "🟡" if confidence > 0.6 else "🔴"
                    st.write(f"{confidence_emoji} **Confidence:** {confidence:.1%}")
                    
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
                    <div style="background-color: #2d3748; color: #e2e8f0; padding: 1.5rem; border-radius: 0.5rem; border-left: 4px solid #28a745; margin: 1rem 0; line-height: 1.6;">
                        {html_content}
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # Show results table if available
                    if result.get('results'):
                        st.subheader("📊 Results Table")
                        df = pd.DataFrame(result['results'])
                        st.dataframe(df, use_container_width=True, hide_index=True)
                        
                        # Show download button
                        csv = df.to_csv(index=False)
                        st.download_button(
                            label="📥 Download Results as CSV",
                            data=csv,
                            file_name=f"query_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                            mime="text/csv"
                        )
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
        <strong>ORBIT Database Chat PoC</strong> - Natural language database queries with AI-powered insights and plugin enhancements
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main() 