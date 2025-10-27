#!/usr/bin/env python3
"""Debug Ollama JSON output with gemma3:12b"""

import requests
import json

OLLAMA_URL = "http://35.182.131.171:11434"
MODEL = "gemma3:12b"

def debug_json_output():
    """Debug what the model actually outputs"""

    # Simple test input
    test_text = """
    Community of Guardians mission is inspiring the world to take action.
    We provide environmental consulting and education services globally.
    Our team includes Dr. Smith as director and Jane Doe as coordinator.
    """

    prompt = f"""Extract information from this text and return it as valid JSON.

Follow this exact format:
{{
  "extractions": [
    {{
      "extraction_class": "organization",
      "extraction_text": "Community of Guardians",
      "attributes": {{"question": "What is the organization?", "answer": "Community of Guardians"}}
    }},
    {{
      "extraction_class": "fact",
      "extraction_text": "inspiring the world to take action",
      "attributes": {{"question": "What is their mission?", "answer": "inspiring the world to take action"}}
    }}
  ]
}}

Text: {test_text}

JSON output:"""

    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.1,
            "num_predict": 800
        }
    }

    print(f"Testing {MODEL} JSON output...")

    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json=payload,
            timeout=60
        )

        if response.status_code == 200:
            result = response.json()
            output = result.get('response', '')

            print(f"\nRaw output:\n{output}\n")
            print("="*50)

            # Try to parse as JSON
            try:
                parsed = json.loads(output)
                print("✅ Valid JSON!")
                print(json.dumps(parsed, indent=2))
            except json.JSONDecodeError as e:
                print(f"❌ Invalid JSON: {e}")
                print(f"Error at position {e.pos}")
                if e.pos < len(output):
                    context_start = max(0, e.pos - 50)
                    context_end = min(len(output), e.pos + 50)
                    print(f"Context: ...{output[context_start:context_end]}...")
        else:
            print(f"❌ HTTP Error: {response.status_code}")
            print(response.text)

    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    debug_json_output()