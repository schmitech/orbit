"""
Template diagnostics utility for testing intent retriever templates
without going through the full LLM inference pipeline.

Exercises: template search → parameter extraction → query execution
and reports detailed diagnostics at each step.
"""

import logging
import time
import traceback
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _get_retriever_type_name(retriever) -> str:
    """Get a human-readable type name for the retriever."""
    return type(retriever).__name__


def _detect_query_type(template: Dict[str, Any]) -> str:
    """Detect the query type from template keys."""
    if template.get('sql_template') or template.get('sql'):
        return "sql"
    if template.get('graphql_template'):
        return "graphql"
    if template.get('mongodb_query'):
        return "mongodb"
    if template.get('endpoint_template'):
        return "http"
    if template.get('query_template'):
        return "elasticsearch"
    if template.get('function_schema'):
        return "agent"
    return "unknown"


def _extract_query_template(template: Dict[str, Any]) -> Optional[str]:
    """Extract the raw query template string from a template dict."""
    for key in ('sql_template', 'sql', 'graphql_template', 'mongodb_query',
                'endpoint_template', 'query_template'):
        val = template.get(key)
        if val:
            return val
    return None


def _serialize_template_candidate(tmpl_info: Dict[str, Any], include_template: bool = False) -> Dict[str, Any]:
    """Serialize a template match for the response."""
    template = tmpl_info.get('template', {})
    entry = {
        "template_id": template.get('id', 'unknown'),
        "similarity": round(tmpl_info.get('similarity', 0), 4),
        "description": template.get('description', ''),
        "nl_examples": template.get('nl_examples', []),
        "category": template.get('category', ''),
        "rescued_by_nl_example": tmpl_info.get('_rescued_by_nl_example', False),
    }
    if include_template:
        query_type = _detect_query_type(template)
        entry["query_type"] = query_type
        entry["query_template"] = _extract_query_template(template)
        entry["parameters_defined"] = [
            {
                "name": p.get('name'),
                "type": p.get('type', 'string'),
                "required": p.get('required', False),
                "description": p.get('description', ''),
                "default": p.get('default'),
            }
            for p in template.get('parameters', [])
        ]
    return entry


# ---------------------------------------------------------------------------
# New diagnostic collectors
# ---------------------------------------------------------------------------

async def _collect_vector_store_info(retriever) -> Optional[Dict[str, Any]]:
    """Collect vector store and embedding health info."""
    try:
        info: Dict[str, Any] = {}
        template_store = getattr(retriever, 'template_store', None)
        if template_store:
            stats = await template_store.get_statistics()
            info["store_type"] = stats.get('store_type', '?')
            info["collection_name"] = stats.get('collection_name', '?')
            info["total_vectors"] = stats.get('total_templates', 0)
            info["cached_templates"] = stats.get('cached_templates', 0)
            info["embedding_dimension"] = stats.get('embedding_dimension')
            collection_dim = stats.get('collection_metadata', {}).get('dimension')
            if collection_dim:
                info["embedding_dimension"] = collection_dim

        embedding_client = getattr(retriever, 'embedding_client', None)
        info["embedding_provider"] = getattr(retriever, '_embedding_provider', '?')
        info["embedding_model"] = getattr(embedding_client, 'model', getattr(embedding_client, 'model_name', '?'))

        # Check dimension match by doing a trivial embed
        if embedding_client and info.get("embedding_dimension"):
            try:
                test_emb = await embedding_client.embed_query("test")
                if test_emb:
                    info["query_embedding_dimension"] = len(test_emb)
                    info["dimension_match"] = len(test_emb) == info["embedding_dimension"]
            except Exception:
                pass

        return info
    except Exception as e:
        logger.debug(f"Could not collect vector store info: {e}")
        return {"error": str(e)}


def _collect_template_inventory(retriever) -> Optional[Dict[str, Any]]:
    """List all loaded templates with summary info."""
    try:
        domain_adapter = getattr(retriever, 'domain_adapter', None)
        if not domain_adapter:
            return None
        all_templates = domain_adapter.get_all_templates()
        if not all_templates:
            return {"total_templates": 0, "templates": []}

        templates_summary = []
        for tmpl in all_templates:
            templates_summary.append({
                "id": tmpl.get('id', '?'),
                "description": tmpl.get('description', ''),
                "nl_examples_count": len(tmpl.get('nl_examples', [])),
                "parameters_count": len(tmpl.get('parameters', [])),
                "query_type": _detect_query_type(tmpl),
                "has_semantic_tags": bool(tmpl.get('semantic_tags')),
            })
        return {"total_templates": len(templates_summary), "templates": templates_summary}
    except Exception as e:
        logger.debug(f"Could not collect template inventory: {e}")
        return {"error": str(e)}


def _collect_domain_info(retriever) -> Optional[Dict[str, Any]]:
    """Collect domain config summary: entities, synonyms, fields."""
    try:
        domain_adapter = getattr(retriever, 'domain_adapter', None)
        if not domain_adapter:
            return None
        domain_config_dict = domain_adapter.get_domain_config()
        if not domain_config_dict:
            return None

        # Import here to avoid circular imports at module level
        from retrievers.implementations.intent.domain import DomainConfig
        if isinstance(domain_config_dict, DomainConfig):
            dc = domain_config_dict
        else:
            dc = DomainConfig(domain_config_dict)

        entity_synonyms = {}
        for name in dc.entities:
            syns = dc.get_entity_synonyms(name)
            if syns:
                entity_synonyms[name] = syns

        field_synonyms = {}
        for fname, syns in dc.field_synonyms.items():
            if syns:
                field_synonyms[fname] = syns

        searchable = [f.name for f in dc.get_searchable_fields()]
        filterable = [f.name for f in dc.get_filterable_fields()]

        return {
            "domain_name": dc.domain_name,
            "domain_type": dc.domain_type,
            "entities": list(dc.entities.keys()),
            "entity_synonyms": entity_synonyms,
            "field_synonyms": field_synonyms,
            "searchable_fields": searchable,
            "filterable_fields": filterable,
        }
    except Exception as e:
        logger.debug(f"Could not collect domain info: {e}")
        return {"error": str(e)}


def _collect_semantic_analysis(query: str, template: Dict[str, Any], retriever=None) -> Dict[str, Any]:
    """Analyse how query words align with the selected template's semantic tags."""
    query_words = query.lower().split()
    tags = template.get('semantic_tags', {})
    if not tags:
        return {"query_words": query_words, "template_has_semantic_tags": False}

    primary_entity = tags.get('primary_entity', '')
    action = tags.get('action', '')
    qualifiers = tags.get('qualifiers', [])

    # Check entity match (including synonyms)
    entity_match = False
    entity_variants = [primary_entity]
    if retriever:
        domain_adapter = getattr(retriever, 'domain_adapter', None)
        if domain_adapter:
            try:
                dc_dict = domain_adapter.get_domain_config()
                from retrievers.implementations.intent.domain import DomainConfig
                dc = dc_dict if isinstance(dc_dict, DomainConfig) else DomainConfig(dc_dict or {})
                entity_variants += dc.get_entity_synonyms(primary_entity)
            except Exception:
                pass
    for variant in entity_variants:
        if variant and variant.lower() in query.lower():
            entity_match = True
            break

    action_match = bool(action and action.lower() in query.lower())
    matched_qualifiers = [q for q in qualifiers if q.lower() in query.lower()]

    return {
        "query_words": query_words,
        "template_has_semantic_tags": True,
        "primary_entity": primary_entity,
        "action": action,
        "qualifiers": qualifiers,
        "entity_match": entity_match,
        "action_match": action_match,
        "matched_qualifiers": matched_qualifiers,
    }


def _collect_extraction_trace(retriever, query: str, template: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Build a detailed per-parameter extraction trace that mirrors the
    DomainParameterExtractor.extract_parameters() resolution journey.

    For each template parameter, shows:
    - Which resolution step found a value (or that none did)
    - The actual regex patterns available for that parameter
    - Whether validation/coercion succeeded or failed
    - Whether LLM fallback would be triggered
    """
    try:
        extractor = getattr(retriever, 'parameter_extractor', None)
        if not extractor:
            return None

        patterns = getattr(extractor, 'patterns', {})
        value_extractor = getattr(extractor, 'value_extractor', None)
        validator = getattr(extractor, 'validator', None)

        # --- Global info ---
        trace: Dict[str, Any] = {
            "patterns_available": len(patterns),
            "pattern_regexes": {},
        }

        # Show the actual regex for each pattern (via get_patterns_info)
        if hasattr(extractor, 'get_patterns_info'):
            trace["pattern_regexes"] = extractor.get_patterns_info()
        else:
            trace["pattern_regexes"] = {k: p.pattern for k, p in patterns.items()}

        # --- First pass: bulk pattern scan ---
        first_pass_matches: Dict[str, Any] = {}
        if value_extractor:
            try:
                first_pass_matches = value_extractor.extract_all_values(query) or {}
            except Exception as e:
                trace["first_pass_error"] = str(e)
        trace["first_pass_matches"] = {k: _coerce_value(v) for k, v in first_pass_matches.items()}

        # --- Per-parameter trace ---
        template_params = template.get('parameters', [])
        param_traces = []
        missing_required = []

        for param in template_params:
            param_name = param.get('name', '?')
            param_type = param.get('type') or param.get('data_type', 'string')
            entity = param.get('entity')
            field = param.get('field')
            required = param.get('required', False)
            default = param.get('default')

            pt: Dict[str, Any] = {
                "name": param_name,
                "type": param_type,
                "entity": entity,
                "field": field,
                "required": required,
                "has_default": default is not None,
                "resolution": "unresolved",
                "value": None,
            }

            # Step 1: Check entity.field key in first-pass matches
            value = None
            if entity and field:
                key = f"{entity}.{field}"
                pt["pattern_key"] = key
                pt["pattern_exists"] = key in patterns
                if key in patterns:
                    pt["pattern_regex"] = patterns[key].pattern
                if key in first_pass_matches:
                    value = first_pass_matches[key]
                    pt["resolution"] = "entity_field_pattern"
            elif param_name in first_pass_matches:
                value = first_pass_matches[param_name]
                pt["resolution"] = "param_name_pattern"

            # Step 2: Context extraction (entity.field only)
            if value is None and entity and field and value_extractor:
                try:
                    value = value_extractor.extract_value(query, entity, field, param_type)
                    if value is not None:
                        pt["resolution"] = "context_extraction"
                except Exception:
                    pass

            # Step 3: Template parameter extraction (non-entity params)
            if value is None and not (entity and field) and value_extractor:
                try:
                    value = value_extractor.extract_template_parameter(query, param)
                    if value is not None:
                        pt["resolution"] = "template_parameter"
                except Exception:
                    pass

            # Step 4: Validation / coercion
            if value is not None:
                pt["raw_value"] = _coerce_value(value)
                if entity and field and validator:
                    try:
                        is_valid, error_msg = validator.validate(value, entity, field)
                        if not is_valid:
                            pt["resolution"] = "validation_failed"
                            pt["validation_error"] = str(error_msg)
                            value = None
                    except Exception as e:
                        pt["validation_error"] = str(e)
                else:
                    # Type coercion for non-entity params
                    if hasattr(extractor, '_coerce_parameter_value'):
                        coerced = extractor._coerce_parameter_value(value, param_type, param_name)
                        if coerced is None and value is not None:
                            pt["resolution"] = "coercion_failed"
                            pt["coercion_error"] = f"Could not coerce {repr(value)} to {param_type}"
                            value = None
                        else:
                            value = coerced

            # Step 5: Would LLM fallback be triggered?
            if value is None and required:
                pt["llm_fallback_needed"] = True
                missing_required.append(param_name)
            elif value is None and default is not None:
                pt["resolution"] = "default"
                pt["value"] = _coerce_value(default)
            elif value is not None:
                pt["value"] = _coerce_value(value)

            if value is None and pt["resolution"] == "unresolved":
                pt["resolution"] = "not_found"

            param_traces.append(pt)

        trace["per_parameter"] = param_traces
        if missing_required:
            trace["llm_fallback_params"] = missing_required

        return trace
    except Exception as e:
        logger.debug(f"Could not collect extraction trace: {e}")
        return {"error": str(e)}


async def _try_all_templates(
    retriever,
    eligible_templates: List[Dict[str, Any]],
    query: str,
    execute: bool,
) -> List[Dict[str, Any]]:
    """
    Try each eligible template (like get_relevant_context does) and record the outcome.
    Stops at first success if execute=True, otherwise records extraction outcome for all.
    """
    tried = []
    for tmpl_info in eligible_templates:
        template = tmpl_info['template']
        similarity = tmpl_info.get('similarity', 0)
        tid = template.get('id', '?')
        entry: Dict[str, Any] = {
            "template_id": tid,
            "similarity": round(similarity, 4),
        }

        # Parameter extraction
        try:
            extractor = getattr(retriever, 'parameter_extractor', None)
            if extractor:
                parameters = await extractor.extract_parameters(query, template)
                validation_errors = extractor.validate_parameters(parameters)
                if validation_errors:
                    entry["outcome"] = "param_validation_failed"
                    entry["detail"] = "; ".join(str(e) for e in validation_errors)
                    tried.append(entry)
                    continue
            elif hasattr(retriever, '_extract_parameters'):
                parameters = await retriever._extract_parameters(query, template)
                validation_errors = []
            else:
                parameters = {}
                validation_errors = []

            entry["parameters"] = _coerce_value(parameters)
        except Exception as e:
            entry["outcome"] = "extraction_error"
            entry["detail"] = str(e)
            tried.append(entry)
            continue

        # Execution
        if execute:
            try:
                results, error = await retriever._execute_template(template, parameters)
                if error:
                    entry["outcome"] = "execution_error"
                    entry["detail"] = error
                    # If datasource is down, stop trying
                    if 'not initialized' in error.lower() or 'connection' in error.lower():
                        tried.append(entry)
                        break
                else:
                    entry["outcome"] = "success"
                    entry["row_count"] = len(results) if results else 0
                    tried.append(entry)
                    break  # Stop at first success
            except Exception as e:
                entry["outcome"] = "execution_exception"
                entry["detail"] = str(e)
                tried.append(entry)
                continue
        else:
            entry["outcome"] = "not_executed"
            tried.append(entry)

    return tried


# ---------------------------------------------------------------------------
# Main diagnostic functions
# ---------------------------------------------------------------------------

async def diagnose_template_query(
    retriever,
    query: str,
    max_templates: int = 5,
    execute: bool = True,
    include_all_candidates: bool = False,
    verbose: bool = False,
) -> Dict[str, Any]:
    """
    Run diagnostic pipeline on an intent retriever and return detailed results.

    Works with IntentSQLRetriever, IntentHTTPRetriever, and CompositeIntentRetriever.
    Exercises: template search → reranking → parameter extraction → query rendering → execution.

    Args:
        retriever: An initialized intent retriever instance.
        query: The natural language query to test.
        max_templates: Maximum template candidates to return.
        execute: Whether to execute the query against the datasource.
        include_all_candidates: Include full details for all candidates, not just the selected one.
        verbose: Include extended diagnostics (vector store info, template inventory, domain info, semantic analysis).

    Returns:
        Diagnostic results dict.
    """
    from retrievers.base.intent_composite_base import CompositeIntentRetriever

    result = {
        "adapter_name": getattr(retriever, 'adapter_name', getattr(retriever, 'name', 'unknown')),
        "adapter_type": _get_retriever_type_name(retriever),
        "query": query,
        "timing": {},
        "vector_store_info": None,
        "template_inventory": None,
        "domain_info": None,
        "template_search": None,
        "reranking": None,
        "selected_template": None,
        "parameter_extraction": None,
        "rendered_query": None,
        "execution": None,
        "templates_tried": None,
        "semantic_analysis": None,
        "composite_routing": None,
    }

    # Composite retrievers have a different flow
    if isinstance(retriever, CompositeIntentRetriever):
        return await _diagnose_composite(retriever, query, max_templates, execute, include_all_candidates, verbose, result)

    return await _diagnose_intent(retriever, query, max_templates, execute, include_all_candidates, verbose, result)


async def _diagnose_intent(
    retriever,
    query: str,
    max_templates: int,
    execute: bool,
    include_all_candidates: bool,
    verbose: bool,
    result: Dict[str, Any],
) -> Dict[str, Any]:
    """Diagnose a single intent retriever (SQL or HTTP based)."""
    total_start = time.monotonic()

    # --- Verbose: collect adapter metadata ---
    if verbose:
        result["vector_store_info"] = await _collect_vector_store_info(retriever)
        result["template_inventory"] = _collect_template_inventory(retriever)
        result["domain_info"] = _collect_domain_info(retriever)

    # --- Step 1: Template Search ---
    try:
        t0 = time.monotonic()
        templates = await retriever._find_best_templates(query)
        search_ms = round((time.monotonic() - t0) * 1000, 1)
        result["timing"]["template_search_ms"] = search_ms

        confidence_threshold = getattr(retriever, 'confidence_threshold', 0)
        result["template_search"] = {
            "candidates_found": len(templates),
            "confidence_threshold": confidence_threshold,
            "candidates": [
                _serialize_template_candidate(t, include_template=include_all_candidates)
                for t in templates[:max_templates]
            ],
        }
    except Exception as e:
        logger.error(f"Template search failed: {e}\n{traceback.format_exc()}")
        result["template_search"] = {"error": str(e), "candidates_found": 0, "candidates": []}
        result["timing"]["total_ms"] = round((time.monotonic() - total_start) * 1000, 1)
        return result

    if not templates:
        result["timing"]["total_ms"] = round((time.monotonic() - total_start) * 1000, 1)
        return result

    # --- Step 2: Reranking ---
    pre_rerank_order = [t['template'].get('id') for t in templates]
    try:
        reranker = getattr(retriever, 'template_reranker', None)
        if reranker:
            t0 = time.monotonic()
            templates = reranker.rerank_templates(templates, query)
            rerank_ms = round((time.monotonic() - t0) * 1000, 1)
            result["timing"]["reranking_ms"] = rerank_ms

            post_rerank_order = [t['template'].get('id') for t in templates]
            result["reranking"] = {
                "applied": True,
                "order_changed": pre_rerank_order != post_rerank_order,
                "pre_rerank_order": pre_rerank_order,
                "post_rerank_order": post_rerank_order,
                "reranked_scores": [
                    {
                        "template_id": t['template'].get('id'),
                        "original_similarity": round(t.get('similarity', 0) - t.get('boost_applied', 0), 4),
                        "boost": round(t.get('boost_applied', 0), 4),
                        "final_similarity": round(t.get('similarity', 0), 4),
                    }
                    for t in templates
                ],
            }
        else:
            result["reranking"] = {"applied": False}
    except Exception as e:
        logger.error(f"Reranking failed: {e}\n{traceback.format_exc()}")
        result["reranking"] = {"applied": False, "error": str(e)}

    # Filter by confidence threshold
    confidence_threshold = getattr(retriever, 'confidence_threshold', 0)
    eligible = [t for t in templates if t.get('similarity', 0) >= confidence_threshold]
    if not eligible:
        result["timing"]["total_ms"] = round((time.monotonic() - total_start) * 1000, 1)
        result["selected_template"] = {
            "error": f"No templates above confidence threshold ({confidence_threshold})",
            "best_score": templates[0].get('similarity', 0) if templates else 0,
        }
        return result

    # --- Step 2.5: Try all templates (records outcomes) ---
    try:
        t0 = time.monotonic()
        templates_tried = await _try_all_templates(retriever, eligible, query, execute)
        tried_ms = round((time.monotonic() - t0) * 1000, 1)
        result["templates_tried"] = templates_tried
    except Exception as e:
        logger.error(f"Templates tried loop failed: {e}\n{traceback.format_exc()}")
        result["templates_tried"] = [{"error": str(e)}]
        templates_tried = []

    # Find the successful template (or fall back to first)
    success_entry = next((t for t in templates_tried if t.get("outcome") == "success"), None)
    if success_entry:
        success_tid = success_entry.get("template_id")
        top_info = next((t for t in eligible if t['template'].get('id') == success_tid), eligible[0])
    else:
        top_info = eligible[0]

    template = top_info['template']
    query_type = _detect_query_type(template)

    result["selected_template"] = _serialize_template_candidate(top_info, include_template=True)

    # --- Step 3: Parameter Extraction (detailed) ---
    parameters = {}
    try:
        t0 = time.monotonic()
        extractor = getattr(retriever, 'parameter_extractor', None)
        if extractor:
            parameters = await extractor.extract_parameters(query, template)
            validation_errors = extractor.validate_parameters(parameters)
            method = "domain_extractor"
        elif hasattr(retriever, '_extract_parameters'):
            parameters = await retriever._extract_parameters(query, template)
            validation_errors = []
            method = "llm_fallback"
        else:
            validation_errors = []
            method = "none"

        extract_ms = round((time.monotonic() - t0) * 1000, 1)
        result["timing"]["parameter_extraction_ms"] = extract_ms

        extraction_result: Dict[str, Any] = {
            "extracted": parameters,
            "method": method,
            "validation_errors": validation_errors if validation_errors else [],
        }

        # Add extraction trace
        trace = _collect_extraction_trace(retriever, query, template)
        if trace:
            extraction_result["trace"] = trace

        result["parameter_extraction"] = extraction_result
    except Exception as e:
        logger.error(f"Parameter extraction failed: {e}\n{traceback.format_exc()}")
        result["parameter_extraction"] = {"error": str(e), "extracted": {}, "method": "failed"}

    # --- Step 4: Query Rendering ---
    try:
        rendered = _render_query(retriever, template, parameters, query_type)
        result["rendered_query"] = rendered
    except Exception as e:
        logger.error(f"Query rendering failed: {e}\n{traceback.format_exc()}")
        result["rendered_query"] = {"type": query_type, "error": str(e)}

    # --- Step 5: Execution result from templates_tried ---
    if execute and success_entry:
        result["execution"] = {
            "success": True,
            "row_count": success_entry.get("row_count", 0),
            "results": _safe_serialize(
                success_entry.get("_raw_results")  # not stored; re-execute for display
            ) if success_entry.get("_raw_results") else None,
            "error": None,
        }
        # Re-execute for full results display if templates_tried didn't store them
        if result["execution"]["results"] is None:
            try:
                t0 = time.monotonic()
                results, error = await retriever._execute_template(template, parameters)
                exec_ms = round((time.monotonic() - t0) * 1000, 1)
                result["timing"]["query_execution_ms"] = exec_ms
                result["execution"] = {
                    "success": error is None,
                    "row_count": len(results) if results else 0,
                    "results": _safe_serialize(results),
                    "error": error,
                }
            except Exception as e:
                result["execution"] = {"success": False, "row_count": 0, "results": [], "error": str(e)}
    elif execute and not success_entry:
        # All templates failed — show the last error
        last_tried = templates_tried[-1] if templates_tried else {}
        result["execution"] = {
            "success": False,
            "row_count": 0,
            "results": [],
            "error": last_tried.get("detail", "All templates failed"),
        }

    # --- Verbose: Semantic analysis ---
    if verbose:
        result["semantic_analysis"] = _collect_semantic_analysis(query, template, retriever)

    result["timing"]["total_ms"] = round((time.monotonic() - total_start) * 1000, 1)
    return result


async def _diagnose_composite(
    retriever,
    query: str,
    max_templates: int,
    execute: bool,
    include_all_candidates: bool,
    verbose: bool,
    result: Dict[str, Any],
) -> Dict[str, Any]:
    """Diagnose a composite intent retriever."""
    total_start = time.monotonic()

    # --- Verbose: composite-level info ---
    if verbose:
        result["vector_store_info"] = await _collect_vector_store_info(retriever)

    # --- Step 1: Search all template stores ---
    try:
        t0 = time.monotonic()
        all_matches = await retriever._search_all_template_stores(query)
        search_ms = round((time.monotonic() - t0) * 1000, 1)
        result["timing"]["template_search_ms"] = search_ms

        result["template_search"] = {
            "candidates_found": len(all_matches),
            "confidence_threshold": getattr(retriever, 'confidence_threshold', 0),
            "candidates": [
                {
                    "template_id": m.template_id,
                    "source_adapter": m.source_adapter,
                    "similarity": round(m.similarity_score, 4),
                    "description": m.template_data.get('description', ''),
                }
                for m in all_matches[:max_templates]
            ],
        }
    except Exception as e:
        logger.error(f"Composite template search failed: {e}\n{traceback.format_exc()}")
        result["template_search"] = {"error": str(e), "candidates_found": 0, "candidates": []}
        result["timing"]["total_ms"] = round((time.monotonic() - total_start) * 1000, 1)
        return result

    if not all_matches:
        result["timing"]["total_ms"] = round((time.monotonic() - total_start) * 1000, 1)
        return result

    # --- Step 2: Multi-stage scoring ---
    multistage_enabled = getattr(retriever, 'multistage_enabled', False)
    if multistage_enabled:
        try:
            t0 = time.monotonic()
            all_matches = await retriever._calculate_combined_scores(query, all_matches)
            rerank_ms = round((time.monotonic() - t0) * 1000, 1)
            result["timing"]["reranking_ms"] = rerank_ms
            result["reranking"] = {
                "applied": True,
                "multistage": True,
                "reranked_scores": [
                    {
                        "template_id": m.template_id,
                        "source_adapter": m.source_adapter,
                        "embedding_score": round(m.similarity_score, 4),
                        "rerank_score": round(m.rerank_score, 4) if m.rerank_score is not None else None,
                        "string_similarity_score": round(m.string_similarity_score, 4) if m.string_similarity_score is not None else None,
                        "combined_score": round(m.combined_score, 4) if m.combined_score is not None else None,
                    }
                    for m in all_matches[:max_templates]
                ],
            }
        except Exception as e:
            logger.error(f"Multi-stage scoring failed: {e}\n{traceback.format_exc()}")
            result["reranking"] = {"applied": False, "error": str(e)}
    else:
        result["reranking"] = {"applied": False, "multistage": False}

    # --- Step 3: Select best match ---
    best_match = retriever._select_best_match(all_matches)
    if not best_match:
        result["timing"]["total_ms"] = round((time.monotonic() - total_start) * 1000, 1)
        result["selected_template"] = {
            "error": "No template met confidence threshold",
            "best_score": all_matches[0].similarity_score if all_matches else 0,
        }
        return result

    result["composite_routing"] = {
        "child_adapters_searched": list(getattr(retriever, '_child_adapters', {}).keys()),
        "selected_adapter": best_match.source_adapter,
        "selected_template_id": best_match.template_id,
        "multistage_enabled": multistage_enabled,
    }

    # --- Step 4: Delegate to child adapter for detailed diagnostics ---
    child_adapters = getattr(retriever, '_child_adapters', {})
    child = child_adapters.get(best_match.source_adapter)
    if not child:
        result["timing"]["total_ms"] = round((time.monotonic() - total_start) * 1000, 1)
        result["selected_template"] = {"error": f"Child adapter '{best_match.source_adapter}' not found"}
        return result

    child_result = await _diagnose_intent(
        child, query, max_templates, execute, include_all_candidates, verbose,
        {
            "adapter_name": best_match.source_adapter,
            "adapter_type": _get_retriever_type_name(child),
            "query": query,
            "timing": {},
            "vector_store_info": None,
            "template_inventory": None,
            "domain_info": None,
            "template_search": None,
            "reranking": None,
            "selected_template": None,
            "parameter_extraction": None,
            "rendered_query": None,
            "execution": None,
            "templates_tried": None,
            "semantic_analysis": None,
            "composite_routing": None,
        }
    )

    # Merge child results into composite result
    result["selected_template"] = child_result.get("selected_template")
    result["parameter_extraction"] = child_result.get("parameter_extraction")
    result["rendered_query"] = child_result.get("rendered_query")
    result["execution"] = child_result.get("execution")
    result["templates_tried"] = child_result.get("templates_tried")
    if verbose:
        result["template_inventory"] = child_result.get("template_inventory")
        result["domain_info"] = child_result.get("domain_info")
        result["semantic_analysis"] = child_result.get("semantic_analysis")

    # Merge child timing
    for key, val in child_result.get("timing", {}).items():
        if key != "total_ms" and key not in result["timing"]:
            result["timing"][key] = val

    result["timing"]["total_ms"] = round((time.monotonic() - total_start) * 1000, 1)
    return result


def _render_query(retriever, template: Dict[str, Any], parameters: Dict[str, Any], query_type: str) -> Dict[str, Any]:
    """Render the query from a template and parameters."""
    rendered: Dict[str, Any] = {"type": query_type}

    if query_type == "sql":
        sql_template = template.get('sql_template', template.get('sql', ''))
        if hasattr(retriever, '_process_sql_template') and sql_template:
            rendered["query"] = retriever._process_sql_template(sql_template, parameters)
        else:
            rendered["query"] = sql_template
        rendered["parameters"] = parameters

    elif query_type == "graphql":
        rendered["query"] = template.get('graphql_template', '')
        rendered["variables"] = parameters

    elif query_type == "mongodb":
        rendered["query"] = template.get('mongodb_query', '')
        rendered["parameters"] = parameters

    elif query_type == "http":
        endpoint = template.get('endpoint_template', '')
        base_url = getattr(retriever, 'base_url', '')
        rendered["endpoint"] = endpoint
        rendered["base_url"] = base_url
        rendered["method"] = template.get('method', 'GET')
        rendered["parameters"] = parameters

    elif query_type == "elasticsearch":
        rendered["query"] = template.get('query_template', '')
        rendered["parameters"] = parameters

    elif query_type == "agent":
        rendered["function_schema"] = template.get('function_schema', {})
        rendered["parameters"] = parameters

    else:
        rendered["raw_template"] = _extract_query_template(template)
        rendered["parameters"] = parameters

    return rendered


def _safe_serialize(obj: Any, max_results: int = 100) -> Any:
    """Safely serialize query results, truncating if needed."""
    if obj is None:
        return []
    if isinstance(obj, list):
        truncated = obj[:max_results]
        items = []
        for item in truncated:
            if isinstance(item, dict):
                items.append({k: _coerce_value(v) for k, v in item.items()})
            else:
                items.append(_coerce_value(item))
        return items
    return _coerce_value(obj)


def _coerce_value(v: Any) -> Any:
    """Coerce a value into a JSON-serializable type."""
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, (list, tuple)):
        return [_coerce_value(i) for i in v]
    if isinstance(v, dict):
        return {k: _coerce_value(val) for k, val in v.items()}
    # datetime, Decimal, bytes, etc.
    return str(v)
