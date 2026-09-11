"""The dataset and the target must cover the same cases.

LangSmith runs every example the dataset holds, and the target resolves each
one through its own case map. If the two sets disagree, the target raises
KeyError before any evaluator runs — so this pins the invariant rather than the
implementation, with a fake client so no network or API key is involved.
"""

from __future__ import annotations

import pytest
from mcpeval import langsmith_sync
from mcpeval.schema import Case, Suite

pytestmark = [pytest.mark.unit]


def _suite() -> Suite:
    return Suite(
        name="support_tickets",
        playbook="support-crud",
        cases=(
            Case(id="read_only", query="q", suite="support_tickets", playbook=None, checks=()),
            Case(
                id="deletes_a_ticket",
                query="q",
                suite="support_tickets",
                playbook=None,
                checks=(),
                mutating=True,
            ),
        ),
    )


class FakeExample:
    def __init__(self, example_id: str, case_id: str):
        self.id = example_id
        self.metadata = {"case_id": case_id}


class FakeClient:
    """Records what push_dataset does instead of talking to LangSmith."""

    def __init__(self, existing: list[FakeExample] | None = None):
        self.existing = existing or []
        self.created: list[dict] = []
        self.deleted: list[str] = []

    def has_dataset(self, dataset_name: str) -> bool:
        return True

    def read_dataset(self, dataset_name: str):
        return type("Dataset", (), {"id": "ds-1"})()

    def list_examples(self, dataset_id: str):
        return list(self.existing)

    def create_examples(self, dataset_id: str, examples: list[dict]):
        self.created.extend(examples)

    def delete_examples(self, example_ids, hard_delete: bool = False):
        self.deleted.extend(example_ids)


@pytest.fixture
def fake_langsmith(monkeypatch):
    def install(client: FakeClient) -> FakeClient:
        monkeypatch.setattr("langsmith.Client", lambda *a, **k: client)
        return client

    return install


def test_eligible_cases_excludes_mutating():
    assert set(langsmith_sync.eligible_cases(_suite())) == {"read_only"}


def test_push_dataset_uploads_only_eligible_cases(fake_langsmith):
    client = fake_langsmith(FakeClient())
    langsmith_sync.push_dataset(_suite(), "orbit-mcp/test")

    uploaded = {example["inputs"]["case_id"] for example in client.created}
    assert uploaded == {"read_only"}, "a mutating case in the dataset makes the target raise KeyError"


def test_push_dataset_removes_already_uploaded_mutating_examples(fake_langsmith):
    # A dataset written before the filter existed still holds the mutating case.
    client = fake_langsmith(
        FakeClient(existing=[FakeExample("ex-1", "read_only"), FakeExample("ex-2", "deletes_a_ticket")])
    )
    langsmith_sync.push_dataset(_suite(), "orbit-mcp/test")

    assert client.deleted == ["ex-2"]
    assert client.created == [], "read_only was already present and must not be duplicated"


def test_dataset_and_target_case_sets_agree(fake_langsmith):
    suite = _suite()
    client = fake_langsmith(FakeClient())
    langsmith_sync.push_dataset(suite, "orbit-mcp/test")

    in_dataset = {example["inputs"]["case_id"] for example in client.created}
    assert in_dataset == set(langsmith_sync.eligible_cases(suite))
