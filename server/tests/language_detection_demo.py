"""
Language Detection Demo
======================

This example demonstrates how the language detection functionality works
with the chat service to automatically respond in the user's language.
"""

import asyncio
import logging
import sys
import os
from datetime import datetime
from bson import ObjectId

# Add the parent directory to the path so we can import the modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.chat_service import ChatService
from utils.text_utils import fix_text_formatting
from utils.language_detector import LanguageDetector

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Mock classes for demonstration
class MockPromptService:
    """Mock implementation of the prompt service"""
    
    async def get_prompt_by_id(self, prompt_id):
        """Return a mock prompt"""
        return {
            "_id": prompt_id,
            "name": "Default System Prompt",
            "prompt": "You are a helpful assistant that provides accurate information.",
            "version": "1.0",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
    
    async def create_prompt(self, name, prompt_text, version="1.0"):
        """Create a mock prompt and return an ID"""
        logger.info(f"Creating prompt: {name}")
        logger.info(f"Prompt text: {prompt_text[:100]}...")
        return ObjectId()

class MockLLMClient:
    """Mock implementation of the LLM client"""
    
    def __init__(self):
        """Initialize the mock LLM client"""
        self.prompt_service = MockPromptService()
    
    async def generate_response(self, message, collection_name, system_prompt_id=None):
        """Generate a mock response"""
        # In a real implementation, this would call the language model
        # For demonstration, we'll just echo back the message with language info
        language_detector = LanguageDetector(verbose=True)
        detected_lang = language_detector.detect(message)
        
        # Get language name
        language_names = {
            'en': 'English',
            'es': 'Spanish',
            'fr': 'French',
            'de': 'German',
            'it': 'Italian',
            'pt': 'Portuguese',
            'ru': 'Russian',
            'zh': 'Chinese',
            'ja': 'Japanese'
        }
        language_name = language_names.get(detected_lang, f"Language code: {detected_lang}")
        
        response = f"I detected that you're speaking {language_name}. Here's my response:\n\n"
        
        # Add a mock response based on the language
        if detected_lang == 'en':
            response += "I understand your message and I'm responding in English."
        elif detected_lang == 'es':
            response += "Entiendo tu mensaje y estoy respondiendo en español."
        elif detected_lang == 'fr':
            response += "Je comprends votre message et je réponds en français."
        elif detected_lang == 'de':
            response += "Ich verstehe Ihre Nachricht und antworte auf Deutsch."
        elif detected_lang == 'it':
            response += "Capisco il tuo messaggio e sto rispondendo in italiano."
        elif detected_lang == 'pt':
            response += "Eu entendo sua mensagem e estou respondendo em português."
        elif detected_lang == 'ru':
            response += "Я понимаю ваше сообщение и отвечаю на русском языке."
        else:
            response += f"I'm responding in the detected language: {language_name}"
        
        return {"response": response}

class MockLoggerService:
    """Mock implementation of the logger service"""
    
    async def log_conversation(self, query, response, ip, backend, blocked, api_key):
        """Log a conversation"""
        logger.info(f"Logged conversation from {ip}")

async def main():
    """Run the language detection demo"""
    # Set up configuration
    config = {
        'general': {
            'verbose': True
        }
    }
    
    # Create the chat service
    llm_client = MockLLMClient()
    logger_service = MockLoggerService()
    chat_service = ChatService(config, llm_client, logger_service)
    
    # Define example messages in different languages
    messages = [
        {"lang": "English", "text": "Hello, how are you today?"},
        {"lang": "Spanish", "text": "Hola, ¿cómo estás hoy?"},
        {"lang": "French", "text": "Bonjour, comment allez-vous aujourd'hui?"},
        {"lang": "German", "text": "Hallo, wie geht es Ihnen heute?"},
        {"lang": "Italian", "text": "Ciao, come stai oggi?"},
        {"lang": "Portuguese", "text": "Olá, como você está hoje?"},
        {"lang": "Russian", "text": "Привет, как ты сегодня?"},
        {"lang": "Greek", "text": "Γεια σας, πώς είστε σήμερα;"},
        {"lang": "Greek (Technical)", "text": "Παρακαλώ ελέγξτε τη διαμόρφωση του συστήματος."},
        {"lang": "Bulgarian", "text": "Здравейте, как сте днес?"},
        {"lang": "Bulgarian (Technical)", "text": "Моля, проверете конфигурацията на системата."},
        {"lang": "Latin", "text": "Lorem ipsum dolor sit amet, consectetur adipiscing elit."},
        {"lang": "Latin (Technical)", "text": "Per se, ad hoc, et cetera, vice versa."},
        {"lang": "Chinese (Simplified)", "text": "你好，今天过得怎么样？"},
        {"lang": "Chinese (Traditional)", "text": "你好，今天過得怎麼樣？"},
        {"lang": "Chinese (Technical)", "text": "请检查系统配置并重启服务器。"},
        {"lang": "Mixed", "text": "Hello and bonjour, how are you? Comment ça va?"}
    ]
    
    # Create a mock system prompt ID
    system_prompt_id = ObjectId()
    
    # Process each message
    print("\n===== LANGUAGE DETECTION DEMO =====\n")
    for idx, msg in enumerate(messages):
        print(f"\n--- Example {idx+1}: {msg['lang']} ---")
        print(f"User: {msg['text']}")
        
        response_data = await chat_service.process_chat(
            message=msg['text'],
            client_ip="127.0.0.1",
            collection_name="demo_collection",
            system_prompt_id=system_prompt_id,
            api_key="demo_api_key"
        )
        
        print(f"Assistant: {response_data['response']}")
        print("-" * 50)
    
    print("\nDemo completed!")

if __name__ == "__main__":
    asyncio.run(main()) 