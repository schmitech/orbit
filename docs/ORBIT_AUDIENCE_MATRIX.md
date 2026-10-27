# Who ORBIT is for

**For organizations that want AI to work with their own information, on infrastructure they control.**

ORBIT connects documents, databases, and business tools to local or hosted AI models through one API. It is an Apache 2.0 open-source AI gateway, retrieval engine, and agent host, with security and administration features included.

## Organizations and the features they may need

These are potential fits and pilot ideas, rather than customer references.

| Organization type | What they are looking for | Relevant ORBIT features | Example first pilot |
| :--- | :--- | :--- | :--- |
| **Government agencies and municipalities** | AI over internal information; control over hosting and access | On-premises deployment; local models; single sign-on; role-based access; audit logs | Staff assistant for policies, procedures, and service information |
| **Banks, credit unions, and insurers** | Controlled access to operational data; traceable AI usage | SQL/API adapters; guarded read-only intent-SQL queries; identity controls; audit and estimated-cost dashboards | Internal policy assistant or operational reporting assistant |
| **Healthcare providers and health administration** | Search over administrative knowledge with deployment and privacy controls | Document retrieval; local inference; configurable personal-information detection; role-based access | Staff assistant for approved administrative procedures |
| **Legal, accounting, and consulting firms** | Answers from engagement documents; choice of model and hosting | PDF, spreadsheet, and scanned-document processing; retrieval and reranking; local or hosted models | Document assistant for a selected engagement |
| **Manufacturers, utilities, and industrial operators** | Access to technical knowledge in restricted network environments | On-premises deployment; offline operation with local dependencies; document and SQL retrieval | Maintenance-manual and procedure assistant |
| **Universities and research organizations** | Flexible model experimentation; shared access with usage limits | Local/cloud model choice; OpenAI-compatible API; per-key quotas; usage and estimated-cost tracking | Shared AI gateway for a lab or research group |
| **Retailers, service businesses, and support organizations** | Assistants connected to business records; ticket routing | SQL/REST/GraphQL adapters; chat and voice; typed decisions with probabilities | Order-status assistant or support-ticket triage pilot |
| **Software companies and systems integrators** | An AI backend for custom products and tool workflows | OpenAI-compatible API; MCP tools; A2A agent communication; asynchronous messaging; configurable adapters | Product assistant connected to one data source and one tool |
| **Organizations serving multiple internal teams** | Shared AI access with centrally managed models and usage | Per-adapter model choices; automatic model selection; provider fallbacks; per-key limits; admin UI | Department assistants with separate adapters and usage limits |

**Strongest fit:** Teams with private information or existing systems to connect, a need for deployment or model choice, and technical capacity to configure and operate the platform.

**Deployment considerations:** Offline operation requires local models and compatible local services throughout. Security controls must be configured and validated; the NIST control mapping supports assessment and does not certify a deployment. Hosting, model services, and operations carry costs.

**Explore a pilot:** Pick one workflow, one data source, and the people allowed to use it. [Explore ORBIT on GitHub](https://github.com/schmitech/orbit) or start with the [tutorial](tutorial.md).

Feature details: [Overview](../README.md) · [Capability matrix](ORBIT_CAPABILITY_MATRIX.md) · [Security architecture and control mapping](security/nist-sp800-53-and-ai-security.md)
