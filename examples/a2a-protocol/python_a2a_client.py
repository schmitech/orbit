#!/usr/bin/env python3
"""Call ORBIT using the python-a2a package's A2AClient and message models."""

import argparse
import os
import sys
import uuid

import requests
from python_a2a import A2AClient, Message, MessageRole, TextContent

ORBIT_API_URL = os.environ.get("ORBIT_API_URL", "http://localhost:3000").rstrip("/")
ORBIT_API_KEY = os.environ.get("ORBIT_API_KEY")
ORBIT_USER_TOKEN = os.environ.get("ORBIT_USER_TOKEN")
ORBIT_A2A_ADAPTER = os.environ.get("ORBIT_A2A_ADAPTER")


class OrbitA2AClient(A2AClient):
    """Adapt python-a2a's typed client API to ORBIT's single `/a2a` endpoint.

    python-a2a discovers an Agent Card and provides the Message helpers used
    here, but its built-in task client probes `/a2a/tasks/send`. ORBIT follows
    the JSON-RPC binding at `/a2a`, so this small adapter sends that envelope
    while retaining `A2AClient.ask()` and its typed Message return value.
    """

    def send_message(self, message, adapter=None):
        if isinstance(message, str):
            message = Message(content=TextContent(text=message), role=MessageRole.USER)

        params = {
            "id": str(uuid.uuid4()),
            "message": message.to_google_a2a(),
        }
        if adapter:
            params["metadata"] = {"adapter": adapter}

        response = requests.post(
            "{}/a2a".format(self.endpoint_url),
            json={
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "method": "tasks/send",
                "params": params,
            },
            headers=self.headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        body = response.json()
        if "error" in body:
            raise RuntimeError("A2A error: {}".format(body["error"].get("message", body["error"])))

        result = body["result"]
        text = _response_text(result)
        return Message(
            content=TextContent(text=text),
            role=MessageRole.AGENT,
            parent_message_id=message.message_id,
            conversation_id=message.conversation_id,
        )

    def ask_orbit(self, text, adapter=None):
        """Send text, optionally selecting an ORBIT A2A skill/adapter."""
        message = Message(content=TextContent(text=text), role=MessageRole.USER)
        response = self.send_message(message, adapter=adapter)
        return response.content.text


def _response_text(task):
    for artifact in task.get("artifacts", []):
        text = "".join(
            part.get("text", "")
            for part in artifact.get("parts", [])
            if part.get("type") == "text"
        )
        if text:
            return text
    raise RuntimeError("A2A response did not contain a text artifact")


def make_headers():
    headers = {"Content-Type": "application/json"}
    if ORBIT_API_KEY:
        headers["Authorization"] = "Bearer {}".format(ORBIT_API_KEY)
    if ORBIT_USER_TOKEN:
        headers["X-ORBIT-User-Authorization"] = "Bearer {}".format(ORBIT_USER_TOKEN)
    return headers


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("message", help="Message to send to ORBIT")
    parser.add_argument(
        "--adapter",
        default=ORBIT_A2A_ADAPTER,
        help="ORBIT adapter/skill ID (defaults to ORBIT_A2A_ADAPTER)",
    )
    args = parser.parse_args()

    try:
        client = OrbitA2AClient(ORBIT_API_URL, headers=make_headers(), google_a2a_compatible=True)
        print(client.ask_orbit(args.message, adapter=args.adapter))
    except requests.RequestException as error:
        sys.exit("Could not reach ORBIT: {}".format(error))
    except (KeyError, RuntimeError, ValueError) as error:
        sys.exit("A2A request failed: {}".format(error))


if __name__ == "__main__":
    main()
