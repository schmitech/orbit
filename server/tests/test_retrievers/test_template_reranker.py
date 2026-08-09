"""
Tests for TemplateReranker (server/retrievers/implementations/intent/template_reranker.py).

Covers generic boosting (entity/action/qualifier/tag/nl_example similarity),
score clamping, re-sort order, explain_ranking output, and the action_verbs
list-mutation bug (fixed: action_verbs.get(action, []) must not be appended
to in place, since domain_config vocabulary lists are shared across calls).
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from retrievers.implementations.intent.template_reranker import TemplateReranker


def make_domain_config(action_verbs=None, entity_synonyms=None):
    return {
        "domain_name": "Test Domain",
        "vocabulary": {
            "action_verbs": action_verbs or {},
            "entity_synonyms": entity_synonyms or {},
        },
        "entities": {},
        "fields": {},
    }


def make_template_info(template_id, similarity, semantic_tags=None, tags=None, nl_examples=None):
    template = {
        "id": template_id,
        "description": f"Template {template_id}",
        "semantic_tags": semantic_tags or {},
        "tags": tags or [],
        "nl_examples": nl_examples or [],
    }
    return {"template": template, "raw_template": template, "similarity": similarity}


class TestGenericBoosting:
    def test_entity_match_boosts_score(self):
        reranker = TemplateReranker(make_domain_config())
        templates = [make_template_info(
            "find_customer", 0.5, semantic_tags={"primary_entity": "customer", "action": ""}
        )]
        result = reranker.rerank_templates(templates, "find the customer record")
        assert result[0]["similarity"] > 0.5
        assert result[0]["boost_applied"] > 0

    def test_entity_synonym_boosts_score(self):
        reranker = TemplateReranker(make_domain_config(entity_synonyms={"customer": ["client", "buyer"]}))
        templates = [make_template_info(
            "find_customer", 0.5, semantic_tags={"primary_entity": "customer", "action": ""}
        )]
        result = reranker.rerank_templates(templates, "find the client record")
        assert result[0]["boost_applied"] > 0

    def test_action_verb_match_boosts_score(self):
        reranker = TemplateReranker(make_domain_config(action_verbs={"find": ["locate", "search"]}))
        templates = [make_template_info(
            "search_tpl", 0.5, semantic_tags={"primary_entity": "", "action": "find"}
        )]
        result = reranker.rerank_templates(templates, "please locate this item")
        assert result[0]["boost_applied"] > 0

    def test_qualifier_match_boosts_score(self):
        reranker = TemplateReranker(make_domain_config())
        templates = [make_template_info(
            "tpl", 0.5, semantic_tags={"primary_entity": "", "action": "", "qualifiers": ["urgent"]}
        )]
        result = reranker.rerank_templates(templates, "this is an urgent request")
        assert result[0]["boost_applied"] > 0

    def test_tag_match_boosts_score(self):
        reranker = TemplateReranker(make_domain_config())
        templates = [make_template_info("tpl", 0.5, tags=["invoice"])]
        result = reranker.rerank_templates(templates, "show me the invoice")
        assert result[0]["boost_applied"] > 0

    def test_dict_tags_are_skipped_without_error(self):
        reranker = TemplateReranker(make_domain_config())
        templates = [make_template_info("tpl", 0.5, tags=[{"unexpected": "dict"}])]
        result = reranker.rerank_templates(templates, "any query")
        assert result[0]["similarity"] == 0.5

    def test_nl_example_similarity_boosts_score(self):
        reranker = TemplateReranker(make_domain_config())
        templates = [make_template_info(
            "tpl", 0.5, nl_examples=["show me all employees in engineering"]
        )]
        result = reranker.rerank_templates(templates, "show me all employees in engineering")
        assert result[0]["boost_applied"] > 0

    def test_no_match_produces_zero_boost(self):
        reranker = TemplateReranker(make_domain_config())
        templates = [make_template_info("tpl", 0.5)]
        result = reranker.rerank_templates(templates, "completely unrelated text")
        assert result[0]["boost_applied"] == 0.0
        assert result[0]["similarity"] == 0.5


class TestScoreClampingAndOrdering:
    def test_similarity_clamped_to_one(self):
        reranker = TemplateReranker(make_domain_config(action_verbs={"find": ["locate"]}))
        templates = [make_template_info(
            "tpl", 0.95,
            semantic_tags={"primary_entity": "customer", "action": "find", "qualifiers": ["urgent"]},
            tags=["customer"],
            nl_examples=["find the urgent customer record"],
        )]
        result = reranker.rerank_templates(templates, "find the urgent customer record")
        assert result[0]["similarity"] <= 1.0

    def test_resorts_by_adjusted_similarity(self):
        reranker = TemplateReranker(make_domain_config())
        low_but_boosted = make_template_info(
            "boosted", 0.3, semantic_tags={"primary_entity": "invoice", "action": ""}
        )
        high_no_boost = make_template_info("unboosted", 0.6)
        result = reranker.rerank_templates([high_no_boost, low_but_boosted], "find the invoice")
        assert result[0]["template"]["id"] == "boosted"


class TestActionVerbsMutationRegression:
    def test_repeated_calls_do_not_grow_action_verbs_list(self):
        """action_verbs.get(action, []) must be copied before .append(action);
        otherwise repeated rerank_templates() calls on the same retriever
        instance mutate the shared domain_config vocabulary list, inflating
        boosts (and eval-harness scores) more with every subsequent query."""
        domain_config = make_domain_config(action_verbs={"find": ["locate", "search"]})
        reranker = TemplateReranker(domain_config)

        def templates_factory():
            return [make_template_info("tpl", 0.5, semantic_tags={"primary_entity": "", "action": "find"})]

        for _ in range(5):
            reranker.rerank_templates(templates_factory(), "please find this")

        assert reranker.domain_config.vocabulary["action_verbs"]["find"] == ["locate", "search"]


class TestExplainRanking:
    def test_explain_ranking_includes_top_templates(self):
        reranker = TemplateReranker(make_domain_config())
        templates = reranker.rerank_templates(
            [make_template_info("tpl_a", 0.9), make_template_info("tpl_b", 0.5)],
            "irrelevant",
        )
        explanation = reranker.explain_ranking(templates)
        assert "tpl_a" in explanation
        assert "tpl_b" in explanation
        assert "Boost" in explanation

    def test_explain_ranking_limits_to_top_five(self):
        reranker = TemplateReranker(make_domain_config())
        templates = reranker.rerank_templates(
            [make_template_info(f"tpl_{i}", 0.9 - i * 0.01) for i in range(8)],
            "irrelevant",
        )
        explanation = reranker.explain_ranking(templates)
        assert "tpl_6" not in explanation
        assert "tpl_7" not in explanation
