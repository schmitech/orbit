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

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Fully-qualified implementation classes (verified against config/adapters/*.yaml).
_MULTIMODAL_IMPL = "implementations.passthrough.multimodal.MultimodalImplementation"
_CONVERSATIONAL_IMPL = "implementations.passthrough.conversational.ConversationalImplementation"


@dataclass
class Question:
    """One wizard prompt. Rendered by cli.py and (later) the admin UI."""

    field: str
    prompt: str
    type: str = "str"  # one of: str, int, bool, list
    default: Any = None
    choices: Optional[List[str]] = None
    help: str = ""
    ai_fillable: bool = False  # soft field the enricher may fill (skill_description, routing_examples)


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

    def soft_fields(self) -> List[str]:
        return [q.field for q in self.questions if q.ai_fillable]


# --------------------------------------------------------------------------- #
# Shared question fragments
# --------------------------------------------------------------------------- #

def _q_name(default: Optional[str] = None) -> Question:
    return Question("name", "Adapter name (unique)", default=default,
                    help="Unique id referenced by API keys and other adapters.")


def _q_enabled() -> Question:
    return Question("enabled", "Enabled?", type="bool", default=True)


def _q_skill_name(default: Optional[str] = None) -> Question:
    return Question("skill_name", "Skill name (clients send this in skill=)", default=default)


def _q_skill_description() -> Question:
    return Question("skill_description", "Skill description", ai_fillable=True,
                    help="One line describing what the skill does. Can be AI-generated.")


def _q_routing_examples() -> Question:
    return Question("routing_examples", "Routing example phrases", type="list", default=[],
                    ai_fillable=True,
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
        Question("storage_root", "Storage root", default="./uploads"),
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
        Question("storage_root", "Storage root", default="./uploads"),
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
        Question("skill_description", "Skill description", default="Fetch and return web page content from a URL",
                 ai_fillable=True),
        Question("routing_examples", "Routing example phrases", type="list", ai_fillable=True,
                 default=["fetch this url", "get the contents of this page", "read this link for me",
                          "what does this webpage say"]),
        Question("fetch_timeout", "Fetch timeout (seconds)", type="int", default=30),
        Question("fetch_user_agent", "User agent", default="Mozilla/5.0 (compatible; OrbitBot/1.0)"),
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
        Question("skill_description", "Skill description",
                 default="Use external MCP server tools to answer (agentic tool calling)", ai_fillable=True),
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
        Question("skill_description", "Skill description",
                 default="Search the web and answer with up-to-date information and citations", ai_fillable=True),
        Question("routing_examples", "Routing example phrases", type="list", ai_fillable=True,
                 default=["search the web for", "look this up online", "what's the latest news on",
                          "find current information about", "google this"]),
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
        Question("result_count", "Number of results to fetch", type="int", default=5),
        Question("api_key", "API key (env ref, e.g. ${BRAVE_SEARCH_API_KEY})", default=None),
        Question("query_url", "Instance URL (SearXNG only)", default=None),
        Question("search_engine_id", "Search engine id (Google PSE only)", default=None),
        _q_enabled(),
    ],
)


SPEC_REGISTRY: Dict[str, AdapterSpec] = {
    s.key: s
    for s in [
        DOC_GENERATOR,
        MEDIA_GENERATOR,
        PASSTHROUGH,
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
