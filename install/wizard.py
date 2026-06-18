#!/usr/bin/env python3
"""ORBIT Setup Wizard — Interactive guided configuration for newcomers."""

import getpass
import os
import re
import sys

# ─── Provider definitions ────────────────────────────────────────────────────

PROVIDERS = [
    {
        "label": "Ollama (Local)",
        "key": "ollama",
        "model": "gemma4-e2b-cpu",
        "env_var": None,
        "description": "Free, private, runs on your machine (requires Ollama installed)",
        "needs_key": False,
        "setup_hint": (
            "Ollama must be running before you start ORBIT.\n"
            "  Install : https://ollama.com/download\n"
            "  Pull model : ollama pull gemma4:e2b\n"
            "  Start      : ollama serve"
        ),
    },
    {
        "label": "OpenAI",
        "key": "openai",
        "model": "gpt-4o-mini",
        "env_var": "OPENAI_API_KEY",
        "description": "Cloud API — needs API key",
        "needs_key": True,
        "setup_hint": "Get your key at https://platform.openai.com/api-keys",
    },
    {
        "label": "Anthropic (Claude)",
        "key": "anthropic",
        "model": "claude-sonnet-4-6",
        "env_var": "ANTHROPIC_API_KEY",
        "description": "Cloud API — needs API key",
        "needs_key": True,
        "setup_hint": "Get your key at https://console.anthropic.com/settings/keys",
    },
    {
        "label": "Google Gemini",
        "key": "gemini",
        "model": "gemini-2.0-flash",
        "env_var": "GOOGLE_API_KEY",
        "description": "Cloud API — needs API key",
        "needs_key": True,
        "setup_hint": "Get your key at https://aistudio.google.com/apikey",
    },
    {
        "label": "Groq",
        "key": "groq",
        "model": "llama-3.1-8b-instant",
        "env_var": "GROQ_API_KEY",
        "description": "Cloud API — fast inference, free tier available",
        "needs_key": True,
        "setup_hint": "Get your key at https://console.groq.com/keys",
    },
]

USE_CASES = [
    {
        "label": "Simple Chat",
        "description": "Chat with AI, no document retrieval",
        "adapter_files": ["adapters/passthrough.yaml"],
        "adapter_names": ["simple-chat"],
    },
    {
        "label": "Chat with Files",
        "description": "Chat + upload PDFs, images, spreadsheets",
        "adapter_files": ["adapters/passthrough.yaml", "adapters/multimodal.yaml"],
        "adapter_names": ["simple-chat", "simple-chat-with-files"],
    },
]

# ─── ANSI helpers ────────────────────────────────────────────────────────────

RESET = "\033[0m"
BOLD = "\033[1m"
BLUE = "\033[0;34m"
GREEN = "\033[0;32m"
YELLOW = "\033[0;33m"
RED = "\033[0;31m"
CYAN = "\033[0;36m"


def c(color, text):
    return f"{color}{text}{RESET}"


# ─── YAML editing (line-based, comment-preserving) ───────────────────────────

def set_yaml_scalar(text, key, value, indent=None):
    """Replace the first occurrence of `key: <anything>` with `key: value`.
    If indent is given, only matches lines with exactly that leading whitespace.
    """
    if indent is not None:
        pattern = rf'^({re.escape(indent)}{re.escape(key)}:\s*).*$'
    else:
        pattern = rf'^(\s*{re.escape(key)}:\s*).*$'
    quoted = f'"{value}"' if not value.startswith('"') else value
    replacement = rf'\g<1>{quoted}'
    new_text, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
    return new_text, count > 0


def enable_inference_provider(text, provider_key):
    """Find the provider section in inference.yaml and set enabled: true."""
    lines = text.splitlines(keepends=True)
    in_provider = False
    result = []
    for line in lines:
        stripped = line.rstrip()
        # Match "  <provider>:" at 2-space indent (top-level inference sub-key)
        if stripped == f"  {provider_key}:":
            in_provider = True
            result.append(line)
            continue
        if in_provider:
            # "    enabled: ..." at 4-space indent
            if re.match(r'^    enabled:', line):
                result.append(re.sub(r'^(    enabled:\s*).*$', r'\g<1>true', line))
                in_provider = False
                continue
            # If we hit another 2-space top-level key, stop
            if re.match(r'^  \S', line):
                in_provider = False
        result.append(line)
    return "".join(result)


def update_adapter_provider(text, adapter_name, provider_key, model):
    """Update inference_provider and model under a named adapter block."""
    lines = text.splitlines(keepends=True)
    in_adapter = False
    found_provider = False
    found_model = False
    result = []
    for line in lines:
        # Detect adapter entry start: "  - name: "<adapter_name>""
        if re.search(rf'name:\s*"{re.escape(adapter_name)}"', line):
            in_adapter = True
            found_provider = False
            found_model = False

        if in_adapter:
            # Next adapter entry starts
            if re.match(r'^  - name:', line) and adapter_name not in line:
                in_adapter = False
            elif re.match(r'^    inference_provider:', line) and not found_provider:
                line = re.sub(
                    r'^(    inference_provider:\s*).*$',
                    rf'\g<1>"{provider_key}"',
                    line,
                )
                found_provider = True
            elif re.match(r'^    model:', line) and not found_model:
                line = re.sub(r'^(    model:\s*).*$', rf'\g<1>"{model}"', line)
                found_model = True

        result.append(line)
    return "".join(result)


def set_env_var(text, var_name, value):
    """Set or append an environment variable in .env content."""
    pattern = rf'^({re.escape(var_name)}\s*=).*$'
    new_text, count = re.subn(pattern, rf'\g<1>{value}', text, count=1, flags=re.MULTILINE)
    if count == 0:
        # Append if not found
        separator = "\n" if text and not text.endswith("\n") else ""
        new_text = text + separator + f"{var_name}={value}\n"
    return new_text


# ─── Prompts ─────────────────────────────────────────────────────────────────

def _render_option(i, opt, selected):
    label = f"{i + 1}. {opt['label']}"
    padded = f"{label:<22}"
    desc = opt["description"]
    if i == selected:
        return f"  {c(GREEN, '▶')} {c(BOLD, padded)}  {desc}"
    return f"    {padded}  {desc}"


def prompt_choice(question, options, default=1):
    """Arrow-key navigable menu. Falls back to number input when stdin is not a tty."""
    selected = default - 1  # 0-based internal index

    print(f"\n{c(CYAN, question)}")

    # Non-interactive fallback (pipe, CI, etc.)
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        for i, opt in enumerate(options):
            print(_render_option(i, opt, selected))
        print()
        while True:
            try:
                raw = input(f"  Select [1-{len(options)}] (default {default}): ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                sys.exit(0)
            if raw == "":
                return selected
            if raw.isdigit() and 1 <= int(raw) <= len(options):
                return int(raw) - 1
            print(c(RED, f"  Invalid — enter a number between 1 and {len(options)}"))

    # Interactive arrow-key mode
    import termios, tty  # noqa: PLC0415 (stdlib, available on macOS/Linux)

    HINT = f"  {c(YELLOW, '↑/↓ to move · Enter to select · 1–' + str(len(options)) + ' to jump')}"
    # After render(), the cursor rests on the hint line (no trailing \n), which is
    # exactly len(options) lines below the first option row — one \n per option row.
    MOVE_UP = len(options)

    def render():
        for i, opt in enumerate(options):
            sys.stdout.write(f"\x1b[2K\r{_render_option(i, opt, selected)}\n")
        sys.stdout.write(f"\x1b[2K\r{HINT}")
        sys.stdout.flush()

    render()

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while True:
            ch = sys.stdin.buffer.read(1)

            if ch == b"\x1b":
                seq = sys.stdin.buffer.read(2)
                if seq == b"[A":   # Up arrow
                    selected = (selected - 1) % len(options)
                elif seq == b"[B": # Down arrow
                    selected = (selected + 1) % len(options)
            elif ch in (b"\r", b"\n"):  # Enter
                break
            elif ch == b"\x03":         # Ctrl-C
                sys.stdout.write("\n")
                sys.stdout.flush()
                raise KeyboardInterrupt
            elif b"1" <= ch <= b"9":    # Direct number jump
                n = int(ch.decode())
                if 1 <= n <= len(options):
                    selected = n - 1
                    break

            # Redraw in place: move up exactly len(options) lines to reach row 0
            sys.stdout.write(f"\x1b[{MOVE_UP}A")
            render()
    except KeyboardInterrupt:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        print()
        sys.exit(0)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    # Final render: replace menu with selected-only view, clear hint line
    sys.stdout.write(f"\x1b[{MOVE_UP}A")
    for i, opt in enumerate(options):
        sys.stdout.write(f"\x1b[2K\r{_render_option(i, opt, selected)}\n")
    sys.stdout.write("\x1b[2K\r")  # clear hint line (cursor stays here, no \n)
    sys.stdout.flush()

    return selected


def prompt_api_key(provider):
    """Prompt for an API key (masked input)."""
    hint = provider.get("setup_hint", "")
    if hint:
        print(f"\n  {c(YELLOW, hint)}")
    print()
    while True:
        try:
            key = getpass.getpass(f"  Enter your {provider['label']} API key: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)
        if key:
            return key
        print(c(RED, "  API key cannot be empty — try again, or press Ctrl-C to exit"))


# ─── File writers ─────────────────────────────────────────────────────────────

def write_config_yaml(config_dir, provider_key):
    path = os.path.join(config_dir, "config.yaml")
    if not os.path.isfile(path):
        print(c(YELLOW, f"  ⚠  config/config.yaml not found at {path} — skipping"))
        return False
    with open(path) as f:
        text = f.read()
    new_text, ok = set_yaml_scalar(text, "inference_provider", provider_key, indent="  ")
    if not ok:
        print(c(YELLOW, "  ⚠  Could not locate inference_provider in config.yaml — skipping"))
        return False
    with open(path, "w") as f:
        f.write(new_text)
    return True


def write_inference_yaml(config_dir, provider_key):
    path = os.path.join(config_dir, "inference.yaml")
    if not os.path.isfile(path):
        print(c(YELLOW, f"  ⚠  config/inference.yaml not found — skipping"))
        return False
    with open(path) as f:
        text = f.read()
    new_text = enable_inference_provider(text, provider_key)
    with open(path, "w") as f:
        f.write(new_text)
    return True


def write_adapter_yaml(config_dir, adapter_file, adapter_name, provider_key, model):
    path = os.path.join(config_dir, adapter_file)
    if not os.path.isfile(path):
        print(c(YELLOW, f"  ⚠  {adapter_file} not found — skipping"))
        return False
    with open(path) as f:
        text = f.read()
    new_text = update_adapter_provider(text, adapter_name, provider_key, model)
    with open(path, "w") as f:
        f.write(new_text)
    return True


def write_env_file(env_path, var_name, value):
    if not os.path.isfile(env_path):
        # Create empty file
        open(env_path, "a").close()
    with open(env_path) as f:
        text = f.read()
    new_text = set_env_var(text, var_name, value)
    with open(env_path, "w") as f:
        f.write(new_text)
    return True


# ─── Main ─────────────────────────────────────────────────────────────────────

def main(project_root):
    print()
    print(c(BLUE, "╔════════════════════════════════════════════════════════════════╗"))
    print(c(BLUE, "║          ORBIT Setup Wizard — Quick Start                     ║"))
    print(c(BLUE, "╚════════════════════════════════════════════════════════════════╝"))
    print()
    print("  This wizard configures your AI provider and adapter settings.")
    print("  You can re-run it any time to change your setup.")
    print()
    print(f"  {c(YELLOW, 'Press Ctrl-C at any time to exit without saving.')}")

    config_dir = os.path.join(project_root, "config")
    env_path = os.path.join(project_root, ".env")

    # Warn early if config/ is missing
    if not os.path.isdir(config_dir):
        print()
        print(c(RED, f"  Error: config/ directory not found at {config_dir}"))
        print(c(YELLOW, "  Make sure you are running this from the ORBIT project root,"))
        print(c(YELLOW, "  or that the install/default-config directory was copied to config/."))
        sys.exit(1)

    # ── Step 1: Use case ──────────────────────────────────────────────────────
    use_case_idx = prompt_choice(
        "Step 1/3 — What kind of setup do you want?",
        USE_CASES,
        default=1,
    )
    use_case = USE_CASES[use_case_idx]

    # ── Step 2: Provider ──────────────────────────────────────────────────────
    provider_idx = prompt_choice(
        "Step 2/3 — Which AI provider do you want to use?",
        PROVIDERS,
        default=1,
    )
    provider = PROVIDERS[provider_idx]

    # ── Step 3: API key (cloud providers only) ────────────────────────────────
    api_key = None
    if provider["needs_key"]:
        print(f"\n{c(CYAN, 'Step 3/3 — Authenticate with ' + provider['label'])}")
        api_key = prompt_api_key(provider)
    else:
        print(f"\n  {c(GREEN, 'Step 3/3 — No API key needed for Ollama.')}")
        print(f"\n  {c(YELLOW, provider['setup_hint'])}")

    # ── Write config ──────────────────────────────────────────────────────────
    print()
    print(c(BLUE, "  Writing configuration..."))

    results = {}

    # .env — only for cloud providers
    if api_key and provider["env_var"]:
        ok = write_env_file(env_path, provider["env_var"], api_key)
        results[".env"] = ok

    # config/config.yaml — global inference_provider
    ok = write_config_yaml(config_dir, provider["key"])
    results["config/config.yaml"] = ok

    # config/inference.yaml — enable the selected provider
    ok = write_inference_yaml(config_dir, provider["key"])
    results["config/inference.yaml"] = ok

    # Adapter YAMLs
    for adapter_file, adapter_name in zip(use_case["adapter_files"], use_case["adapter_names"]):
        ok = write_adapter_yaml(config_dir, adapter_file, adapter_name, provider["key"], provider["model"])
        results[adapter_file] = ok

    # ── Summary ───────────────────────────────────────────────────────────────
    print()
    for label, ok in results.items():
        icon = c(GREEN, "  ✓") if ok else c(YELLOW, "  ⚠")
        print(f"{icon}  {label}")

    print()
    print(c(GREEN, "  ════════════════════════════════════════════════════════════════"))
    print(c(GREEN, f"  Setup complete!  Provider: {provider['label']}  ·  Use case: {use_case['label']}"))
    print(c(GREEN, "  ════════════════════════════════════════════════════════════════"))
    print()
    if provider["key"] == "ollama":
        print(f"  {c(YELLOW, 'Before starting ORBIT, make sure Ollama is running:')}")
        print(f"    ollama serve")
        print()
    print(f"  {c(CYAN, 'Start ORBIT:')}")
    print(f"    {c(BOLD, './bin/orbit.sh start')}")
    print()
    print(f"  {c(CYAN, 'Test the API:')}")
    print(
        "    curl -X POST http://localhost:3000/v1/chat \\\n"
        '      -H \'Content-Type: application/json\' \\\n'
        '      -H \'X-API-Key: default-key\' \\\n'
        '      -H \'X-Session-ID: test\' \\\n'
        '      -d \'{"messages": [{"role": "user", "content": "Hello!"}], "stream": false}\''
    )
    print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: wizard.py <project_root>", file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1])
