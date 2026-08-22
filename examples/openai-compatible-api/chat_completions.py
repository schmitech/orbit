#!/usr/bin/env python3
"""Example: call ORBIT with the official OpenAI Python SDK.

ORBIT's /v1/chat/completions endpoint is OpenAI-compatible, so the
standard `openai` client works unmodified — just point `base_url` at
your ORBIT server and pass your ORBIT API key.
"""

import argparse
import os
import sys
import uuid

from openai import OpenAI

ORBIT_API_URL = os.environ.get("ORBIT_API_URL", "http://localhost:3000")
ORBIT_API_KEY = os.environ.get("ORBIT_API_KEY")


def chat(message: str, stream: bool = False):
    if not ORBIT_API_KEY:
        sys.exit("Set the ORBIT_API_KEY environment variable")

    client = OpenAI(
        base_url=f"{ORBIT_API_URL}/v1",
        api_key=ORBIT_API_KEY,
        # ORBIT requires a session id per request by default
        # (config.yaml: chat_history.session.required).
        default_headers={"X-Session-ID": str(uuid.uuid4())},
    )

    response = client.chat.completions.create(
        model=os.environ.get("ORBIT_MODEL", "gpt-oss:120b"),
        messages=[{"role": "user", "content": message}],
        stream=stream,
    )

    if not stream:
        print(response.choices[0].message.content)
        return

    for chunk in response:
        delta = chunk.choices[0].delta.content or ""
        print(delta, end="", flush=True)
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("message", help="Message to send to ORBIT")
    parser.add_argument("--stream", action="store_true", help="Stream the response")
    args = parser.parse_args()

    chat(args.message, stream=args.stream)
