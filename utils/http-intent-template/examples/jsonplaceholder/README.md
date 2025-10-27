# JSONPlaceholder API - HTTP Adapter Example

A simple, clean example using JSONPlaceholder fake REST API to test the HTTP adapter functionality.

## Why JSONPlaceholder?

JSONPlaceholder is **intentionally simpler** than GitHub to isolate issues:

| Feature | GitHub API | JSONPlaceholder |
|---------|-----------|-----------------|
| **Authentication** | Required (Bearer token) | ❌ None |
| **Rate Limits** | 5000/hour | ❌ None |
| **ID Format** | Strings/UUIDs | ✅ Simple integers (1, 2, 3...) |
| **Response Structure** | Complex nested | ✅ Simple flat JSON |
| **Setup Time** | 5-10 minutes | ✅ 30 seconds |
| **Stability** | Can change | ✅ Stable, designed for testing |

**Perfect for debugging the parameter extraction issue!**

## Files in This Directory

```
examples/jsonplaceholder/
├── README.md                          # This file
├── ADAPTER_CONFIG.md                  # How to configure the adapter
├── test_queries.md                    # Test queries and expected results
└── templates/
    ├── jsonplaceholder_domain.yaml    # API domain configuration
    └── jsonplaceholder_templates.yaml # 8 HTTP request templates
```

## Quick Start

### 1. Add Adapter Configuration

Copy the configuration from `ADAPTER_CONFIG.md` to `config/adapters.yaml`:

```yaml
  - name: "intent-http-jsonplaceholder"
    enabled: true
    type: "retriever"
    datasource: "http"
    adapter: "intent"
    implementation: "retrievers.implementations.intent.IntentHTTPJSONRetriever"
    inference_provider: "ollama_cloud"
    model: "gpt-oss:120b-cloud"
    embedding_provider: "openai"
    config:
      domain_config_path: "utils/http-intent-template/examples/jsonplaceholder/templates/jsonplaceholder_domain.yaml"
      template_library_path:
        - "utils/http-intent-template/examples/jsonplaceholder/templates/jsonplaceholder_templates.yaml"
      template_collection_name: "jsonplaceholder_http_templates"
      store_name: "chroma"
      confidence_threshold: 0.4
      base_url: "https://jsonplaceholder.typicode.com"
      verbose: true
```

### 2. Restart Server

```bash
python server/inference_server.py
```

### 3. Test Simple Query

Send this query:
```
"Show me post 1"
```

**Expected Result**:
```json
{
  "userId": 1,
  "id": 1,
  "title": "sunt aut facere repellat provident...",
  "body": "quia et suscipit..."
}
```

### 4. Check Logs

Look for:
```
✅ INFO - Executing REST GET request to: /posts/1
✅ INFO - Successfully retrieved 1 results
```

**NOT**:
```
❌ ERROR - REST GET request to: /posts/{post_id}
                                        ^^^^^^^^^^^
                                        PLACEHOLDER NOT REPLACED!
```

## Available Templates

The adapter includes **8 templates** covering common scenarios:

### Posts (3 templates)
- `get_post_by_id` - Get a specific post → `/posts/{post_id}`
- `list_posts_by_user` - Posts by user → `/posts?userId={user_id}`
- `list_all_posts` - All posts → `/posts`

### Users (2 templates)
- `get_user_by_id` - Get a specific user → `/users/{user_id}`
- `list_all_users` - All users → `/users`

### Comments (1 template)
- `get_comments_for_post` - Comments on a post → `/comments?postId={post_id}`

### Todos (1 template)
- `get_todos_by_user` - User's todos → `/todos?userId={user_id}`

### Template Distribution

| Template Type | Count | Purpose |
|--------------|-------|---------|
| **Path parameters** | 2 | Test parameter extraction |
| **Query parameters** | 3 | Test query building |
| **No parameters** | 2 | Test simple endpoints |
| **Mixed** | 1 | Test combined logic |

## Test Scenarios

See `test_queries.md` for comprehensive test cases:

### Phase 1: Path Parameters
```
✅ "Show me post 1"    → /posts/1
✅ "Get user 5"        → /users/5
✅ "Retrieve post 42"  → /posts/42
```

### Phase 2: Query Parameters
```
✅ "Show me posts by user 1"  → /posts?userId=1
✅ "Get comments for post 5"  → /comments?postId=5
✅ "Show todos for user 3"    → /todos?userId=3
```

### Phase 3: No Parameters
```
✅ "List all posts"     → /posts
✅ "Show me all users"  → /users
```

## Success Criteria

The adapter is working correctly if:

1. ✅ **Adapter loads successfully** (8 templates)
2. ✅ **Path parameters are extracted** (post_id → 1)
3. ✅ **URLs are built correctly** (/posts/1, not /posts/{post_id})
4. ✅ **No 404 errors** on valid queries
5. ✅ **Responses are parsed** and returned to user

## Debugging Parameter Extraction

If you see this pattern:
```
INFO - Trying template: get_post_by_id
ERROR - REST GET request to: /posts/{post_id}  ← NOT REPLACED!
ERROR - HTTP 404: {"error": "Not Found"}
```

**The parameter extraction is not working.** Check:

1. **Is `_extract_parameters()` being called?**
   - Look for `🔍 _extract_parameters CALLED` logs
   - If missing, the method is being skipped

2. **Is the inference client available?**
   - Check `inference_provider` configuration
   - Verify model is loaded

3. **Are parameters defined in the template?**
   - Check `jsonplaceholder_templates.yaml`
   - Verify `parameters:` section exists

## Advantages Over GitHub

### Simpler Parameter Extraction

**GitHub**:
```yaml
parameters:
  - name: username
    type: string
    description: "GitHub username"
    example: "octocat"
```
Query: "Find projects by user schmitech"
Extraction difficulty: **Medium** (username embedded in sentence)

**JSONPlaceholder**:
```yaml
parameters:
  - name: post_id
    type: integer
    description: "The ID of the post"
    example: 1
```
Query: "Show me post 1"
Extraction difficulty: **Easy** (numeric ID at end of sentence)

### No Authentication

**GitHub**: Requires valid token, expires, rate limited
**JSONPlaceholder**: ✅ No setup, no limits, no failures

### Predictable Responses

**GitHub**: Dynamic data, can change
**JSONPlaceholder**: ✅ Static fake data, always consistent

### Easier Debugging

**GitHub**: 7 templates, complex relationships, nested data
**JSONPlaceholder**: ✅ 8 simple templates, flat data structure

## API Documentation

Official JSONPlaceholder docs: https://jsonplaceholder.typicode.com/

### Available Endpoints
- `/posts` - 100 posts
- `/users` - 10 users
- `/comments` - 500 comments
- `/todos` - 200 todos

### Example Requests
```bash
# Get post 1
curl https://jsonplaceholder.typicode.com/posts/1

# Get posts by user 1
curl "https://jsonplaceholder.typicode.com/posts?userId=1"

# Get all users
curl https://jsonplaceholder.typicode.com/users

# Get comments for post 1
curl "https://jsonplaceholder.typicode.com/comments?postId=1"
```

All endpoints return valid JSON with no authentication required.

## Next Steps

1. ✅ **Add adapter config** to `config/adapters.yaml`
2. ✅ **Restart server** and verify adapter loads
3. ✅ **Test simple query**: "Show me post 1"
4. ✅ **Check parameter extraction** in logs
5. ✅ **Compare behavior** with GitHub adapter
6. ✅ **Identify root cause** of parameter extraction issue

## Support

For issues or questions about this example:
- Check `ADAPTER_CONFIG.md` for configuration help
- Check `test_queries.md` for testing guidance
- Check main HTTP adapter documentation
- Refer to `PARAMETER_EXTRACTION_ISSUE.md` for known issues

---

**Created**: 2025-10-24
**Purpose**: Simple, clean API for testing HTTP adapter
**Status**: Ready for testing
**Complexity**: Low (intentionally simple)
