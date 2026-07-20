#!/usr/bin/env python3
"""
Generate a multi_user_load_test.py config from the OrbitChat client setup.

Reads adapter metadata (id, display name, description) from an orbitchat
client YAML file and joins it with the real API keys from that client's
.env.local (VITE_ADAPTER_KEYS), producing a JSON config that
multi_user_load_test.py can drive load with.

Usage:
    python gen_load_config.py \
        --env-file ../../../clients/orbitchat/.env.local \
        --client-yaml ../../../clients/orbitchat/orbitchat.yaml \
        --host http://localhost:3000 \
        --out load_test_config.json
"""

import argparse
import json
import re
from pathlib import Path

import yaml

# Adapters that don't make sense for a text chat load test: they generate
# media, transcribe audio, or hold open a realtime voice socket. Excluded
# by default so a load run doesn't fire expensive Veo/DALL-E/realtime calls
# or hang on a websocket handshake.
NON_TEXT_ADAPTER_IDS = {
    "image-generator",
    "video-generator",
    "audio-generator",
    "audio-transcription",
    "voice-chat",
    "real-time-voice-chat",
    "open-ai-real-time-voice-chat",
}

DEFAULT_PROMPTS = [
    "What can you help me with?",
    "Give me a short summary of what you do.",
    "Tell me something interesting.",
]

# Seed prompts per adapter id, tailored to what each adapter actually knows
# about. Adapters not listed here fall back to DEFAULT_PROMPTS.
ADAPTER_PROMPTS = {
    "qa-sql": [
        "What are the city's business hours?",
        "How do I request a building permit?",
        "Where can I pay a parking ticket?",
    ],
    "qa-vector-chroma": [
        "What services does the city offer online?",
        "How do I report a pothole?",
        "What's the process for renewing a business license?",
    ],
    "hr-db-chatbot": [
        "How many employees are in the engineering department?",
        "Who is the manager of the sales team?",
        "What is the average salary in the marketing department?",
    ],
    "intent-sql-postgres": [
        "How many orders were placed last month?",
        "What is the total revenue from customer orders?",
        "Which customer has placed the most orders?",
    ],
    "ecomm-analytics": [
        "What were the top selling products last quarter?",
        "Show me revenue trends by region.",
        "Which product category has the highest margin?",
    ],
    "intent-duckdb-ev-population": [
        "How many electric vehicles are registered in Washington State?",
        "What is the most popular EV make?",
        "How many Tesla vehicles are in the dataset?",
    ],
    "intent-http-jsonplaceholder": [
        "List the first five users.",
        "What posts did user 1 write?",
        "Show me the comments on post 3.",
    ],
    "intent-http-paris-opendata": [
        "What events are happening in Paris this week?",
        "Are there any free activities for kids in Paris?",
        "What cultural events are near the Louvre?",
    ],
    "intent-mongodb-mflix": [
        "What movies did Tom Hanks star in?",
        "What is the highest rated movie from the 1990s?",
        "List comedies released after 2010.",
    ],
    "intent-graphql-spacex": [
        "When was the last SpaceX launch?",
        "How many Falcon 9 launches have there been?",
        "What is the next scheduled SpaceX mission?",
    ],
    "intent-elasticsearch-log": [
        "Are there any errors in the logs from the last hour?",
        "Show me the most frequent error messages.",
        "What services logged warnings today?",
    ],
    "simple-chat": DEFAULT_PROMPTS,
    "web-search": [
        "What's the latest news on AI regulation?",
        "Who won the most recent World Cup?",
        "What's the current weather in Ottawa?",
    ],
    "chat-with-files": DEFAULT_PROMPTS,
}


def parse_env_local(path: Path) -> dict:
    """Extract the VITE_ADAPTER_KEYS JSON blob from a .env.local file."""
    text = path.read_text()
    match = re.search(r"VITE_ADAPTER_KEYS\s*=\s*'(.*?)'", text, re.DOTALL)
    if not match:
        raise ValueError(f"VITE_ADAPTER_KEYS not found in {path}")
    return json.loads(match.group(1))


def load_client_adapters(path: Path) -> list:
    with open(path) as f:
        data = yaml.safe_load(f)
    return data.get("adapters", []) or []


def build_config(env_file: Path, client_yaml: Path, host: str, include_all: bool) -> dict:
    adapter_keys = parse_env_local(env_file)
    client_adapters = load_client_adapters(client_yaml)

    adapters = []
    skipped = []

    for entry in client_adapters:
        adapter_id = entry.get("id")
        if not adapter_id:
            continue

        if not include_all and adapter_id in NON_TEXT_ADAPTER_IDS:
            skipped.append((adapter_id, "non-text adapter"))
            continue

        api_key = adapter_keys.get(adapter_id)
        if not api_key or not api_key.startswith("orbit_"):
            skipped.append((adapter_id, "missing or placeholder key"))
            continue

        adapters.append({
            "id": adapter_id,
            "name": entry.get("name", adapter_id),
            "api_key": api_key,
            "weight": 1,
            "prompts": ADAPTER_PROMPTS.get(adapter_id, DEFAULT_PROMPTS),
        })

    for adapter_id, reason in skipped:
        print(f"  skipped '{adapter_id}': {reason}")

    return {
        "host": host,
        "endpoint": "/v1/chat/completions",
        "default_prompts": DEFAULT_PROMPTS,
        "adapters": adapters,
    }


def main():
    parser = argparse.ArgumentParser(description="Generate a multi-user load test config")
    parser.add_argument("--env-file", default="../../../clients/orbitchat/.env.local",
                        help="Path to the orbitchat .env.local file with VITE_ADAPTER_KEYS")
    parser.add_argument("--client-yaml", default="../../../clients/orbitchat/orbitchat.yaml",
                        help="Path to the orbitchat client YAML with adapter metadata")
    parser.add_argument("--host", default="http://localhost:3000", help="ORBIT server host")
    parser.add_argument("--out", default="load_test_config.json", help="Output config file path")
    parser.add_argument("--include-all", action="store_true",
                        help="Include media/voice adapters normally excluded from text load tests")
    args = parser.parse_args()

    env_file = Path(args.env_file)
    client_yaml = Path(args.client_yaml)

    if not env_file.exists():
        raise SystemExit(f"env file not found: {env_file}")
    if not client_yaml.exists():
        raise SystemExit(f"client yaml not found: {client_yaml}")

    print(f"Reading keys from {env_file}")
    print(f"Reading adapter metadata from {client_yaml}")

    config = build_config(env_file, client_yaml, args.host, args.include_all)

    out_path = Path(args.out)
    with open(out_path, "w") as f:
        json.dump(config, f, indent=2)

    print(f"\nWrote {len(config['adapters'])} adapters to {out_path}")
    for adapter in config["adapters"]:
        print(f"  {adapter['id']} ({adapter['name']})")


if __name__ == "__main__":
    main()
