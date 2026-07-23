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
    assert "stt_provider" not in adapter
    assert "tts_provider" not in adapter


@pytest.mark.parametrize("profile_id", ["ollama", "openai", "gemini"])
def test_resolve_config_enables_selected_inference_and_vision_providers(profile_id, runtime_config_dir):
    profile = rp.get_profile(profile_id)
    rp.resolve_config(profile, runtime_config_dir)

    inference = yaml.safe_load((runtime_config_dir / "inference.yaml").read_text())
    assert inference["inference"][profile.inference_provider]["enabled"] is True

    vision = yaml.safe_load((runtime_config_dir / "vision.yaml").read_text())
    assert vision["visions"][profile.vision_provider]["enabled"] is True


def test_resolve_config_points_sqlite_at_data_volume_and_drops_audio_imports(runtime_config_dir):
    profile = rp.get_profile("openai")
    rp.resolve_config(profile, runtime_config_dir)

    config = yaml.safe_load((runtime_config_dir / "config.yaml").read_text())
    assert config["internal_services"]["backend"]["sqlite"]["database_path"] == "/orbit/data/orbit.db"
    assert "stt.yaml" not in config["import"]
    assert "tts.yaml" not in config["import"]


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
    profile = rp.get_profile("gemini")
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
    assert generated["features"]["enableAudioInput"] is False
    assert generated["features"]["enableAudioOutput"] is False
