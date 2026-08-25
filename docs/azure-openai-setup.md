# Azure OpenAI Setup

This guide walks through provisioning an Azure OpenAI resource, deploying a model, and wiring the credentials into ORBIT.

## Prerequisites

- An Azure subscription with access to Azure OpenAI Service. If your subscription hasn't been approved yet, request access at [aka.ms/oai/access](https://aka.ms/oai/access).
- Your Azure account must have permission to **create Cognitive Services resources** and **create deployments**. The built-in roles that grant this are `Cognitive Services Contributor` (resource creation) and `Cognitive Services OpenAI Contributor` (deployments). See [Azure OpenAI RBAC](https://learn.microsoft.com/en-us/azure/foundry-classic/openai/how-to/role-based-access-control) for details.
- ORBIT running with the `openai` Python package installed (included in the default install profile).

---

## 1. Create an Azure OpenAI Resource

1. Sign in to the [Azure Portal](https://portal.azure.com).
2. Search for **Azure OpenAI** in the top search bar and select it.
3. Click **Create**.
4. On the **Basics** tab, fill in:

   | Field | Notes |
   |---|---|
   | **Subscription** | The subscription used in your Azure OpenAI onboarding application |
   | **Resource group** | Create a new one or use an existing group |
   | **Region** | Affects latency but not runtime availability; pick one that offers the models you need (e.g. `East US`, `Canada East`) |
   | **Name** | Becomes `<your-resource-name>` in the endpoint URL — must be globally unique |
   | **Pricing tier** | Standard S0 (only tier currently available) |

5. Click **Next** to move to the **Network** tab.

### Network security (choose one)

| Option | When to use |
|---|---|
| **All networks, including the internet** | Default; simplest for getting started |
| **Selected networks** | Restrict to specific VNets and subnets; optionally add a firewall IP range |
| **Disabled (private endpoint only)** | No public access; add one or more private endpoints after creation |

For a private endpoint setup, ORBIT only needs the private DNS hostname in the `endpoint` field — no other code changes are needed.

6. Click **Next** to optionally add **Tags**, then **Next** again for **Review + submit**.
7. Confirm the settings and click **Create**. Wait ~1–2 minutes, then click **Go to resource**.

---

## 2. Deploy a Model

Azure OpenAI requires a named **deployment** on top of the base model. The deployment name (not the underlying model name) is what ORBIT and the API use.

1. Go to [ai.azure.com](https://ai.azure.com). Make sure the **New Foundry** toggle is **off** — these steps use **Foundry (classic)**.
2. In the **Keep building with Foundry** section, click **View all resources** and select your resource.

   > **Note:** You may be prompted to upgrade your Azure OpenAI resource to the new Foundry resource type. Click **Cancel** to proceed without upgrading (the classic resource works with ORBIT).

3. In the left sidebar under **Shared resources**, click **Deployments**.
4. Click **+ Deploy model** → **Deploy base model**.
5. Select a model (e.g. `gpt-4o`, `gpt-4-turbo`, `gpt-35-turbo`) and click **Confirm**.
6. Configure the deployment:

   | Field | Notes |
   |---|---|
   | **Deployment name** | The name your code (and ORBIT's `deployment` config field) uses to call the model — choose carefully, it can't be renamed |
   | **Deployment type** | `Standard` for most use cases; see [deployment types](https://learn.microsoft.com/en-us/azure/foundry-classic/openai/foundry-models/concepts/deployment-types) for Global-Standard, Global-Batch, and Provisioned-Managed |
   | **Content filter** (optional) | Assign a content filter policy to this deployment |
   | **Tokens per Minute Rate Limit** (optional) | Sets the effective TPM rate limit; adjustable later under **Quotas** |

7. Click **Deploy**. When provisioning finishes, the **Provisioning state** changes to **Succeeded**.

Note the deployment name — you'll need it in step 4.

---

## 3. Get Your Endpoint and API Key

1. Back in the Azure Portal, open your Azure OpenAI resource.
2. Go to **Resource Management** → **Keys and Endpoint**.
3. Copy:
   - **Endpoint** — use Azure's unified, versionless v1 API path: `https://<your-resource-name>.services.ai.azure.com/openai/v1`
   - **Key 1** (or Key 2) — this is your API key

---

## 4. Configure ORBIT

### Set the environment variable

Add to your `.env` file (or export in your shell):

```env
AZURE_ACCESS_KEY=<your-key-from-step-3>
```

### Add a preset in `config/azure.yaml`

Each Azure AI Foundry deployment is bound one-to-one to an `endpoint` + `deployment` name
(and often its own API key) — unlike other providers, you can't just list alternate model
names against one shared `base_url`/`api_key`. ORBIT models this as a **preset**, the same
pattern used for `config/ollama.yaml` and `config/llama_cpp.yaml`.

Add an entry under `azure_presets` in `config/azure.yaml`:

```yaml
azure_presets:
  your-deployment-name:
    endpoint: "https://<your-resource-name>.services.ai.azure.com/openai/v1"
    deployment: "your-deployment-name"       # the name you set in step 2
    api_key: ${AZURE_ACCESS_KEY}
    context_window: 128000
    temperature: 0.1
    top_p: 0.8
    max_tokens: 1024
    stream: true
```

### Point `config/inference.yaml` at the preset

Find the `azure:` block and set `use_preset` to the key you just added:

```yaml
inference:
  # ... other providers ...
  azure:
    enabled: true
    use_preset: "your-deployment-name"  # Reference to preset in config/azure.yaml
```

Key fields (in the preset):

| Field | Description |
|---|---|
| `endpoint` | Azure's unified v1 endpoint, must end with `/openai/v1` — this is versionless, no `api_version` needed |
| `deployment` | The deployment name from Azure AI Foundry — **not** the base model name |
| `api_key` | Reference to the env var; do not paste the key directly |

### Point an adapter at Azure

Set `provider: azure` in the adapter's config. Example in `config/adapters/<your-adapter>.yaml`:

```yaml
provider: azure
```

Or in `config/adapters.yaml`:

```yaml
adapters:
  - name: my-adapter
    provider: azure
    # ...
```

---

## 5. Verify

Start ORBIT and check the logs for:

```
Configured Azure AI service with deployment: your-deployment-name
Initialized Azure AI inference service with deployment your-deployment-name
```

Test with a quick curl:

```bash
curl http://localhost:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "your-deployment-name",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

---

## Common Errors

| Error | Cause | Fix |
|---|---|---|
| `Azure endpoint is required` | `endpoint` missing or blank in the preset | Add the full endpoint URL |
| `Azure API key is required` | `AZURE_ACCESS_KEY` not set or not loaded | Check `.env` and restart ORBIT |
| `401 Unauthorized` | Wrong API key | Re-copy Key 1 from Azure Portal → Keys and Endpoint |
| `DeploymentNotFound` | `deployment` name doesn't match Azure AI Foundry | Check exact deployment name (case-sensitive) |
| `BadRequest: API version not supported` | Using an old dated `api_version` or the legacy `.openai.azure.com/` endpoint | Switch `endpoint` to the versionless `https://<resource>.services.ai.azure.com/openai/v1` form; no `api_version` field needed |
| `Unsupported parameter: 'max_tokens' is not supported with this model` | Newer reasoning-family deployments (e.g. `gpt-5.x`) require `max_completion_tokens` | ORBIT already sends `max_completion_tokens` for Azure — update ORBIT if you see this on a current build |
| `404 Resource Not Found` | Wrong endpoint URL | Verify the endpoint ends with `/openai/v1` |
| `429 Too Many Requests` | TPM rate limit hit | Increase the rate limit under **Quotas** in Foundry portal, or use a Global-Standard deployment |

---

## Notes

- ORBIT talks to Azure via the `openai` SDK's `AsyncOpenAI` client, pointed at Azure's unified `/openai/v1` endpoint. That endpoint is versionless — no `api_version` field.
- Deployments are configured as named presets in `config/azure.yaml` (`azure_presets`), referenced from `config/inference.yaml` via `use_preset`. This mirrors how `config/ollama.yaml` and `config/llama_cpp.yaml` work, and exists because each Azure deployment is tied to its own endpoint/deployment/key — unlike other providers, it can't be swapped via an adapter's `allowed_models` list.
- For private networking, point `endpoint` at your private DNS hostname (still ending in `/openai/v1`) — no other ORBIT changes are needed.
- Deployment names can follow any naming convention, but they can't be renamed after creation. Using the model name (e.g. `gpt-4o`) is common for clarity.
