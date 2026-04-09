#!/usr/bin/env python3
"""
CLI tool for testing intent retriever templates without the full LLM pipeline.

Calls the POST /admin/adapters/{adapter_name}/test-query endpoint on a running
ORBIT server and pretty-prints the diagnostic results.

Usage:
    python server/tools/test_template_query.py \\
        --query "what are the salary statistics?" \\
        --adapter intent-sql-sqlite-hr \\
        --server-url http://localhost:3000 \\
        --api-key <admin-api-key-or-bearer-token>

    # Pick a random nl_example from a template ID (no need to type a query)
    python server/tools/test_template_query.py \\
        --template-id search_employees_by_name \\
        --templates-file examples/intent-templates/sql-intent-template/examples/sqlite/hr/hr-templates.yaml \\
        --adapter intent-sql-sqlite-hr \\
        --server-url http://localhost:3000 --api-key <token>

    # Verbose mode (vector store info, template inventory, domain config, semantic analysis)
    python server/tools/test_template_query.py \\
        --query "salary stats" --adapter intent-sql-sqlite-hr \\
        --server-url http://localhost:3000 --api-key <token> --verbose

    # Skip query execution (template matching only)
    python server/tools/test_template_query.py \\
        --query "salary stats" --adapter intent-sql-sqlite-hr \\
        --server-url http://localhost:3000 --api-key <token> --no-execute

    # Raw JSON output
    python server/tools/test_template_query.py \\
        --query "salary stats" --adapter intent-sql-sqlite-hr \\
        --server-url http://localhost:3000 --api-key <token> --output json
"""

import argparse
import json
import random
import sys

try:
    import httpx
except ImportError:
    print("Error: httpx is required. Install with: pip install httpx", file=sys.stderr)
    sys.exit(1)

try:
    import yaml
except ImportError:
    yaml = None


# ANSI color codes
class C:
    BOLD = "\033[1m"
    DIM = "\033[2m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    CYAN = "\033[36m"
    MAGENTA = "\033[35m"
    BLUE = "\033[34m"
    RESET = "\033[0m"


def _no_color():
    """Disable colors."""
    for attr in ('BOLD', 'DIM', 'GREEN', 'YELLOW', 'RED', 'CYAN', 'MAGENTA', 'BLUE', 'RESET'):
        setattr(C, attr, '')


def _sim_color(sim: float) -> str:
    if sim >= 0.7:
        return C.GREEN
    if sim >= 0.4:
        return C.YELLOW
    return C.RED


def print_pretty(data: dict) -> None:
    """Pretty-print the diagnostic results."""
    print()
    print(f"{C.BOLD}{'=' * 70}{C.RESET}")
    print(f"{C.BOLD}  Template Query Diagnostics{C.RESET}")
    print(f"{C.BOLD}{'=' * 70}{C.RESET}")

    # Header
    print(f"\n  {C.DIM}Adapter:{C.RESET}  {data.get('adapter_name', '?')}")
    print(f"  {C.DIM}Type:{C.RESET}     {data.get('adapter_type', '?')}")
    print(f"  {C.DIM}Query:{C.RESET}    {data.get('query', '?')}")

    # Timing
    timing = data.get("timing", {})
    if timing:
        print(f"\n{C.BOLD}  Timing{C.RESET}")
        for key, val in timing.items():
            label = key.replace("_ms", "").replace("_", " ").title()
            print(f"    {label}: {val}ms")

    # Vector store info (verbose)
    vs_info = data.get("vector_store_info")
    if vs_info and not vs_info.get("error"):
        print(f"\n{C.BOLD}  Vector Store{C.RESET}")
        print(f"    Store type:    {vs_info.get('store_type', '?')}")
        print(f"    Collection:    {vs_info.get('collection_name', '?')}")
        print(f"    Total vectors: {vs_info.get('total_vectors', '?')}")
        print(f"    Cached:        {vs_info.get('cached_templates', '?')}")
        emb_dim = vs_info.get('embedding_dimension')
        query_dim = vs_info.get('query_embedding_dimension')
        dim_match = vs_info.get('dimension_match')
        if emb_dim:
            dim_str = f"{emb_dim}"
            if query_dim and query_dim != emb_dim:
                dim_str += f" {C.RED}(query: {query_dim} - MISMATCH){C.RESET}"
            elif dim_match is True:
                dim_str += f" {C.GREEN}(match){C.RESET}"
            print(f"    Dimensions:    {dim_str}")
        print(f"    Provider:      {vs_info.get('embedding_provider', '?')}")
        print(f"    Model:         {vs_info.get('embedding_model', '?')}")
    elif vs_info and vs_info.get("error"):
        print(f"\n{C.BOLD}  Vector Store{C.RESET}")
        print(f"    {C.RED}Error: {vs_info['error']}{C.RESET}")

    # Template inventory (verbose)
    inventory = data.get("template_inventory")
    if inventory and not inventory.get("error"):
        total = inventory.get("total_templates", 0)
        print(f"\n{C.BOLD}  Template Inventory{C.RESET}  ({total} templates loaded)")
        for t in inventory.get("templates", []):
            tags_marker = f" {C.BLUE}[tags]{C.RESET}" if t.get("has_semantic_tags") else ""
            print(f"    {t.get('id', '?'):40s}  {C.DIM}ex:{t.get('nl_examples_count', 0)} params:{t.get('parameters_count', 0)} type:{t.get('query_type', '?')}{C.RESET}{tags_marker}")

    # Domain info (verbose)
    domain = data.get("domain_info")
    if domain and not domain.get("error"):
        print(f"\n{C.BOLD}  Domain Config{C.RESET}  ({domain.get('domain_name', '?')})")
        print(f"    Entities:    {', '.join(domain.get('entities', []))}")
        for ent, syns in domain.get("entity_synonyms", {}).items():
            print(f"    {C.DIM}  {ent} synonyms:{C.RESET} {', '.join(syns)}")
        field_syns = domain.get("field_synonyms", {})
        if field_syns:
            print(f"    Field synonyms:")
            for fname, syns in field_syns.items():
                print(f"      {fname}: {', '.join(syns)}")
        searchable = domain.get("searchable_fields", [])
        filterable = domain.get("filterable_fields", [])
        if searchable:
            print(f"    Searchable:  {', '.join(searchable)}")
        if filterable:
            print(f"    Filterable:  {', '.join(filterable)}")

    # Composite routing
    routing = data.get("composite_routing")
    if routing:
        print(f"\n{C.BOLD}  Composite Routing{C.RESET}")
        if routing.get('cross_adapter'):
            print(f"    {C.MAGENTA}Cross-adapter query{C.RESET}")
            print(f"    Template:  {routing.get('template_id', '?')}")
            print(f"    Strategy:  {routing.get('merge_strategy', '?')}")
            print(f"    Targets:   {', '.join(routing.get('target_adapters', []))}")
            successful = routing.get('successful_adapters', [])
            failed = routing.get('failed_adapters', [])
            if successful:
                print(f"    {C.GREEN}Successful:{C.RESET} {', '.join(successful)}")
            if failed:
                for fa in failed:
                    print(f"    {C.RED}Failed:{C.RESET} {fa.get('adapter', '?')} - {fa.get('error', '?')}")
            score = routing.get('combined_score') or routing.get('similarity_score')
            if score:
                print(f"    Score:     {score:.4f}")
        else:
            print(f"    Searched: {', '.join(routing.get('child_adapters_searched', []))}")
            print(f"    {C.GREEN}Selected adapter:{C.RESET} {routing.get('selected_adapter', '?')}")
            print(f"    Multistage: {routing.get('multistage_enabled', False)}")

    # Template search
    search = data.get("template_search")
    if search:
        print(f"\n{C.BOLD}  Template Search{C.RESET}  ({search.get('candidates_found', 0)} candidates, threshold={search.get('confidence_threshold', '?')})")
        if search.get("error"):
            print(f"    {C.RED}Error: {search['error']}{C.RESET}")
        for i, cand in enumerate(search.get("candidates", [])):
            marker = f"{C.GREEN}>>>{C.RESET} " if i == 0 else "    "
            sim = cand.get("similarity", 0)
            color = _sim_color(sim)
            rescued = f" {C.MAGENTA}[rescued]{C.RESET}" if cand.get("rescued_by_nl_example") else ""
            source = f" {C.DIM}from {cand['source_adapter']}{C.RESET}" if "source_adapter" in cand else ""
            print(f"  {marker}{color}{sim:.4f}{C.RESET}  {cand.get('template_id', '?')}{rescued}{source}")
            if cand.get("description"):
                print(f"           {C.DIM}{cand['description']}{C.RESET}")

    # Reranking
    reranking = data.get("reranking")
    if reranking and reranking.get("applied"):
        print(f"\n{C.BOLD}  Reranking{C.RESET}")
        if reranking.get("error"):
            print(f"    {C.RED}Error: {reranking['error']}{C.RESET}")
        elif reranking.get("multistage"):
            for entry in reranking.get("reranked_scores", [])[:5]:
                combined = entry.get("combined_score")
                emb = entry.get("embedding_score")
                print(f"    {entry.get('template_id', '?')}: combined={combined}, emb={emb}")
        else:
            changed = reranking.get("order_changed", False)
            print(f"    Order changed: {changed}")
            for entry in reranking.get("reranked_scores", [])[:5]:
                orig = entry.get("original_similarity", 0)
                boost = entry.get("boost", 0)
                final = entry.get("final_similarity", 0)
                boost_str = f" {C.GREEN}+{boost:.3f}{C.RESET}" if boost > 0 else ""
                print(f"    {entry.get('template_id', '?'):40s}  {orig:.4f}{boost_str} -> {final:.4f}")

    # Selected template
    selected = data.get("selected_template")
    if selected:
        print(f"\n{C.BOLD}  Selected Template{C.RESET}")
        if selected.get("error"):
            print(f"    {C.RED}{selected['error']}{C.RESET}")
            if "best_score" in selected:
                print(f"    Best score was: {selected['best_score']}")
        else:
            print(f"    ID:          {selected.get('template_id', '?')}")
            print(f"    Similarity:  {selected.get('similarity', 0):.4f}")
            print(f"    Description: {selected.get('description', '')}")
            if selected.get("query_type"):
                print(f"    Query type:  {selected['query_type']}")
            params = selected.get("parameters_defined", [])
            if params:
                print(f"    Parameters:  {', '.join(p.get('name', '?') for p in params)}")

    # Parameter extraction
    extraction = data.get("parameter_extraction")
    if extraction:
        print(f"\n{C.BOLD}  Parameter Extraction{C.RESET}  (method: {extraction.get('method', '?')})")
        if extraction.get("error"):
            print(f"    {C.RED}Error: {extraction['error']}{C.RESET}")
        extracted = extraction.get("extracted", {})
        if extracted:
            for k, v in extracted.items():
                print(f"    {k}: {v}")
        else:
            print(f"    {C.DIM}(no parameters extracted){C.RESET}")
        errors = extraction.get("validation_errors", [])
        if errors:
            for err in errors:
                print(f"    {C.RED}Validation: {err}{C.RESET}")

        # Extraction trace
        trace = extraction.get("trace")
        if trace:
            print(f"    {C.DIM}--- Extraction Trace ---{C.RESET}")
            print(f"    Patterns available: {trace.get('patterns_available', 0)}")

            # First-pass bulk pattern scan results
            first_pass = trace.get("first_pass_matches", {})
            if first_pass:
                print(f"    {C.GREEN}First-pass pattern matches:{C.RESET}")
                for k, v in first_pass.items():
                    print(f"      {k}: {v}")
            else:
                print(f"    {C.DIM}First-pass: no pattern matches{C.RESET}")
            if trace.get("first_pass_error"):
                print(f"    {C.RED}First-pass error: {trace['first_pass_error']}{C.RESET}")

            # Per-parameter resolution trace
            per_param = trace.get("per_parameter", [])
            if per_param:
                print(f"    {C.BOLD}Per-parameter resolution:{C.RESET}")
                for pt in per_param:
                    name = pt.get("name", "?")
                    ptype = pt.get("type", "?")
                    required = pt.get("required", False)
                    resolution = pt.get("resolution", "?")
                    value = pt.get("value")

                    req_marker = f" {C.RED}*required{C.RESET}" if required else ""

                    # Color the resolution status
                    res_colors = {
                        "entity_field_pattern": C.GREEN,
                        "param_name_pattern": C.GREEN,
                        "context_extraction": C.CYAN,
                        "template_parameter": C.CYAN,
                        "default": C.YELLOW,
                        "not_found": C.RED,
                        "validation_failed": C.RED,
                        "coercion_failed": C.RED,
                    }
                    rc = res_colors.get(resolution, C.DIM)
                    res_str = f"{rc}{resolution}{C.RESET}"

                    val_str = ""
                    if value is not None:
                        val_str = f" = {C.GREEN}{value}{C.RESET}"
                    elif pt.get("raw_value") is not None:
                        val_str = f" raw={pt['raw_value']}"

                    print(f"      {name} ({ptype}){req_marker}: {res_str}{val_str}")

                    # Show pattern info if entity.field based
                    pkey = pt.get("pattern_key")
                    if pkey and pt.get("pattern_exists") is False:
                        print(f"        {C.RED}No regex pattern for '{pkey}'{C.RESET}")
                    elif pkey and pt.get("pattern_regex"):
                        print(f"        {C.DIM}regex: {pt['pattern_regex']}{C.RESET}")

                    # Show validation/coercion errors
                    if pt.get("validation_error"):
                        print(f"        {C.RED}Validation: {pt['validation_error']}{C.RESET}")
                    if pt.get("coercion_error"):
                        print(f"        {C.RED}Coercion: {pt['coercion_error']}{C.RESET}")
                    if pt.get("llm_fallback_needed"):
                        print(f"        {C.YELLOW}-> LLM fallback would be triggered{C.RESET}")

            # LLM fallback summary
            llm_params = trace.get("llm_fallback_params", [])
            if llm_params:
                print(f"    {C.YELLOW}LLM fallback needed for: {', '.join(llm_params)}{C.RESET}")

    # Rendered query
    rendered = data.get("rendered_query")
    if rendered:
        print(f"\n{C.BOLD}  Rendered Query{C.RESET}  (type: {rendered.get('type', '?')})")
        if rendered.get("error"):
            print(f"    {C.RED}Error: {rendered['error']}{C.RESET}")
        query_text = rendered.get("query") or rendered.get("endpoint") or rendered.get("raw_template")
        if query_text:
            for line in str(query_text).strip().split('\n'):
                print(f"    {C.CYAN}{line}{C.RESET}")
        params = rendered.get("parameters") or rendered.get("variables")
        if params:
            print(f"    {C.DIM}Parameters: {json.dumps(params, default=str)}{C.RESET}")

    # Templates tried
    tried = data.get("templates_tried")
    if tried and len(tried) > 1:
        print(f"\n{C.BOLD}  Templates Tried{C.RESET}  ({len(tried)} attempted)")
        for entry in tried:
            outcome = entry.get("outcome", "?")
            tid = entry.get("template_id", "?")
            sim = entry.get("similarity", 0)
            if outcome == "success":
                rows = entry.get("row_count", 0)
                print(f"    {C.GREEN}OK{C.RESET}  {tid} ({sim:.4f}) -> {rows} rows")
            elif outcome == "not_executed":
                print(f"    {C.DIM}--{C.RESET}  {tid} ({sim:.4f}) -> not executed")
            else:
                detail = entry.get("detail", "")
                print(f"    {C.RED}FAIL{C.RESET} {tid} ({sim:.4f}) -> {outcome}: {detail}")

    # Execution results
    execution = data.get("execution")
    if execution:
        print(f"\n{C.BOLD}  Execution{C.RESET}")
        if execution.get("error"):
            print(f"    {C.RED}Error: {execution['error']}{C.RESET}")
        success = execution.get("success", False)
        color = C.GREEN if success else C.RED
        print(f"    Success:   {color}{success}{C.RESET}")
        print(f"    Row count: {execution.get('row_count', 0)}")
        results = execution.get("results", [])
        if results:
            max_show = min(10, len(results))
            for i, row in enumerate(results[:max_show]):
                print(f"    {C.DIM}[{i+1}]{C.RESET} {json.dumps(row, default=str)}")
            if len(results) > max_show:
                print(f"    {C.DIM}... and {len(results) - max_show} more rows{C.RESET}")
    elif data.get("execution") is None and not any(
        data.get(k, {}).get("error") for k in ("template_search", "selected_template") if data.get(k)
    ):
        print(f"\n  {C.DIM}(execution skipped){C.RESET}")

    # Semantic analysis (verbose)
    semantic = data.get("semantic_analysis")
    if semantic and semantic.get("template_has_semantic_tags"):
        print(f"\n{C.BOLD}  Semantic Analysis{C.RESET}")
        entity = semantic.get("primary_entity", "")
        action = semantic.get("action", "")
        entity_match = semantic.get("entity_match", False)
        action_match = semantic.get("action_match", False)
        e_color = C.GREEN if entity_match else C.RED
        a_color = C.GREEN if action_match else C.RED
        print(f"    Primary entity: {entity}  {e_color}{'MATCH' if entity_match else 'NO MATCH'}{C.RESET}")
        print(f"    Action:         {action}  {a_color}{'MATCH' if action_match else 'NO MATCH'}{C.RESET}")
        qualifiers = semantic.get("qualifiers", [])
        matched_q = semantic.get("matched_qualifiers", [])
        if qualifiers:
            for q in qualifiers:
                qm = C.GREEN + "MATCH" + C.RESET if q in matched_q else C.DIM + "no match" + C.RESET
                print(f"    Qualifier: {q}  {qm}")
        print(f"    {C.DIM}Query words: {' '.join(semantic.get('query_words', []))}{C.RESET}")

    print(f"\n{C.BOLD}{'=' * 70}{C.RESET}\n")


def _pick_random_example(templates_file: str, template_id: str) -> str:
    """Load a templates YAML file and pick a random nl_example from the given template ID."""
    if yaml is None:
        print("Error: PyYAML is required for --template-id. Install with: pip install pyyaml",
              file=sys.stderr)
        sys.exit(1)

    try:
        with open(templates_file, 'r') as f:
            data = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"Error: Templates file not found: {templates_file}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error loading templates file: {e}", file=sys.stderr)
        sys.exit(1)

    # Templates can be a list or nested under a 'templates' key
    templates = data if isinstance(data, list) else data.get('templates', [])
    if not templates:
        print(f"Error: No templates found in {templates_file}", file=sys.stderr)
        sys.exit(1)

    # Find the template by ID
    match = None
    available_ids = []
    for tmpl in templates:
        tid = tmpl.get('id', '')
        available_ids.append(tid)
        if tid == template_id:
            match = tmpl
            break

    if not match:
        print(f"Error: Template '{template_id}' not found in {templates_file}", file=sys.stderr)
        print(f"Available IDs: {', '.join(available_ids)}", file=sys.stderr)
        sys.exit(1)

    examples = match.get('nl_examples', [])
    if not examples:
        print(f"Error: Template '{template_id}' has no nl_examples", file=sys.stderr)
        sys.exit(1)

    chosen = random.choice(examples)
    return chosen


def main():
    parser = argparse.ArgumentParser(
        description="Test intent retriever templates without the full LLM pipeline.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Explicit query
  %(prog)s --query "salary stats" --adapter intent-sql-sqlite-hr --api-key <token>

  # Random nl_example from a template
  %(prog)s --template-id search_employees_by_name \\
    --templates-file examples/intent-templates/sql-intent-template/examples/sqlite/hr/hr-templates.yaml \\
    --adapter intent-sql-sqlite-hr --api-key <token>

  %(prog)s -q "top movies" -a intent-mongodb-mflix -k <token> --no-execute
  %(prog)s -q "events in Paris" -a composite-full-explorer -k <token> --verbose
  %(prog)s -q "salary stats" -a intent-sql-sqlite-hr -k <token> --output json
        """,
    )
    parser.add_argument("--query", "-q", default=None,
                        help="Natural language query to test (or use --template-id to pick one automatically)")
    parser.add_argument("--template-id", default=None,
                        help="Pick a random nl_example from this template ID (requires --templates-file)")
    parser.add_argument("--templates-file", default=None,
                        help="Path to the templates YAML file (used with --template-id)")
    parser.add_argument("--adapter", "-a", required=True, help="Adapter name to test against")
    parser.add_argument("--server-url", "-s", default="http://localhost:3000",
                        help="ORBIT server URL (default: http://localhost:3000)")
    parser.add_argument("--api-key", "-k", required=True,
                        help="Admin API key or bearer token for authentication")
    parser.add_argument("--no-execute", action="store_true",
                        help="Skip query execution (template matching and extraction only)")
    parser.add_argument("--all-candidates", action="store_true",
                        help="Include full details for all template candidates")
    parser.add_argument("--max-templates", type=int, default=5,
                        help="Maximum template candidates to return (default: 5)")
    parser.add_argument("--verbose", "-V", action="store_true",
                        help="Show extended diagnostics: vector store health, template inventory, "
                             "domain config, semantic tag analysis")
    parser.add_argument("--output", choices=["pretty", "json"], default="pretty",
                        help="Output format (default: pretty)")
    parser.add_argument("--no-color", action="store_true", help="Disable colored output")
    parser.add_argument("--timeout", type=int, default=30, help="Request timeout in seconds (default: 30)")

    args = parser.parse_args()

    # Resolve query: explicit --query or random pick from --template-id
    if args.template_id:
        if not args.templates_file:
            parser.error("--templates-file is required when using --template-id")
        query = _pick_random_example(args.templates_file, args.template_id)
        if not args.no_color and sys.stdout.isatty():
            print(f"\033[2mPicked random example from '{args.template_id}': \033[0m{query}",
                  file=sys.stderr)
    elif args.query:
        query = args.query
    else:
        parser.error("either --query or --template-id (with --templates-file) is required")

    if args.no_color or not sys.stdout.isatty():
        _no_color()

    url = f"{args.server_url.rstrip('/')}/admin/adapters/{args.adapter}/test-query"
    headers = {}

    # Support both bearer token and API key auth
    if args.api_key.startswith("Bearer "):
        headers["Authorization"] = args.api_key
    else:
        headers["Authorization"] = f"Bearer {args.api_key}"
        headers["X-API-Key"] = args.api_key

    payload = {
        "query": query,
        "max_templates": args.max_templates,
        "execute": not args.no_execute,
        "include_all_candidates": args.all_candidates,
        "verbose": args.verbose,
    }

    try:
        with httpx.Client(timeout=args.timeout) as client:
            resp = client.post(url, json=payload, headers=headers)
    except httpx.ConnectError:
        print(f"{C.RED}Error: Could not connect to {args.server_url}{C.RESET}", file=sys.stderr)
        print(f"Make sure the ORBIT server is running.", file=sys.stderr)
        sys.exit(1)
    except httpx.TimeoutException:
        print(f"{C.RED}Error: Request timed out after {args.timeout}s{C.RESET}", file=sys.stderr)
        sys.exit(1)

    if resp.status_code != 200:
        print(f"{C.RED}Error {resp.status_code}: {resp.text}{C.RESET}", file=sys.stderr)
        sys.exit(1)

    data = resp.json()

    if args.output == "json":
        print(json.dumps(data, indent=2, default=str))
    else:
        print_pretty(data)


if __name__ == "__main__":
    main()
