import type { AdapterModelInfo, ApiClient } from '@schmitech/chatbot-api';

/**
 * List the models allowed for the currently active agent.
 *
 * The server resolves models for the API key's own adapter regardless of
 * `adapterName` unless `skill` is also passed — so a selected skill must be
 * threaded through here, not just its backing adapter name, or this quietly
 * falls back to the base adapter's models.
 */
export async function listModels(
  client: ApiClient,
  adapterName: string,
  skill: string | undefined
): Promise<AdapterModelInfo[]> {
  const { models } = await client.getAdapterModels(adapterName, skill);
  return models;
}

export function findModel(models: AdapterModelInfo[], query: string): AdapterModelInfo | undefined {
  const index = Number(query);
  if (Number.isInteger(index) && index >= 1 && index <= models.length) {
    return models[index - 1];
  }
  return models.find((m) => m.name?.toLowerCase() === query.toLowerCase() || m.id?.toLowerCase() === query.toLowerCase());
}
