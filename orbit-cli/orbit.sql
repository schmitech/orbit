-- API Key Operations

-- 1. Create a new API key
-- Function to generate a random API key (this would be implemented in your application code)
-- In SQLite you might implement a function or handle this in your application code
-- Here's the insert operation:
INSERT INTO api_keys (api_key, collection_name, client_name, notes)
VALUES (:api_key, :collection_name, :client_name, :notes);

-- 2. List all API keys
SELECT 
    api_keys.id, 
    api_keys.api_key, 
    api_keys.collection_name, 
    api_keys.client_name, 
    api_keys.notes, 
    api_keys.active, 
    api_keys.created_at, 
    api_keys.last_used_at,
    system_prompts.id AS prompt_id,
    system_prompts.name AS prompt_name
FROM 
    api_keys
LEFT JOIN 
    api_key_prompts ON api_keys.id = api_key_prompts.api_key_id
LEFT JOIN 
    system_prompts ON api_key_prompts.prompt_id = system_prompts.id;

-- 3. Get a specific API key by its value
SELECT 
    api_keys.id, 
    api_keys.api_key, 
    api_keys.collection_name, 
    api_keys.client_name, 
    api_keys.notes, 
    api_keys.active, 
    api_keys.created_at, 
    api_keys.last_used_at,
    system_prompts.id AS prompt_id,
    system_prompts.name AS prompt_name
FROM 
    api_keys
LEFT JOIN 
    api_key_prompts ON api_keys.id = api_key_prompts.api_key_id
LEFT JOIN 
    system_prompts ON api_key_prompts.prompt_id = system_prompts.id
WHERE
    api_keys.api_key = :api_key;

-- 4. Deactivate an API key
UPDATE api_keys
SET active = FALSE
WHERE api_key = :api_key;

-- 5. Delete an API key
DELETE FROM api_keys
WHERE api_key = :api_key;

-- 6. Update last used timestamp for an API key
UPDATE api_keys
SET last_used_at = CURRENT_TIMESTAMP
WHERE api_key = :api_key;

-- 7. Check if an API key is valid and active
SELECT active FROM api_keys WHERE api_key = :api_key;

-- System Prompt Operations

-- 1. Create a new system prompt
INSERT INTO system_prompts (name, prompt_text, version)
VALUES (:name, :prompt_text, :version);

-- 2. List all system prompts
SELECT id, name, prompt_text, version, created_at, updated_at 
FROM system_prompts;

-- 3. Get a specific prompt by ID
SELECT id, name, prompt_text, version, created_at, updated_at 
FROM system_prompts 
WHERE id = :prompt_id;

-- 4. Get a specific prompt by name
SELECT id, name, prompt_text, version, created_at, updated_at 
FROM system_prompts 
WHERE name = :prompt_name;

-- 5. Update an existing system prompt
UPDATE system_prompts
SET 
    prompt_text = :prompt_text,
    version = :version,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :prompt_id;

-- 6. Delete a system prompt
DELETE FROM system_prompts
WHERE id = :prompt_id;

-- API Key - Prompt Association Operations

-- 1. Associate a system prompt with an API key
-- First, get the API key ID
SELECT id FROM api_keys WHERE api_key = :api_key;
-- Then, insert or replace the association
INSERT OR REPLACE INTO api_key_prompts (api_key_id, prompt_id)
VALUES (:api_key_id, :prompt_id);

-- 2. Remove a prompt association from an API key
DELETE FROM api_key_prompts
WHERE api_key_id = (SELECT id FROM api_keys WHERE api_key = :api_key);

-- 3. Get the prompt associated with an API key
SELECT 
    system_prompts.id,
    system_prompts.name,
    system_prompts.prompt_text,
    system_prompts.version
FROM 
    api_key_prompts
JOIN 
    system_prompts ON api_key_prompts.prompt_id = system_prompts.id
WHERE 
    api_key_prompts.api_key_id = (SELECT id FROM api_keys WHERE api_key = :api_key);

-- Utility Queries

-- 1. Get all API keys for a specific collection
SELECT 
    api_keys.id, 
    api_keys.api_key, 
    api_keys.client_name, 
    api_keys.notes, 
    api_keys.active
FROM 
    api_keys
WHERE 
    collection_name = :collection_name;

-- 2. Find all API keys associated with a specific prompt
SELECT 
    api_keys.id, 
    api_keys.api_key, 
    api_keys.collection_name, 
    api_keys.client_name
FROM 
    api_keys
JOIN 
    api_key_prompts ON api_keys.id = api_key_prompts.api_key_id
WHERE 
    api_key_prompts.prompt_id = :prompt_id;

-- 3. Get usage statistics (count of active/inactive keys)
SELECT 
    COUNT(*) AS total_keys,
    SUM(CASE WHEN active = TRUE THEN 1 ELSE 0 END) AS active_keys,
    SUM(CASE WHEN active = FALSE THEN 1 ELSE 0 END) AS inactive_keys
FROM 
    api_keys;

-- 4. Get counts by collection
SELECT 
    collection_name,
    COUNT(*) AS key_count
FROM 
    api_keys
GROUP BY 
    collection_name;