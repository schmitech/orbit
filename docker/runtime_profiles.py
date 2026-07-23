"""Runtime profile resolver for published ORBIT Docker flavors.

Given ORBIT_PROFILE, resolves the canonical install/default-config tree
(already copied to /orbit/config-runtime by docker-entrypoint.sh) into a
working configuration for that flavor: inference/vision/embedding provider
wiring, the simple-chat-with-files adapter, and the matching orbitchat UI
config. This is packaging/runtime glue, not server code.

Supported profiles: ollama, openai, gemini. Each requires exactly one
runtime credential (or none, for ollama) so the whole multimodal stack
(chat + vision + embeddings) comes up from a single API key.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ADAPTER_NAME = "simple-chat-with-files"
ADAPTER_FILE = "adapters/multimodal.yaml"

# The Ollama flavor uses gemma4:e2b — the smallest "edge" tier in the gemma4
# family. It is the only tier that comfortably runs multimodal (text+vision)
# inference on a CPU-only container with modest RAM; e4b/12b need far more
# memory/compute than a pull-and-run quick start should require.
OLLAMA_GEMMA4_MODEL = "gemma4-e2b-cpu"  # preset name in install/default-config/ollama.yaml
OLLAMA_GEMMA4_TAG = "gemma4:e2b"  # resolved Ollama model tag, must match the preset


@dataclass(frozen=True)
class RuntimeProfile:
    profile_id: str
    inference_provider: str
    inference_model: str  # value written to adapter `model:` (preset name or model id)
    embedding_provider: str
    embedding_model: str
    vision_provider: str
    vision_model: str
    required_env_var: str | None  # None => no credential required (ollama)
    needs_ollama: bool
    ollama_models: tuple[str, ...] = field(default_factory=tuple)
    allowed_models: tuple[dict, ...] = field(default_factory=tuple)


PROFILES: dict[str, RuntimeProfile] = {
    "ollama": RuntimeProfile(
        profile_id="ollama",
        inference_provider="ollama",
        inference_model=OLLAMA_GEMMA4_MODEL,
        embedding_provider="ollama",
        embedding_model="nomic-embed-text",
        vision_provider="ollama",
        vision_model=OLLAMA_GEMMA4_TAG,
        required_env_var=None,
        needs_ollama=True,
        ollama_models=(OLLAMA_GEMMA4_TAG, "nomic-embed-text"),
    ),
    "openai": RuntimeProfile(
        profile_id="openai",
        inference_provider="openai",
        inference_model="gpt-5.4-mini",
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
        vision_provider="openai",
        vision_model="gpt-5.5",
        required_env_var="OPENAI_API_KEY",
        needs_ollama=False,
        allowed_models=(
            {"name": "gpt-5.4-mini", "provider": "openai", "model": "gpt-5.4-mini",
             "context_window": 400000, "max_tokens": 32000},
            {"name": "gpt-5.4", "provider": "openai", "model": "gpt-5.4",
             "context_window": 400000, "max_tokens": 64000},
            {"name": "gpt-5.4-nano", "provider": "openai", "model": "gpt-5.4-nano",
             "context_window": 400000, "max_tokens": 16000},
        ),
    ),
    "gemini": RuntimeProfile(
        profile_id="gemini",
        inference_provider="gemini",
        inference_model="gemini-3.1-pro-preview",
        embedding_provider="gemini",
        embedding_model="gemini-embedding-2-preview",
        vision_provider="gemini",
        vision_model="gemini-3.6-flash",
        required_env_var="GOOGLE_API_KEY",
        needs_ollama=False,
        allowed_models=(
            {"name": "gemini-3.6-flash", "provider": "gemini", "model": "gemini-3.6-flash",
             "context_window": 1048576, "max_tokens": 32000},
            {"name": "gemini-3.1-pro-preview", "provider": "gemini", "model": "gemini-3.1-pro-preview",
             "context_window": 1048576, "max_tokens": 65536},
        ),
    ),
}


class ProfileError(ValueError):
    pass


def get_profile(profile_id: str) -> RuntimeProfile:
    try:
        return PROFILES[profile_id]
    except KeyError:
        raise ProfileError(
            f"Unknown ORBIT_PROFILE '{profile_id}'. Supported profiles: {', '.join(sorted(PROFILES))}"
        ) from None


def check_credential(profile: RuntimeProfile, env: dict[str, str]) -> None:
    if profile.required_env_var and not env.get(profile.required_env_var):
        raise ProfileError(
            f"Profile '{profile.profile_id}' requires {profile.required_env_var} to be set at container startup."
        )


def _load_yaml(path: Path) -> dict:
    with path.open("r") as f:
        return yaml.safe_load(f) or {}


def _dump_yaml(path: Path, data: dict) -> None:
    with path.open("w") as f:
        yaml.safe_dump(data, f, sort_keys=False, default_flow_style=False, allow_unicode=True)


def resolve_config(profile: RuntimeProfile, config_dir: Path) -> None:
    """Mutate the runtime config copy at config_dir in place for `profile`."""
    _resolve_adapter(profile, config_dir / ADAPTER_FILE)
    _resolve_inference_preset(profile, config_dir / "inference.yaml")
    _resolve_provider_enablement(profile, config_dir)
    _resolve_docker_paths(config_dir / "config.yaml")
    _resolve_adapter_registry(config_dir / "adapters.yaml")


def _resolve_provider_enablement(profile: RuntimeProfile, config_dir: Path) -> None:
    """server/ai_services/registry.py only registers inference/vision providers
    whose config block has enabled: true (default_enabled=False for both
    sections) — an adapter-level provider override is not enough on its own."""
    inference_path = config_dir / "inference.yaml"
    if inference_path.exists():
        data = _load_yaml(inference_path)
        provider_block = data.get("inference", {}).get(profile.inference_provider)
        if provider_block is not None:
            provider_block["enabled"] = True
        _dump_yaml(inference_path, data)

    vision_path = config_dir / "vision.yaml"
    if vision_path.exists():
        data = _load_yaml(vision_path)
        provider_block = data.get("visions", {}).get(profile.vision_provider)
        if provider_block is not None:
            provider_block["enabled"] = True
        _dump_yaml(vision_path, data)


def _resolve_docker_paths(config_path: Path) -> None:
    """Point the sqlite backend at the container's persistent /orbit/data volume
    and drop the STT/TTS import — flavor images ship text+vision+file chat only."""
    if not config_path.exists():
        return
    data = _load_yaml(config_path)

    imports = data.get("import", [])
    data["import"] = [name for name in imports if name not in ("stt.yaml", "tts.yaml")]

    backend = data.get("internal_services", {}).get("backend", {})
    sqlite_block = backend.get("sqlite")
    if sqlite_block is not None:
        sqlite_block["database_path"] = "/orbit/data/orbit.db"

    _dump_yaml(config_path, data)


def _resolve_adapter_registry(adapters_registry_path: Path) -> None:
    """Flavor images expose exactly one product adapter (simple-chat-with-files);
    only load its category so unrelated datasource adapters never initialize."""
    if not adapters_registry_path.exists():
        return
    data = _load_yaml(adapters_registry_path)
    data["import"] = [ADAPTER_FILE]
    _dump_yaml(adapters_registry_path, data)


def _resolve_adapter(profile: RuntimeProfile, adapter_path: Path) -> None:
    data = _load_yaml(adapter_path)
    for adapter in data.get("adapters", []):
        if adapter.get("name") != ADAPTER_NAME:
            continue
        adapter["inference_provider"] = profile.inference_provider
        adapter["model"] = profile.inference_model
        adapter["embedding_provider"] = profile.embedding_provider
        adapter["embedding_model"] = profile.embedding_model
        adapter["vision_provider"] = profile.vision_provider
        adapter.pop("stt_provider", None)
        adapter.pop("tts_provider", None)
        if profile.allowed_models:
            adapter["allowed_models"] = [dict(m) for m in profile.allowed_models]
        else:
            adapter.pop("allowed_models", None)
    _dump_yaml(adapter_path, data)


def _resolve_inference_preset(profile: RuntimeProfile, inference_path: Path) -> None:
    if profile.inference_provider != "ollama" or not inference_path.exists():
        return
    data = _load_yaml(inference_path)
    ollama_block = data.get("inference", {}).get("ollama")
    if ollama_block is not None:
        ollama_block["use_preset"] = profile.inference_model
    _dump_yaml(inference_path, data)


def generate_orbitchat_config(profile: RuntimeProfile, template_path: Path, output_path: Path) -> None:
    """Single-mode orbitchat UI config wired to the one product adapter."""
    with template_path.open("r") as f:
        data = yaml.safe_load(f) or {}

    data.setdefault("agentMode", {})
    data["agentMode"]["mode"] = "single"
    data["agentMode"]["defaultAdapterId"] = ADAPTER_NAME
    data["adapters"] = [
        {
            "id": ADAPTER_NAME,
            "name": "ORBIT Multimodal Chat",
            "apiUrl": "http://localhost:3000",
            "description": "Chat, PDF/Word/Excel/image/Markdown document Q&A.",
            "inputPlaceholder": "Message ORBIT...",
        }
    ]
    data.setdefault("features", {})
    data["features"]["enableAudioInput"] = False
    data["features"]["enableAudioOutput"] = False

    with output_path.open("w") as f:
        yaml.safe_dump(data, f, sort_keys=False, default_flow_style=False, allow_unicode=True)


def log_profile(profile: RuntimeProfile) -> None:
    print(f"ORBIT_PROFILE={profile.profile_id}")
    print(f"  inference: {profile.inference_provider} ({profile.inference_model})")
    print(f"  vision:    {profile.vision_provider} ({profile.vision_model})")
    print(f"  embedding: {profile.embedding_provider} ({profile.embedding_model})")
    print(f"  credential: {profile.required_env_var or 'none required'}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, help="ORBIT_PROFILE value")
    parser.add_argument("--config-dir", required=True, type=Path, help="Runtime config directory to mutate in place")
    parser.add_argument("--orbitchat-template", type=Path, help="orbitchat.yaml template to render from")
    parser.add_argument("--orbitchat-out", type=Path, help="Where to write the generated orbitchat.yaml")
    args = parser.parse_args(argv)

    try:
        profile = get_profile(args.profile)
        check_credential(profile, os.environ)
    except ProfileError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    log_profile(profile)
    resolve_config(profile, args.config_dir)

    if args.orbitchat_template and args.orbitchat_out:
        generate_orbitchat_config(profile, args.orbitchat_template, args.orbitchat_out)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
