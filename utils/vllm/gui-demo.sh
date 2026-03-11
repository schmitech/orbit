#!/bin/bash

# Install required packages if not already installed
pip install gradio openai

# Create a simple Gradio UI for vLLM
cat > vllm_gradio_ui.py << 'EOF'
import gradio as gr
import argparse
import time
from openai import OpenAI

def format_history(history):
    formatted_history = [{
        "role": "system", 
        "content": "You are a helpful AI assistant."
    }]
    
    for message in history:
        if isinstance(message, tuple):
            human, assistant = message
            formatted_history.append({"role": "user", "content": human})
            if assistant:
                formatted_history.append({"role": "assistant", "content": assistant})
        else:
            formatted_history.append(message)
    
    return formatted_history

def main():
    parser = argparse.ArgumentParser(description='Gradio UI for vLLM')
    parser.add_argument('--model', type=str, default="VLLMQwen2.5-14B", help='Model name')
    parser.add_argument('--api-url', type=str, default="http://localhost:5000/v1", help='API base URL')
    parser.add_argument('--api-key', type=str, default="", help='API key')
    parser.add_argument('--temperature', type=float, default=0.7, help='Temperature')
    parser.add_argument('--port', type=int, default=7860, help='Port for Gradio UI')
    
    args = parser.parse_args()
    
    # Create OpenAI client
    client = OpenAI(api_key=args.api_key or "not-needed", base_url=args.api_url)
    
    def user(user_message, history):
        return "", history + [{"role": "user", "content": user_message}]
    
    def bot(history, temperature):
        if not history:
            return history
            
        # Get messages for API call
        messages = format_history(history)
        
        # Add empty assistant message
        history.append({"role": "assistant", "content": ""})
        
        # Stream response
        response = ""
        for delta in client.chat.completions.create(
            model=args.model,
            messages=messages,
            temperature=temperature,
            stream=True
        ):
            content = delta.choices[0].delta.content
            if content is not None:
                response += content
                history[-1] = {"role": "assistant", "content": response}
                yield history
                time.sleep(0.01)  # Small delay for smoother streaming
        
        return history
    
    # Create Gradio interface
    with gr.Blocks(title=f"vLLM Chat Interface - {args.model}") as demo:
        gr.Markdown(f"# Chat with {args.model}")
        gr.Markdown("A simple chat interface powered by vLLM")
        
        chatbot = gr.Chatbot(height=500, type="messages")
        msg = gr.Textbox(placeholder="Type your message here and press Enter...", container=False)
        
        with gr.Row():
            submit_btn = gr.Button("Send")
            clear_btn = gr.Button("Clear")
        
        # Temperature slider
        temp_slider = gr.Slider(
            minimum=0.0, maximum=1.0, value=args.temperature, step=0.1, 
            label="Temperature", info="Higher values make output more random"
        )
        
        # Set up event handlers
        msg.submit(
            user, 
            [msg, chatbot], 
            [msg, chatbot]
        ).then(
            bot,
            [chatbot, temp_slider],
            [chatbot]
        )
        
        submit_btn.click(
            user, 
            [msg, chatbot], 
            [msg, chatbot]
        ).then(
            bot,
            [chatbot, temp_slider],
            [chatbot]
        )
        
        clear_btn.click(lambda: [], None, chatbot)
    
    # Launch the interface
    demo.queue()
    demo.launch(server_name="0.0.0.0", server_port=args.port, share=False)

if __name__ == "__main__":
    main()
EOF

echo "Created vllm_gradio_ui.py"
echo "Starting Gradio UI for vLLM..."

# Run the Gradio UI
python3 vllm_gradio_ui.py "$@" 