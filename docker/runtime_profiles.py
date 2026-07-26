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
# memory/compute than a pull-and-run quick start should require. Must match
# docker/flavors/ollama.yaml's inference.model / vision.model.
OLLAMA_GEMMA4_MODEL = "gemma4-e2b-cpu"  # preset name in install/default-config/ollama.yaml
OLLAMA_GEMMA4_TAG = "gemma4:e2b"  # resolved Ollama model tag, must match the preset

# Per-flavor profile definitions live in docker/flavors/*.yaml so new flavors,
# generator adapters (config/adapters/*-generator.yaml), and provider
# overrides can be added without touching this script.
FLAVORS_DIR = Path(__file__).resolve().parent / "flavors"


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
    extra_adapters: tuple[dict, ...] = field(default_factory=tuple)
    # Skill names to expose as available_skills/auto_routable_skills on
    # simple-chat-with-files, e.g. "PDF", "web-search". Empty = no auto-routing.
    auto_routable_skills: tuple[str, ...] = field(default_factory=tuple)
    skill_router_provider: str | None = None
    skill_router_model: str | None = None
    # Global STT/TTS provider for this flavor. None = audio stays disabled
    # and stt.yaml/tts.yaml are dropped from config.yaml's import list.
    audio_stt_provider: str | None = None
    audio_tts_provider: str | None = None


class ProfileError(ValueError):
    pass


def _available_flavor_ids() -> list[str]:
    return sorted(p.stem for p in FLAVORS_DIR.glob("*.yaml"))


def _load_flavor_file(profile_id: str) -> dict:
    path = FLAVORS_DIR / f"{profile_id}.yaml"
    if not path.exists():
        raise ProfileError(
            f"Unknown ORBIT_PROFILE '{profile_id}'. Supported profiles: {', '.join(_available_flavor_ids())}"
        )
    return _load_yaml(path)


def get_profile(profile_id: str) -> RuntimeProfile:
    data = _load_flavor_file(profile_id)
    inference = data.get("inference", {})
    embedding = data.get("embedding", {})
    vision = data.get("vision", {})
    skills = data.get("skills") or {}
    audio = data.get("audio") or {}
    try:
        return RuntimeProfile(
            profile_id=profile_id,
            inference_provider=inference["provider"],
            inference_model=inference["model"],
            embedding_provider=embedding["provider"],
            embedding_model=embedding["model"],
            vision_provider=vision["provider"],
            vision_model=vision["model"],
            required_env_var=data.get("required_env_var"),
            needs_ollama=bool(data.get("needs_ollama", False)),
            ollama_models=tuple(data.get("ollama_models") or ()),
            allowed_models=tuple(data.get("allowed_models") or ()),
            extra_adapters=tuple(data.get("extra_adapters") or ()),
            auto_routable_skills=tuple(skills.get("auto_routable") or ()),
            skill_router_provider=skills.get("router_provider"),
            skill_router_model=skills.get("router_model"),
            audio_stt_provider=audio.get("stt_provider"),
            audio_tts_provider=audio.get("tts_provider"),
        )
    except KeyError as exc:
        raise ProfileError(
            f"docker/flavors/{profile_id}.yaml is missing required field {exc}"
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


UPLOADS_DIR = "/orbit/data/uploads"
CHROMA_DIR = "/orbit/data/chroma_db"


def resolve_config(profile: RuntimeProfile, config_dir: Path) -> None:
    """Mutate the runtime config copy at config_dir in place for `profile`."""
    _resolve_adapter(profile, config_dir / ADAPTER_FILE)
    _resolve_inference_preset(profile, config_dir / "inference.yaml")
    _resolve_provider_enablement(profile, config_dir)
    _resolve_docker_paths(profile, config_dir / "config.yaml")
    _resolve_adapter_registry(config_dir / "adapters.yaml")
    _resolve_stores(config_dir / "stores.yaml")
    _resolve_extra_adapters(profile, config_dir)
    _resolve_skill_routing(profile, config_dir / "config.yaml")


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
            provider_block["model"] = profile.vision_model
        # The canonical default also ships a GLOBAL vision.enabled: false (on
        # top of the per-provider visions.<name>.enabled above).
        # file_processing_service.py reads this as self.enable_vision and,
        # if false, routes image uploads through MarkItDown/OCR instead of
        # the vision LLM path entirely — regardless of the adapter's own
        # vision_provider override.
        global_vision_block = data.get("vision")
        if global_vision_block is not None:
            global_vision_block["enabled"] = True
            global_vision_block["provider"] = profile.vision_provider
        _dump_yaml(vision_path, data)

    # The canonical default ships "ollama" enabled as the out-of-the-box local
    # provider. On a cloud profile there's no bundled Ollama to warm up
    # against, so leaving it enabled makes the server eagerly try (and fail)
    # to connect to a local Ollama that doesn't exist in this image.
    if inference_path.exists() and profile.inference_provider != "ollama":
        data = _load_yaml(inference_path)
        ollama_block = data.get("inference", {}).get("ollama")
        if ollama_block is not None:
            ollama_block["enabled"] = False
        _dump_yaml(inference_path, data)

    # base_retriever.py treats the global embedding.enabled flag (default
    # false in the canonical config) as an explicit disable and never
    # initializes an embedding service at all — independent of the adapter's
    # own embedding_provider override — so file uploads fail to index/query.
    embeddings_path = config_dir / "embeddings.yaml"
    if embeddings_path.exists():
        data = _load_yaml(embeddings_path)
        embedding_block = data.get("embedding")
        if embedding_block is not None:
            embedding_block["enabled"] = True
        _dump_yaml(embeddings_path, data)

    # Audio (STT/TTS) is opt-in per flavor via docker/flavors/<id>.yaml's `audio:`
    # section. Same enablement pattern as inference/vision above: the global
    # singular flag AND the specific provider block both need enabled: true.
    stt_path = config_dir / "stt.yaml"
    if profile.audio_stt_provider and stt_path.exists():
        data = _load_yaml(stt_path)
        stt_block = data.get("stt")
        if stt_block is not None:
            stt_block["enabled"] = True
            stt_block["provider"] = profile.audio_stt_provider
        provider_block = data.get("stt_providers", {}).get(profile.audio_stt_provider)
        if provider_block is not None:
            provider_block["enabled"] = True
        _dump_yaml(stt_path, data)

    tts_path = config_dir / "tts.yaml"
    if profile.audio_tts_provider and tts_path.exists():
        data = _load_yaml(tts_path)
        tts_block = data.get("tts")
        if tts_block is not None:
            tts_block["enabled"] = True
            tts_block["provider"] = profile.audio_tts_provider
        provider_block = data.get("tts_providers", {}).get(profile.audio_tts_provider)
        if provider_block is not None:
            provider_block["enabled"] = True
        _dump_yaml(tts_path, data)


def _resolve_docker_paths(profile: RuntimeProfile, config_path: Path) -> None:
    """Point the sqlite backend at the container's persistent /orbit/data volume,
    drop the STT/TTS import unless the flavor enables audio, and make the
    selected profile the global default inference provider — the canonical
    default (general.inference_provider: "ollama") would otherwise stay wired
    to a provider a cloud flavor doesn't bundle."""
    if not config_path.exists():
        return
    data = _load_yaml(config_path)

    drop = set()
    if not profile.audio_stt_provider:
        drop.add("stt.yaml")
    if not profile.audio_tts_provider:
        drop.add("tts.yaml")
    imports = data.get("import", [])
    data["import"] = [name for name in imports if name not in drop]

    general = data.setdefault("general", {})
    general["inference_provider"] = profile.inference_provider

    backend = data.get("internal_services", {}).get("backend", {})
    sqlite_block = backend.get("sqlite")
    if sqlite_block is not None:
        sqlite_block["database_path"] = "/orbit/data/orbit.db"

    # WORKDIR /orbit is root-owned; the container runs as the non-root
    # "orbit" user, so the canonical relative default ("./uploads") fails
    # with a permission error when the file service tries to create it.
    files_block = data.get("files")
    if files_block is not None:
        files_block["storage_root"] = UPLOADS_DIR

    _dump_yaml(config_path, data)


def _resolve_stores(stores_path: Path) -> None:
    """Same root cause as storage_root above: Chroma's relative default
    persist_directory ("./chroma_db") isn't writable by the non-root
    container user under WORKDIR /orbit."""
    if not stores_path.exists():
        return
    data = _load_yaml(stores_path)
    chroma = data.get("vector_stores", {}).get("chroma")
    if chroma is not None:
        connection_params = chroma.setdefault("connection_params", {})
        connection_params["persist_directory"] = CHROMA_DIR
    _dump_yaml(stores_path, data)


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
        if profile.audio_stt_provider:
            adapter["stt_provider"] = profile.audio_stt_provider
        else:
            adapter.pop("stt_provider", None)
        if profile.audio_tts_provider:
            adapter["tts_provider"] = profile.audio_tts_provider
        else:
            adapter.pop("tts_provider", None)
        if profile.allowed_models:
            adapter["allowed_models"] = [dict(m) for m in profile.allowed_models]
        else:
            adapter.pop("allowed_models", None)
        # Same non-root/WORKDIR permission issue as config.yaml's files.storage_root.
        adapter_config = adapter.get("config")
        if adapter_config is not None and "storage_root" in adapter_config:
            adapter_config["storage_root"] = UPLOADS_DIR

        capabilities = adapter.setdefault("capabilities", {})
        if profile.auto_routable_skills:
            capabilities["available_skills"] = list(profile.auto_routable_skills)
            capabilities["auto_routable_skills"] = list(profile.auto_routable_skills)
            capabilities["auto_skill_routing"] = True
    _dump_yaml(adapter_path, data)


def _resolve_extra_adapters(profile: RuntimeProfile, config_dir: Path) -> None:
    """Enable optional adapters (document/image/video generators, etc.) declared
    in the flavor's extra_adapters list — see docker/flavors/ollama.yaml for the
    entry schema. Each referenced file must already exist under config_dir; add
    it to install/default-config/adapters/ and Dockerfile.flavor's COPY first."""
    if not profile.extra_adapters:
        return

    registry_path = config_dir / "adapters.yaml"
    registry = _load_yaml(registry_path) if registry_path.exists() else {"import": []}
    imports = registry.setdefault("import", [])

    for entry in profile.extra_adapters:
        adapter_file = entry["file"]
        adapter_path = config_dir / adapter_file
        if not adapter_path.exists():
            raise ProfileError(
                f"extra_adapters entry '{entry.get('name', adapter_file)}' references "
                f"{adapter_file}, which does not exist in the runtime config directory. "
                "Add it to install/default-config/adapters/ (and Dockerfile.flavor's COPY) first."
            )

        data = _load_yaml(adapter_path)
        for adapter in data.get("adapters", []):
            for field_name, value in entry.get("provider_fields", {}).items():
                adapter[field_name] = value
            if "rewrite_provider" in entry:
                adapter["rewrite_provider"] = entry["rewrite_provider"]
            if "rewrite_model" in entry:
                adapter["rewrite_model"] = entry["rewrite_model"]
            # Same non-root/WORKDIR permission issue as the main adapter's storage_root.
            adapter_config = adapter.get("config")
            if adapter_config is not None and "storage_root" in adapter_config:
                adapter_config["storage_root"] = UPLOADS_DIR
        _dump_yaml(adapter_path, data)

        if adapter_file not in imports:
            imports.append(adapter_file)

    _dump_yaml(registry_path, registry)


def _resolve_skill_routing(profile: RuntimeProfile, config_path: Path) -> None:
    """When the flavor declares auto_routable_skills, turn on the natural-language
    skill router: conversation_threading.enabled (required by supports_threading
    skills) and skill_routing.auto_detect, with a small/fast confirm-LLM."""
    if not profile.auto_routable_skills or not config_path.exists():
        return
    data = _load_yaml(config_path)

    threading_block = data.get("conversation_threading")
    if threading_block is not None:
        threading_block["enabled"] = True

    skill_routing_block = data.setdefault("skill_routing", {})
    skill_routing_block["auto_detect"] = True
    skill_routing_block["router_provider"] = profile.skill_router_provider or profile.inference_provider
    skill_routing_block["router_model"] = profile.skill_router_model or profile.inference_model

    _dump_yaml(config_path, data)


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
    data["features"]["enableUpload"] = True
    data["features"]["enableAudioOutput"] = True
    data["features"]["enableAudioInput"] = True
    data["features"]["enableFeedbackButtons"] = True
    data["features"]["enableConversationThreads"] = True
    data["features"]["enableAutocomplete"] = True

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
