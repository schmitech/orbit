"""Environment and repo-path resolution. Plain values, no config framework."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
REPO_ROOT = HERE.parent.parent
MCP_SERVER_DIR = REPO_ROOT / "examples" / "mcp-server"
SYSTEM_PROMPT_PATH = MCP_SERVER_DIR / "business-mcp-prompt.md"
SKILLS_DIR = REPO_ROOT / "config" / "skills"
CASES_DIR = HERE / "cases"
RESULTS_DIR = HERE / "results"

# Tools that mutate the server's in-memory data. Ground-truth resolution is
# forbidden from calling these — see ground_truth.resolve().
MUTATING_TOOLS = frozenset(
    {"create_support_ticket", "update_support_ticket", "delete_support_ticket"}
)


def _load_dotenv() -> None:
    """Load .env files without overriding anything already in the environment.

    Local file first so it can shadow the repo's, then the repo root, which is
    where ORBIT's own OPENAI_API_KEY / ANTHROPIC_API_KEY already live.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    for path in (HERE / ".env", REPO_ROOT / ".env"):
        if path.exists():
            load_dotenv(path, override=False)


@dataclass(frozen=True)
class Settings:
    mcp_url: str
    mcp_token: str
    openai_key: str | None
    anthropic_key: str | None
    langsmith_key: str | None
    langsmith_project: str
    autostart: bool

    @property
    def health_url(self) -> str:
        return self.mcp_url.rsplit("/", 1)[0] + "/health"

    @property
    def auth_headers(self) -> dict[str, str]:
        # An empty MCP_TOKEN disables auth on the server side, so send nothing.
        return {"Authorization": f"Bearer {self.mcp_token}"} if self.mcp_token else {}

    @property
    def langsmith_enabled(self) -> bool:
        return bool(self.langsmith_key)

    @staticmethod
    def from_env() -> Settings:
        _load_dotenv()
        return Settings(
            mcp_url=os.getenv("MCP_URL", "http://127.0.0.1:9999/mcp"),
            mcp_token=os.getenv("MCP_TOKEN", "test-secret"),
            openai_key=os.getenv("OPENAI_API_KEY") or None,
            anthropic_key=os.getenv("ANTHROPIC_API_KEY") or None,
            langsmith_key=os.getenv("LANGSMITH_API_KEY") or None,
            langsmith_project=os.getenv("LANGSMITH_PROJECT", "orbit-mcp-server-test"),
            autostart=os.getenv("ORBIT_MCP_TEST_AUTOSTART", "0") == "1",
        )


def strip_frontmatter(text: str) -> str:
    """Drop a leading YAML frontmatter block from a SKILL.md body.

    ORBIT injects the procedure, not the metadata, so the harness must too.
    """
    if not text.startswith("---"):
        return text.strip()
    end = text.find("\n---", 3)
    return text[end + 4 :].strip() if end != -1 else text.strip()


def load_system_prompt(playbook: str | None = None) -> str:
    """The business system prompt, optionally with one playbook appended.

    `playbook` is a directory name under config/skills/. Appending the playbook
    body mirrors what ORBIT's tool-skill injection does at runtime, which is
    what makes the base/playbook comparison meaningful.
    """
    prompt = SYSTEM_PROMPT_PATH.read_text().strip()
    if not playbook:
        return prompt
    body = strip_frontmatter((SKILLS_DIR / playbook / "SKILL.md").read_text())
    return f"{prompt}\n\n---\n\n## Tool playbook: {playbook}\n\n{body}"
