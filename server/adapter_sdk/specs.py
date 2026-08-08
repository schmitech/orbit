"""
Adapter spec registry — the source of truth that tames the combinatorics.

Each AdapterSpec hard-codes the interdependent tuple (type/datasource/adapter/
implementation) and the correct capability shape for one family, so neither the
user nor the AI ever has to guess them. A spec also declares the ordered wizard
questions, which both the CLI and a future admin UI render from a single source.

Scope (v1): template-like families only — document generators, media generators,
passthrough/conversational, fetch, mcp-agent, and web-search (native + external).
Intent x datasource adapters are intentionally out of scope here.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

# Fully-qualified implementation classes (verified against config/adapters/*.yaml).
_MULTIMODAL_IMPL = "implementations.passthrough.multimodal.MultimodalImplementation"
_CONVERSATIONAL_IMPL = "implementations.passthrough.conversational.ConversationalImplementation"


# Bounds applied to any question that does not set its own. Every answer is
# bounded: an adapter config is a small YAML document, and unbounded values reach
# both the config file and the LLM prompt that the adapter builds.
DEFAULT_MAX_LENGTH = 200  # characters, per string (or per list item)
DEFAULT_MAX_ITEMS = 25    # entries in a list answer


@dataclass
class Question:
    """One wizard prompt. Rendered by cli.py and the admin UI."""

    field: str
    prompt: str
    type: str = "str"  # one of: str, int, bool, list
    default: Any = None
    choices: Optional[List[str]] = None
    help: str = ""
    max_length: Optional[int] = None  # str/list: chars per value (per item for lists)
    max_items: Optional[int] = None   # list only
    min_value: Optional[int] = None   # int only
    max_value: Optional[int] = None   # int only


def question_limits(q: Question) -> Dict[str, Any]:
    """Concrete bounds for a question — explicit values win, else the type default.

    Resolved in one place so the form controls, the server-side check and the CLI
    all enforce identical limits.
    """
    if q.type == "bool":
        return {}
    if q.type == "int":
        return {"min_value": q.min_value, "max_value": q.max_value}
    limits: Dict[str, Any] = {"max_length": q.max_length or DEFAULT_MAX_LENGTH}
    if q.type == "list":
        limits["max_items"] = q.max_items or DEFAULT_MAX_ITEMS
    return limits


@dataclass
class AdapterSpec:
    """Everything needed to generate one family of adapter configs."""

    key: str
    title: str
    description: str
    template: str  # Jinja2 filename under templates/
    fixed: Dict[str, Any]  # context values always emitted, never asked
    questions: List[Question]
    variant_field: Optional[str] = None  # the question that selects a variant (e.g. document_format)
    variants: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    # variants[value] = {"fixed": {...ctx overrides...}, "defaults": {...question defaults...}}

    def variant_values(self) -> List[str]:
        return list(self.variants.keys())

    def question_default(self, q: Question, chosen_variant: Optional[str]) -> Any:
        """Default for a question, letting the chosen variant override the base default."""
        if chosen_variant and chosen_variant in self.variants:
            defaults = self.variants[chosen_variant].get("defaults", {})
            if q.field in defaults:
                return defaults[q.field]
        return q.default

    def resolve(self, answers: Dict[str, Any]) -> Dict[str, Any]:
        """Build the full template context from fixed values + variant + answers."""
        ctx: Dict[str, Any] = dict(self.fixed)
        if self.variant_field:
            variant_val = answers.get(self.variant_field)
            if variant_val not in self.variants:
                raise ValueError(
                    f"{self.key}: {self.variant_field}={variant_val!r} is not a valid variant. "
                    f"Choose one of: {', '.join(self.variant_values())}"
                )
            variant = self.variants[variant_val]
            ctx.update(variant.get("fixed", {}))
            ctx[self.variant_field] = variant_val
        # Answers win last. Keep None values present (as falsy) so templates using
        # StrictUndefined can test optional fields with `{% if x %}` without raising.
        ctx.update(answers)
        return ctx


# --------------------------------------------------------------------------- #
# Shared question fragments
# --------------------------------------------------------------------------- #

def _q_name(default: Optional[str] = None) -> Question:
    # Becomes a filename, so it is kept well inside every filesystem's limit.
    return Question("name", "Adapter name (unique)", default=default, max_length=64,
                    help="Unique id referenced by API keys and other adapters.")


def _q_enabled() -> Question:
    return Question("enabled", "Enabled?", type="bool", default=True)


def _q_skill_name(default: Optional[str] = None) -> Question:
    return Question("skill_name", "Skill name (clients send this in skill=)", default=default,
                    max_length=64)


def _q_skill_description(default: Optional[str] = None) -> Question:
    return Question("skill_description", "Skill description", default=default,
                    max_length=500,
                    help="One line describing what the skill does. Can be AI-generated.")


def _q_routing_examples(default: Optional[List[str]] = None) -> Question:
    return Question("routing_examples", "Routing example phrases", type="list",
                    default=default if default is not None else [],
                    max_length=200, max_items=50,
                    help="Phrases that boost auto-routing to this skill. Can be AI-generated.")


# --------------------------------------------------------------------------- #
# Specs
# --------------------------------------------------------------------------- #

DOC_GENERATOR = AdapterSpec(
    key="doc-generator",
    title="Document generator",
    description="Generate PDF/Word/Excel/CSV/Markdown/PowerPoint documents from text or data.",
    template="doc_generator.yaml.j2",
    fixed={
        "type": "document_generation",
        "datasource": "none",
        "adapter": "multimodal",
        "implementation": _MULTIMODAL_IMPL,
    },
    variant_field="document_format",
    variants={
        "pdf": {"defaults": {"name": "pdf-generator", "skill_name": "PDF",
                             "skill_description": "Generate PDF documents from text descriptions or structured data",
                             "routing_examples": ["make a pdf", "create a pdf document", "export this as a pdf",
                                                  "save this as a pdf", "turn this into a pdf", "generate a pdf report"]}},
        "docx": {"defaults": {"name": "word-generator", "skill_name": "Word",
                              "skill_description": "Generate Word documents from text descriptions or structured data",
                              "routing_examples": ["make a word document", "create a docx", "export this as word",
                                                   "save this as a word file", "turn this into a word document"]}},
        "xlsx": {"defaults": {"name": "excel-generator", "skill_name": "Excel",
                              "skill_description": "Generate Excel spreadsheets from text descriptions or structured data",
                              "routing_examples": ["make an excel file", "create a spreadsheet", "export this as excel",
                                                   "save this as xlsx", "turn this into a spreadsheet"]}},
        "csv": {"defaults": {"name": "csv-generator", "skill_name": "CSV",
                             "skill_description": "Generate CSV files from text descriptions or structured data",
                             "routing_examples": ["make a csv", "create a csv file", "export this as csv",
                                                  "save this as a csv", "turn this into csv"]}},
        "md": {"defaults": {"name": "markdown-generator", "skill_name": "Markdown",
                            "skill_description": "Generate Markdown documents from text descriptions or structured data",
                            "routing_examples": ["make a markdown file", "create markdown", "export this as markdown",
                                                 "save this as md", "turn this into markdown"]}},
        "pptx": {"defaults": {"name": "pptx-generator", "skill_name": "PowerPoint",
                              "skill_description": "Generate PowerPoint presentations from text descriptions or structured data",
                              "routing_examples": ["make a powerpoint", "create a presentation", "export this as pptx",
                                                   "save this as a slide deck", "turn this into slides"]}},
    },
    questions=[
        Question("document_format", "Document format", choices=["pdf", "docx", "xlsx", "csv", "md", "pptx"]),
        _q_name(),
        _q_skill_name(),
        _q_skill_description(),
        _q_routing_examples(),
        Question("rewrite_provider", "Rewrite provider (text LLM that enriches the request)",
                 default="openai", help="Omit to use the global default."),
        Question("rewrite_model", "Rewrite model", default="gpt-5.4-mini"),
        Question("storage_backend", "Storage backend", default="filesystem"),
        Question("storage_root", "Storage root", default="./uploads", max_length=500),
        _q_enabled(),
    ],
)


MEDIA_GENERATOR = AdapterSpec(
    key="media-generator",
    title="Media generator",
    description="Generate images, videos, or audio from text prompts.",
    template="media_generator.yaml.j2",
    fixed={
        "datasource": "none",
        "adapter": "multimodal",
        "implementation": _MULTIMODAL_IMPL,
    },
    variant_field="media_type",
    variants={
        "image": {
            "fixed": {"type": "image_generation", "provider_field": "image_provider", "has_config": True,
                      "optional_parameters": ["session_id"]},
            "defaults": {"name": "image-generator", "skill_name": "Image", "provider_default": "gemini",
                         "skill_description": "Generate images from text descriptions using AI",
                         "routing_examples": ["draw a picture of", "generate an image of", "create an image",
                                              "paint a", "make a picture", "illustrate"]},
        },
        "video": {
            "fixed": {"type": "video_generation", "provider_field": "video_provider", "has_config": False,
                      "optional_parameters": ["session_id"]},
            "defaults": {"name": "video-generator", "skill_name": "Video", "provider_default": "xai",
                         "skill_description": "Generate short videos from text descriptions using AI",
                         "routing_examples": ["make a video of", "generate a short video", "create a video clip",
                                              "animate", "produce a video"]},
        },
        "audio": {
            "fixed": {"type": "audio_generation", "provider_field": "tts_provider", "has_config": True,
                      "optional_parameters": ["session_id", "tts_voice"]},
            "defaults": {"name": "audio-generator", "skill_name": "Audio", "provider_default": "gemini",
                         "skill_description": "Generate spoken audio from text using AI",
                         "routing_examples": ["read this aloud", "generate audio for", "make a voiceover",
                                              "turn this into speech", "narrate this"]},
        },
    },
    questions=[
        Question("media_type", "Media type", choices=["image", "video", "audio"]),
        _q_name(),
        _q_skill_name(),
        _q_skill_description(),
        _q_routing_examples(),
        Question("media_provider", "Media provider (override; blank to use the global default)", default=None),
        Question("rewrite_provider", "Rewrite provider (text LLM that enriches the prompt)", default="openai"),
        Question("rewrite_model", "Rewrite model", default="gpt-5.4-mini"),
        Question("storage_backend", "Storage backend", default="filesystem"),
        Question("storage_root", "Storage root", default="./uploads", max_length=500),
        _q_enabled(),
    ],
)


MULTIMODAL = AdapterSpec(
    key="multimodal",
    title="Multimodal (file retrieval)",
    description="Conditional RAG over uploaded files (documents/images/audio) with vision/STT/TTS support.",
    template="multimodal.yaml.j2",
    fixed={
        "type": "passthrough",
        "datasource": "none",
        "adapter": "multimodal",
        "implementation": _MULTIMODAL_IMPL,
        "retrieval_behavior": "conditional",
        "supports_file_ids": True,
        "skip_when_no_files": True,
        "requires_api_key_validation": True,
        "optional_parameters": ["file_ids", "api_key", "session_id"],
    },
    questions=[
        _q_name(default="simple-chat-with-files"),
        Question("inference_provider", "Inference provider (override; blank for global default)", default=None),
        Question("model", "Model (override; blank for global default)", default=None),
        Question("embedding_provider", "Embedding provider", default="openai"),
        Question("embedding_model", "Embedding model", default="text-embedding-3-small"),
        Question("vision_provider", "Vision provider (image files)", default="gemini"),
        Question("stt_provider", "STT provider (audio transcription)", default="openai"),
        Question("tts_provider", "TTS provider", default="gemini"),
        Question("available_skills", "Available skills (invokable via / picker)", type="list", default=[]),
        Question("auto_routable_skills", "Auto-routable skills (auto-only, not user-invokable)",
                 type="list", default=[]),
        Question("auto_skill_routing", "Enable automatic skill intent detection?", type="bool", default=True),
        Question("mcp_tools", "Enable opportunistic MCP tool calling?", type="bool", default=False),
        Question("mcp_servers", "Allowed MCP servers (blank = all enabled)", type="list", default=[]),
        Question("storage_backend", "Storage backend", default="filesystem"),
        Question("storage_root", "Storage root", default="./uploads", max_length=500),
        Question("max_file_size", "Max file size (bytes)", type="int", default=52428800,
                 min_value=1, max_value=1073741824),
        Question("chunking_strategy", "Chunking strategy", default="recursive",
                 choices=["fixed", "semantic", "token", "recursive"]),
        Question("chunk_size", "Chunk size", type="int", default=1000, min_value=1, max_value=100000),
        Question("chunk_overlap", "Chunk overlap", type="int", default=100, min_value=0, max_value=10000),
        Question("vector_store", "Vector store (see stores.yaml)", default="chroma"),
        Question("collection_prefix", "Collection prefix", default="files_", max_length=64),
        Question("requires_encryption", "Require encrypted file storage?", type="bool", default=False),
        Question("enable_audio_transcription", "Enable audio file transcription?", type="bool", default=False),
        Question("supported_types", "Supported file MIME types (blank = loader defaults)", type="list",
                 default=[], max_length=100, max_items=50,
                 help="Only emitted when audio transcription is enabled, e.g. \"audio/wav, audio/mpeg\"."),
        _q_enabled(),
    ],
)


PASSTHROUGH = AdapterSpec(
    key="passthrough",
    title="Passthrough / conversational",
    description="Pure conversational adapter with no retrieval; optional skill routing and MCP tools.",
    template="passthrough.yaml.j2",
    fixed={
        "type": "passthrough",
        "datasource": "none",
        "adapter": "conversational",
        "implementation": _CONVERSATIONAL_IMPL,
        "retrieval_behavior": "none",
    },
    questions=[
        _q_name(default="simple-chat"),
        Question("inference_provider", "Inference provider (override; blank for global default)", default=None),
        Question("model", "Model (override; blank for global default)", default=None),
        Question("available_skills", "Available skills (invokable via / picker)", type="list", default=[]),
        Question("auto_routable_skills", "Auto-routable skills (auto-only, not user-invokable)",
                 type="list", default=[]),
        Question("auto_skill_routing", "Enable automatic skill intent detection?", type="bool", default=False),
        Question("mcp_tools", "Enable opportunistic MCP tool calling?", type="bool", default=False),
        Question("mcp_servers", "Allowed MCP servers (blank = all enabled)", type="list", default=[]),
        _q_enabled(),
    ],
)


FETCH = AdapterSpec(
    key="fetch",
    title="Fetch",
    description="Fetch web page content from a URL (no LLM inference step).",
    template="fetch.yaml.j2",
    fixed={
        "type": "fetch",
        "datasource": "none",
        "adapter": "conversational",
        "implementation": _CONVERSATIONAL_IMPL,
    },
    questions=[
        _q_name(default="fetch"),
        _q_skill_name(default="Fetch"),
        _q_skill_description(default="Fetch and return web page content from a URL"),
        _q_routing_examples(default=["fetch this url", "get the contents of this page",
                                     "read this link for me", "what does this webpage say"]),
        Question("fetch_timeout", "Fetch timeout (seconds)", type="int", default=30,
                 min_value=1, max_value=600),
        Question("fetch_user_agent", "User agent", default="Mozilla/5.0 (compatible; OrbitBot/1.0)",
                 max_length=256),
        _q_enabled(),
    ],
)


MCP_AGENT = AdapterSpec(
    key="mcp-agent",
    title="MCP agent",
    description="Expose configured MCP servers as an agentic tool-calling skill.",
    template="mcp_agent.yaml.j2",
    fixed={
        "type": "mcp_agent",
        "datasource": "none",
        "adapter": "conversational",
        "implementation": _CONVERSATIONAL_IMPL,
    },
    questions=[
        _q_name(default="mcp-agent-chat"),
        Question("inference_provider", "Inference provider (must support native tool calling)", default="openai",
                 help="openai, anthropic, gemini, or xai."),
        Question("model", "Model", default="gpt-5.4-mini"),
        _q_skill_name(default="mcp-agent"),
        _q_skill_description(default="Use external MCP server tools to answer (agentic tool calling)"),
        Question("mcp_servers", "Allowed MCP servers (blank = all enabled)", type="list", default=[]),
        _q_enabled(),
    ],
)


WEB_SEARCH_NATIVE = AdapterSpec(
    key="web-search-native",
    title="Web search (provider-native)",
    description="Delegate web search to the LLM provider's built-in search tool (gemini/openai/xai).",
    template="web_search_native.yaml.j2",
    fixed={
        "type": "passthrough",
        "datasource": "none",
        "adapter": "conversational",
        "implementation": _CONVERSATIONAL_IMPL,
        "web_search_capability": True,
    },
    questions=[
        _q_name(default="web-search"),
        Question("inference_provider", "Inference provider (must support native search)", default="gemini",
                 choices=["gemini", "openai", "xai"]),
        Question("model", "Model", default="gemini-3.1-pro-preview"),
        _q_skill_name(default="web-search"),
        _q_skill_description(
            default="Search the web and answer with up-to-date information and citations"),
        _q_routing_examples(default=["search the web for", "look this up online",
                                     "what's the latest news on", "find current information about",
                                     "google this"]),
        _q_enabled(),
    ],
)


WEB_SEARCH_EXTERNAL = AdapterSpec(
    key="web-search-external",
    title="Web search (external provider)",
    description="Call a dedicated search API (DuckDuckGo/Brave/Serper/Tavily/SearXNG/Google PSE/Perplexity); any LLM synthesizes.",
    template="web_search_external.yaml.j2",
    fixed={
        "type": "web-search",
        "datasource": "none",
        "adapter": "conversational",
        "implementation": _CONVERSATIONAL_IMPL,
    },
    variant_field="search_provider",
    variants={
        "duckduckgo": {"defaults": {"name": "web-search-duckduckgo", "skill_name": "web-search-duckduckgo",
                                    "skill_description": "Search the web using DuckDuckGo (free, no API key)",
                                    "api_key": None}},
        "brave": {"defaults": {"name": "web-search-brave", "skill_name": "web-search-brave",
                               "skill_description": "Search the web using Brave Search API",
                               "api_key": "${BRAVE_SEARCH_API_KEY}"}},
        "searxng": {"defaults": {"name": "web-search-searxng", "skill_name": "web-search-searxng",
                                 "skill_description": "Search the web using a self-hosted SearXNG instance",
                                 "query_url": "${SEARXNG_URL}"}},
        "serper": {"defaults": {"name": "web-search-serper", "skill_name": "web-search-serper",
                                "skill_description": "Search Google via the Serper API",
                                "api_key": "${SERPER_API_KEY}"}},
        "tavily": {"defaults": {"name": "web-search-tavily", "skill_name": "web-search-tavily",
                                "skill_description": "Search the web using Tavily AI search",
                                "api_key": "${TAVILY_API_KEY}"}},
        "google_pse": {"defaults": {"name": "web-search-google-pse", "skill_name": "web-search-google-pse",
                                    "skill_description": "Search Google via Programmable Search Engine",
                                    "api_key": "${GOOGLE_PSE_API_KEY}", "search_engine_id": "${GOOGLE_PSE_ENGINE_ID}"}},
        "perplexity": {"defaults": {"name": "web-search-perplexity", "skill_name": "web-search-perplexity",
                                    "skill_description": "Search the web using Perplexity Search API",
                                    "api_key": "${PERPLEXITY_API_KEY}"}},
    },
    questions=[
        Question("search_provider", "Search provider",
                 choices=["duckduckgo", "brave", "searxng", "serper", "tavily", "google_pse", "perplexity"]),
        _q_name(),
        _q_skill_name(),
        _q_skill_description(),
        Question("inference_provider", "Inference provider (synthesizes the answer)", default="anthropic"),
        Question("model", "Model", default="claude-haiku-4-5-20251001"),
        Question("result_count", "Number of results to fetch", type="int", default=5,
                 min_value=1, max_value=50),
        Question("api_key", "API key (env ref, e.g. ${BRAVE_SEARCH_API_KEY})", default=None),
        Question("query_url", "Instance URL (SearXNG only)", default=None, max_length=500),
        Question("search_engine_id", "Search engine id (Google PSE only)", default=None),
        _q_enabled(),
    ],
)


SPEC_REGISTRY: Dict[str, AdapterSpec] = {
    s.key: s
    for s in [
        PASSTHROUGH,
        MULTIMODAL,
        DOC_GENERATOR,
        MEDIA_GENERATOR,
        FETCH,
        MCP_AGENT,
        WEB_SEARCH_NATIVE,
        WEB_SEARCH_EXTERNAL,
    ]
}


def get_spec(key: str) -> AdapterSpec:
    if key not in SPEC_REGISTRY:
        raise KeyError(f"Unknown adapter spec '{key}'. Available: {', '.join(SPEC_REGISTRY)}")
    return SPEC_REGISTRY[key]


def serialize_spec(spec: AdapterSpec) -> Dict[str, Any]:
    """JSON form of a spec, used by the admin UI form builder and `--list --json`.

    Each question carries its per-variant defaults so a client can re-default the
    form when the variant changes without another round-trip.
    """
    variant_values = spec.variant_values()
    questions = []
    for q in spec.questions:
        item = asdict(q)
        item.update(question_limits(q))  # resolved bounds, so the form can enforce them
        if variant_values:
            item["variant_defaults"] = {v: spec.question_default(q, v) for v in variant_values}
        questions.append(item)

    return {
        "key": spec.key,
        "title": spec.title,
        "description": spec.description,
        "variant_field": spec.variant_field,
        "variants": variant_values,
        "questions": questions,
    }


def serialize_registry() -> List[Dict[str, Any]]:
    """JSON form of every registered spec, in registry order."""
    return [serialize_spec(spec) for spec in SPEC_REGISTRY.values()]
