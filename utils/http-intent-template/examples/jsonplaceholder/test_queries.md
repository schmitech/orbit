# JSONPlaceholder API - Test Queries

These queries are designed to test the HTTP adapter with a simple, reliable API.

## Test Categories

### 1. Path Parameter Tests (Testing Parameter Extraction)

These test if `{post_id}` and `{user_id}` are correctly extracted and replaced:

```
✅ "Show me post 1"
   Expected: GET /posts/1
   Tests: Path parameter extraction (post_id)

✅ "Get user 5"
   Expected: GET /users/5
   Tests: Path parameter extraction (user_id)

✅ "Retrieve post 42"
   Expected: GET /posts/42
   Tests: Numeric parameter extraction
```

### 2. Query Parameter Tests

These test if query parameters are correctly built:

```
✅ "Show me posts by user 1"
   Expected: GET /posts?userId=1
   Tests: Query parameter (userId)

✅ "Get comments for post 5"
   Expected: GET /comments?postId=5
   Tests: Query parameter (postId)

✅ "Show todos for user 3"
   Expected: GET /todos?userId=3
   Tests: Query parameter (userId)
```

### 3. No Parameter Tests

These test templates with no parameters:

```
✅ "List all posts"
   Expected: GET /posts
   Tests: No parameters required

✅ "Show me all users"
   Expected: GET /users
   Tests: No parameters required
```

### 4. Complex Parameter Tests

These test multiple parameters or complex extraction:

```
✅ "Show me posts by user 2 limit 5"
   Expected: GET /posts?userId=2&_limit=5
   Tests: Multiple query parameters

✅ "Get comments for post 10 limit 20"
   Expected: GET /comments?postId=10&_limit=20
   Tests: Multiple query parameters
```

## Test Sequence

### Phase 1: Basic Path Parameters
Start with the simplest tests:

1. "Show me post 1" → Should return single post
2. "Get user 5" → Should return single user
3. "Get post 10" → Should return single post

**Expected Result**:
- ✅ Parameter extracted correctly
- ✅ URL built: `/posts/1`, `/users/5`, `/posts/10`
- ✅ Valid JSON response
- ❌ **NO 404 errors**

### Phase 2: Query Parameters
Test filtering:

1. "Show me posts by user 1" → Should return array of posts
2. "Get comments for post 5" → Should return array of comments
3. "Show todos for user 2" → Should return array of todos

**Expected Result**:
- ✅ Query parameters extracted
- ✅ URL built: `/posts?userId=1`, etc.
- ✅ Valid JSON array response

### Phase 3: No Parameters
Test simple endpoints:

1. "List all posts" → Should return array of posts
2. "Show me all users" → Should return array of users

**Expected Result**:
- ✅ No parameters needed
- ✅ URL built: `/posts`, `/users`
- ✅ Valid JSON array response

## What to Look For

### Success Indicators
```
✅ INFO - Executing REST GET request to: /posts/1
✅ INFO - Successfully parsed response
✅ No 404 errors
✅ Results returned to user
```

### Failure Indicators (Parameter Extraction Issue)
```
❌ INFO - Executing REST GET request to: /posts/{post_id}
                                               ^^^^^^^^^^^
                                               NOT REPLACED!
❌ ERROR - REST API request failed: HTTP 404
```

## Manual API Tests

You can test these endpoints directly with curl to verify they work:

```bash
# Test path parameter endpoint
curl https://jsonplaceholder.typicode.com/posts/1

# Test query parameter endpoint
curl "https://jsonplaceholder.typicode.com/posts?userId=1"

# Test simple endpoint
curl https://jsonplaceholder.typicode.com/users
```

## Expected Responses

### Single Post (GET /posts/1)
```json
{
  "userId": 1,
  "id": 1,
  "title": "sunt aut facere repellat provident...",
  "body": "quia et suscipit..."
}
```

### Posts by User (GET /posts?userId=1)
```json
[
  {
    "userId": 1,
    "id": 1,
    "title": "sunt aut facere...",
    "body": "quia et suscipit..."
  },
  ...
]
```

### User Profile (GET /users/5)
```json
{
  "id": 5,
  "name": "Chelsey Dietrich",
  "username": "Kamren",
  "email": "Lucio_Hettinger@annie.ca",
  "address": {
    "city": "Roscoeview"
  },
  "company": {
    "name": "Keebler LLC"
  }
}
```

## Troubleshooting

### If Path Parameters Don't Work
Check logs for:
```
🔍 _extract_parameters CALLED for query: ...
🔍 Found N required parameters: ['post_id']
🔍 Extracted parameters: {'post_id': 1}
```

If you DON'T see these logs, parameter extraction is not being called.

### If Query Parameters Don't Work
Check if the URL is being built correctly:
```
INFO - Executing REST GET request to: /posts?userId=1
```

Should NOT be:
```
ERROR - Executing REST GET request to: /posts?userId={{user_id}}
```

## Success Criteria

For the JSONPlaceholder adapter to be considered working:

- ✅ Path parameter extraction works (post_id, user_id)
- ✅ Query parameter extraction works (userId, postId)
- ✅ No 404 errors on valid queries
- ✅ Responses are correctly parsed
- ✅ Results are formatted and returned to user

## Comparison with GitHub

| Aspect | GitHub API | JSONPlaceholder |
|--------|-----------|-----------------|
| Auth | Required (token) | None |
| Complexity | High (many entities) | Low (4 entities) |
| Rate Limits | Yes (strict) | No |
| Parameter Types | Mixed | Simple integers |
| Response Format | Complex nested | Simple flat |
| IDs | Strings/UUIDs | Sequential integers |

JSONPlaceholder is intentionally **much simpler** to isolate the parameter extraction issue.
