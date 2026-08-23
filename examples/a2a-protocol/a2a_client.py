#!/usr/bin/env python3
"""Call ORBIT through its Google Agent-to-Agent (A2A) protocol endpoint."""

import argparse
import codecs
import json
import os
import sys
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ORBIT_API_URL = os.environ.get("ORBIT_API_URL", "http://localhost:3000").rstrip("/")
ORBIT_API_KEY = os.environ.get("ORBIT_API_KEY")
ORBIT_USER_TOKEN = os.environ.get("ORBIT_USER_TOKEN")
ORBIT_A2A_ADAPTER = os.environ.get("ORBIT_A2A_ADAPTER")


def headers():
    result = {"Content-Type": "application/json"}
    if ORBIT_API_KEY:
        result["Authorization"] = "Bearer {}".format(ORBIT_API_KEY)
    if ORBIT_USER_TOKEN:
        result["X-ORBIT-User-Authorization"] = "Bearer {}".format(ORBIT_USER_TOKEN)
    return result


def rpc_request(method, params):
    """Build one JSON-RPC 2.0 request for POST /a2a."""
    return {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": method,
        "params": params,
    }


def post(payload, stream=False):
    request = Request(
        "{}/a2a".format(ORBIT_API_URL),
        data=json.dumps(payload).encode("utf-8"),
        headers=headers(),
        method="POST",
    )
    try:
        return urlopen(request) if stream else json.load(urlopen(request))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        sys.exit("HTTP {}: {}".format(error.code, detail))
    except URLError as error:
        sys.exit("Could not reach ORBIT: {}".format(error.reason))


def task_params(message=None, task_id=None):
    params = {}
    if task_id:
        params["id"] = task_id
    if message is not None:
        params["message"] = {
            "role": "user",
            "parts": [{"type": "text", "text": message}],
        }
    if ORBIT_A2A_ADAPTER:
        params["metadata"] = {"adapter": ORBIT_A2A_ADAPTER}
    return params


def discover():
    request = Request("{}/.well-known/agent.json".format(ORBIT_API_URL))
    try:
        print(json.dumps(json.load(urlopen(request)), indent=2))
    except HTTPError as error:
        sys.exit("HTTP {}: {}".format(error.code, error.read().decode("utf-8", "replace")))
    except URLError as error:
        sys.exit("Could not reach ORBIT: {}".format(error.reason))


def send(message):
    response = post(rpc_request("tasks/send", task_params(message)))
    print(json.dumps(response, indent=2))


def send_subscribe(message):
    response = post(rpc_request("tasks/sendSubscribe", task_params(message)), stream=True)
    print("Streaming A2A events:")

    def print_event(line):
        line = line.strip()
        if not line.startswith("data: "):
            return False
        event = json.loads(line[6:])
        print(json.dumps(event, indent=2))
        return event.get("result", {}).get("final", False)

    decoder = codecs.getincrementaldecoder("utf-8")()
    buffer = ""
    while True:
        chunk = response.read(4096)
        if not chunk:
            buffer += decoder.decode(b"", final=True)
            break
        buffer += decoder.decode(chunk)
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            if print_event(line):
                return

    # SSE permits the last event to omit its trailing newline. Process it rather
    # than silently dropping a complete event when the connection closes.
    if buffer.strip():
        try:
            print_event(buffer)
        except json.JSONDecodeError as error:
            sys.exit("Stream ended with an incomplete SSE event: {}".format(error))


def get_or_cancel(method, task_id):
    response = post(rpc_request(method, {"id": task_id}))
    print(json.dumps(response, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--discover", action="store_true", help="Fetch the A2A Agent Card")
    actions.add_argument("--get", metavar="TASK_ID", help="Retrieve a task")
    actions.add_argument("--cancel", metavar="TASK_ID", help="Cancel a task")
    parser.add_argument("message", nargs="?", help="Message to send to ORBIT")
    parser.add_argument("--stream", action="store_true", help="Use tasks/sendSubscribe")
    args = parser.parse_args()

    if args.discover:
        discover()
    elif args.get:
        get_or_cancel("tasks/get", args.get)
    elif args.cancel:
        get_or_cancel("tasks/cancel", args.cancel)
    elif args.message:
        send_subscribe(args.message) if args.stream else send(args.message)
    else:
        parser.error("provide a message or one of --discover, --get, or --cancel")


if __name__ == "__main__":
    main()
