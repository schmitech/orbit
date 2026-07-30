import shutil
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import runtime_profiles as rp

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO_ROOT / "install" / "default-config"
ORBITCHAT_TEMPLATE = REPO_ROOT / "clients" / "orbitchat" / "orbitchat.yaml.example"


@pytest.fixture
def runtime_config_dir(tmp_path):
    dest = tmp_path / "config-runtime"
    shutil.copytree(DEFAULT_CONFIG, dest)
    return dest


@pytest.mark.parametrize("profile_id", ["ollama", "openai", "gemini"])
def test_get_profile_known(profile_id):
    profile = rp.get_profile(profile_id)
    assert profile.profile_id == profile_id


def test_get_profile_unknown_rejected():
    with pytest.raises(rp.ProfileError):
        rp.get_profile("anthropic")
    with pytest.raises(rp.ProfileError):
        rp.get_profile("bogus")


@pytest.mark.parametrize(
    "profile_id,env_var",
    [("openai", "OPENAI_API_KEY"), ("gemini", "GOOGLE_API_KEY")],
)
def test_cloud_profiles_require_credential(profile_id, env_var):
    profile = rp.get_profile(profile_id)
    with pytest.raises(rp.ProfileError):
        rp.check_credential(profile, {})
    rp.check_credential(profile, {env_var: "secret"})  # does not raise


def test_ollama_profile_requires_no_credential():
    profile = rp.get_profile("ollama")
    rp.check_credential(profile, {})  # does not raise


def test_ollama_profile_keeps_simple_chat_with_files_and_gemma4(runtime_config_dir):
    profile = rp.get_profile("ollama")
    rp.resolve_config(profile, runtime_config_dir)

    adapters = yaml.safe_load((runtime_config_dir / rp.ADAPTER_FILE).read_text())
    adapter = next(a for a in adapters["adapters"] if a["name"] == rp.ADAPTER_NAME)
    assert adapter["inference_provider"] == "ollama"
    assert adapter["model"] == rp.OLLAMA_GEMMA4_MODEL
    assert adapter["embedding_provider"] == "ollama"
    assert adapter["embedding_model"] == "nomic-embed-text"
    assert adapter["vision_provider"] == "ollama"

    ollama_presets = yaml.safe_load((runtime_config_dir / "ollama.yaml").read_text())
    preset = ollama_presets["ollama_presets"][rp.OLLAMA_GEMMA4_MODEL]
    assert preset["model"] == rp.OLLAMA_GEMMA4_TAG

    inference = yaml.safe_load((runtime_config_dir / "inference.yaml").read_text())
    assert inference["inference"]["ollama"]["use_preset"] == rp.OLLAMA_GEMMA4_MODEL


@pytest.mark.parametrize(
    "profile_id,provider",
    [("openai", "openai"), ("gemini", "gemini")],
)
def test_cloud_profiles_never_fall_back_to_ollama_embeddings(profile_id, provider, runtime_config_dir):
    profile = rp.get_profile(profile_id)
    rp.resolve_config(profile, runtime_config_dir)

    adapters = yaml.safe_load((runtime_config_dir / rp.ADAPTER_FILE).read_text())
    adapter = next(a for a in adapters["adapters"] if a["name"] == rp.ADAPTER_NAME)
    assert adapter["inference_provider"] == provider
    assert adapter["embedding_provider"] == provider
    assert adapter["embedding_provider"] != "ollama"
    assert adapter["vision_provider"] == provider
    assert adapter["allowed_models"], "cloud profiles should expose allowed_models"
    assert all(m.get("effort") == "low" for m in adapter["allowed_models"]), (
        "allowed_models should ship a conservative default reasoning effort"
    )


def test_ollama_profile_has_no_audio_wiring(runtime_config_dir):
    # ollama has no audio: section (unlike openai/gemini) — stt/tts_provider
    # should stay absent from the adapter rather than silently defaulting.
    profile = rp.get_profile("ollama")
    rp.resolve_config(profile, runtime_config_dir)

    adapters = yaml.safe_load((runtime_config_dir / rp.ADAPTER_FILE).read_text())
    adapter = next(a for a in adapters["adapters"] if a["name"] == rp.ADAPTER_NAME)
    assert "stt_provider" not in adapter
    assert "tts_provider" not in adapter


def test_openai_profile_enables_audio_and_skill_routing(runtime_config_dir):
    profile = rp.get_profile("openai")
    rp.resolve_config(profile, runtime_config_dir)

    adapters = yaml.safe_load((runtime_config_dir / rp.ADAPTER_FILE).read_text())
    adapter = next(a for a in adapters["adapters"] if a["name"] == rp.ADAPTER_NAME)
    assert adapter["stt_provider"] == "openai"
    assert adapter["tts_provider"] == "openai"
    assert set(adapter["capabilities"]["auto_routable_skills"]) == {
        "Audio", "Image", "PDF", "Word", "Excel", "PowerPoint", "Fetch", "Markdown", "web-search",
    }
    assert adapter["capabilities"]["auto_skill_routing"] is True

    stt = yaml.safe_load((runtime_config_dir / "stt.yaml").read_text())
    assert stt["stt"]["enabled"] is True
    assert stt["stt_providers"]["openai"]["enabled"] is True

    tts = yaml.safe_load((runtime_config_dir / "tts.yaml").read_text())
    assert tts["tts"]["enabled"] is True
    assert tts["tts_providers"]["openai"]["enabled"] is True

    config = yaml.safe_load((runtime_config_dir / "config.yaml").read_text())
    assert config["conversation_threading"]["enabled"] is True
    assert config["skill_routing"]["auto_detect"] is True
    assert config["skill_routing"]["router_provider"] == "openai"
    assert config["skill_routing"]["router_model"] == "gpt-5.4-mini"
    assert "stt.yaml" in config["import"]
    assert "tts.yaml" in config["import"]

    registry = yaml.safe_load((runtime_config_dir / "adapters.yaml").read_text())
    for expected_file in (
        "adapters/web-search.yaml", "adapters/audio-generator.yaml", "adapters/image-generator.yaml",
        "adapters/pdf-generator.yaml", "adapters/word-generator.yaml", "adapters/excel-generator.yaml",
        "adapters/pptx-generator.yaml", "adapters/markdown-generator.yaml", "adapters/fetch.yaml",
    ):
        assert expected_file in registry["import"]

    web_search = yaml.safe_load((runtime_config_dir / "adapters/web-search.yaml").read_text())
    ws_adapter = web_search["adapters"][0]
    assert ws_adapter["inference_provider"] == "openai"
    assert ws_adapter["model"] == "gpt-5.4-mini"

    image_generator = yaml.safe_load((runtime_config_dir / "adapters/image-generator.yaml").read_text())
    ig_adapter = image_generator["adapters"][0]
    assert ig_adapter["image_provider"] == "openai"
    assert ig_adapter["rewrite_provider"] == "openai"
    assert ig_adapter["rewrite_model"] == "gpt-5.4-mini"

    image_config = yaml.safe_load((runtime_config_dir / "image.yaml").read_text())
    assert image_config["image_generation"]["openai"]["enabled"] is True


def test_gemini_profile_enables_audio_video_and_skill_routing(runtime_config_dir):
    profile = rp.get_profile("gemini")
    rp.resolve_config(profile, runtime_config_dir)

    adapters = yaml.safe_load((runtime_config_dir / rp.ADAPTER_FILE).read_text())
    adapter = next(a for a in adapters["adapters"] if a["name"] == rp.ADAPTER_NAME)
    assert adapter["stt_provider"] == "gemini"
    assert adapter["tts_provider"] == "gemini"
    assert set(adapter["capabilities"]["auto_routable_skills"]) == {
        "Audio", "Image", "Video", "PDF", "Word", "Excel", "PowerPoint", "Fetch", "Markdown", "web-search",
    }
    assert adapter["capabilities"]["auto_skill_routing"] is True

    stt = yaml.safe_load((runtime_config_dir / "stt.yaml").read_text())
    assert stt["stt"]["enabled"] is True
    assert stt["stt_providers"]["gemini"]["enabled"] is True

    tts = yaml.safe_load((runtime_config_dir / "tts.yaml").read_text())
    assert tts["tts"]["enabled"] is True
    assert tts["tts_providers"]["gemini"]["enabled"] is True

    config = yaml.safe_load((runtime_config_dir / "config.yaml").read_text())
    assert config["skill_routing"]["router_provider"] == "gemini"
    assert config["skill_routing"]["router_model"] == "gemini-3.6-flash"

    registry = yaml.safe_load((runtime_config_dir / "adapters.yaml").read_text())
    for expected_file in (
        "adapters/web-search.yaml", "adapters/audio-generator.yaml", "adapters/image-generator.yaml",
        "adapters/video-generator.yaml", "adapters/pdf-generator.yaml", "adapters/word-generator.yaml",
        "adapters/excel-generator.yaml", "adapters/pptx-generator.yaml", "adapters/markdown-generator.yaml",
        "adapters/fetch.yaml",
    ):
        assert expected_file in registry["import"]

    image_generator = yaml.safe_load((runtime_config_dir / "adapters/image-generator.yaml").read_text())
    assert image_generator["adapters"][0]["image_provider"] == "gemini"
    image_config = yaml.safe_load((runtime_config_dir / "image.yaml").read_text())
    assert image_config["image_generation"]["gemini"]["enabled"] is True

    video_generator = yaml.safe_load((runtime_config_dir / "adapters/video-generator.yaml").read_text())
    vg_adapter = video_generator["adapters"][0]
    assert vg_adapter["video_provider"] == "gemini"
    assert vg_adapter["rewrite_provider"] == "gemini"
    assert vg_adapter["rewrite_model"] == "gemini-3.6-flash"

    video_config = yaml.safe_load((runtime_config_dir / "video.yaml").read_text())
    assert video_config["video"]["enabled"] is True
    assert video_config["video_generation"]["gemini"]["enabled"] is True


@pytest.mark.parametrize("profile_id", ["ollama", "openai", "gemini"])
def test_resolve_config_enables_selected_inference_and_vision_providers(profile_id, runtime_config_dir):
    profile = rp.get_profile(profile_id)
    rp.resolve_config(profile, runtime_config_dir)

    inference = yaml.safe_load((runtime_config_dir / "inference.yaml").read_text())
    assert inference["inference"][profile.inference_provider]["enabled"] is True

    vision = yaml.safe_load((runtime_config_dir / "vision.yaml").read_text())
    assert vision["visions"][profile.vision_provider]["enabled"] is True
    assert vision["visions"][profile.vision_provider]["model"] == profile.vision_model


@pytest.mark.parametrize("profile_id", ["ollama", "openai", "gemini"])
def test_resolve_config_enables_global_vision_flag(profile_id, runtime_config_dir):
    # file_processing_service.py reads the global vision.enabled (default
    # false) as self.enable_vision; if false, image uploads are routed
    # through MarkItDown/OCR instead of the vision LLM path entirely,
    # regardless of the adapter's own vision_provider override.
    profile = rp.get_profile(profile_id)
    rp.resolve_config(profile, runtime_config_dir)

    vision = yaml.safe_load((runtime_config_dir / "vision.yaml").read_text())
    assert vision["vision"]["enabled"] is True
    assert vision["vision"]["provider"] == profile.vision_provider


@pytest.mark.parametrize("profile_id", ["ollama", "openai", "gemini"])
def test_resolve_config_enables_global_embedding_flag(profile_id, runtime_config_dir):
    # base_retriever.py treats embedding.enabled: false as an explicit
    # disable and skips creating any embedding service at all, independent
    # of the adapter's own embedding_provider override.
    profile = rp.get_profile(profile_id)
    rp.resolve_config(profile, runtime_config_dir)

    embeddings = yaml.safe_load((runtime_config_dir / "embeddings.yaml").read_text())
    assert embeddings["embedding"]["enabled"] is True


def test_resolve_config_points_sqlite_at_data_volume_and_drops_audio_imports(runtime_config_dir):
    # ollama has no audio: section, so stt.yaml/tts.yaml should still be dropped.
    profile = rp.get_profile("ollama")
    rp.resolve_config(profile, runtime_config_dir)

    config = yaml.safe_load((runtime_config_dir / "config.yaml").read_text())
    assert config["internal_services"]["backend"]["sqlite"]["database_path"] == "/orbit/data/orbit.db"
    assert "stt.yaml" not in config["import"]
    assert "tts.yaml" not in config["import"]


@pytest.mark.parametrize("profile_id", ["ollama", "openai", "gemini"])
def test_resolve_config_enables_audit_for_cost_tracking(profile_id, runtime_config_dir):
    # /admin/observability/usage (the Costs tab) 503s unless inference
    # auditing is on — usage/cost rows are read straight from audit records.
    profile = rp.get_profile(profile_id)
    rp.resolve_config(profile, runtime_config_dir)

    config = yaml.safe_load((runtime_config_dir / "config.yaml").read_text())
    assert config["internal_services"]["audit"]["enabled"] is True


@pytest.mark.parametrize("profile_id", ["ollama", "openai", "gemini"])
def test_resolve_config_keeps_pricing_import(profile_id, runtime_config_dir):
    # pricing.yaml backs the local rate table the Costs tab estimates from;
    # _resolve_docker_paths prunes the import list, so guard against it
    # being dropped along with stt.yaml/tts.yaml.
    profile = rp.get_profile(profile_id)
    rp.resolve_config(profile, runtime_config_dir)

    config = yaml.safe_load((runtime_config_dir / "config.yaml").read_text())
    assert "pricing.yaml" in config["import"]
    assert (runtime_config_dir / "pricing.yaml").exists()


@pytest.mark.parametrize("profile_id", ["ollama", "openai", "gemini"])
def test_resolve_config_sets_global_default_inference_provider(profile_id, runtime_config_dir):
    profile = rp.get_profile(profile_id)
    rp.resolve_config(profile, runtime_config_dir)

    config = yaml.safe_load((runtime_config_dir / "config.yaml").read_text())
    assert config["general"]["inference_provider"] == profile.inference_provider


@pytest.mark.parametrize("profile_id", ["openai", "gemini"])
def test_cloud_profiles_disable_ollama_inference_to_avoid_warmup_against_nothing(profile_id, runtime_config_dir):
    profile = rp.get_profile(profile_id)
    rp.resolve_config(profile, runtime_config_dir)

    inference = yaml.safe_load((runtime_config_dir / "inference.yaml").read_text())
    assert inference["inference"]["ollama"]["enabled"] is False


def test_ollama_profile_keeps_ollama_inference_enabled(runtime_config_dir):
    profile = rp.get_profile("ollama")
    rp.resolve_config(profile, runtime_config_dir)

    inference = yaml.safe_load((runtime_config_dir / "inference.yaml").read_text())
    assert inference["inference"]["ollama"]["enabled"] is True


def test_resolve_config_limits_adapter_registry_to_multimodal(runtime_config_dir):
    # ollama has no extra_adapters, so the registry should only ever import multimodal.yaml.
    profile = rp.get_profile("ollama")
    rp.resolve_config(profile, runtime_config_dir)

    adapters_registry = yaml.safe_load((runtime_config_dir / "adapters.yaml").read_text())
    assert adapters_registry["import"] == [rp.ADAPTER_FILE]


@pytest.mark.parametrize("profile_id", ["ollama", "openai", "gemini"])
def test_resolve_config_uses_writable_absolute_paths_for_uploads_and_chroma(profile_id, runtime_config_dir):
    # WORKDIR /orbit is root-owned; the container runs as a non-root user, so
    # the canonical relative defaults ("./uploads", "./chroma_db") fail with
    # a permission error instead of falling back gracefully.
    profile = rp.get_profile(profile_id)
    rp.resolve_config(profile, runtime_config_dir)

    config = yaml.safe_load((runtime_config_dir / "config.yaml").read_text())
    assert config["files"]["storage_root"] == rp.UPLOADS_DIR

    stores = yaml.safe_load((runtime_config_dir / "stores.yaml").read_text())
    assert stores["vector_stores"]["chroma"]["connection_params"]["persist_directory"] == rp.CHROMA_DIR

    adapters = yaml.safe_load((runtime_config_dir / rp.ADAPTER_FILE).read_text())
    adapter = next(a for a in adapters["adapters"] if a["name"] == rp.ADAPTER_NAME)
    assert adapter["config"]["storage_root"] == rp.UPLOADS_DIR


@pytest.mark.skipif(not ORBITCHAT_TEMPLATE.exists(), reason="orbitchat template not present in this checkout")
def test_generate_orbitchat_config_single_mode(tmp_path):
    profile = rp.get_profile("openai")
    out_path = tmp_path / "orbitchat.yaml"
    rp.generate_orbitchat_config(profile, ORBITCHAT_TEMPLATE, out_path)

    generated = yaml.safe_load(out_path.read_text())
    assert generated["agentMode"]["mode"] == "single"
    assert generated["agentMode"]["defaultAdapterId"] == rp.ADAPTER_NAME
    assert len(generated["adapters"]) == 1
    assert generated["adapters"][0]["id"] == rp.ADAPTER_NAME
    assert generated["features"]["enableUpload"] is True
    assert generated["features"]["enableAudioInput"] is True
    assert generated["features"]["enableAudioOutput"] is True
    assert generated["features"]["enableFeedbackButtons"] is True
    assert generated["features"]["enableConversationThreads"] is True
    assert generated["features"]["enableAutocomplete"] is True
