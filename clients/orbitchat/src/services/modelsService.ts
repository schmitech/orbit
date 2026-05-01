/**
 * Models Service
 *
 * Provides model discovery for the runtime model selection feature.
 * Use these methods to populate a model-picker UI before or when starting a conversation.
 */

import { getApi } from '../apiClient';
import type { AdapterModelsResponse, AllModelsResponse, AllowedModel } from '../types';

export class ModelsService {
  /**
   * List models available for a specific adapter.
   *
   * Returns the adapter's allowed_models list when restrictions are defined,
   * or a single entry for the adapter's default model when not.
   *
   * @param adapterName - The adapter to query (e.g. "simple-chat")
   * @param clientAdapterName - Adapter name associated with the API key (for auth header)
   * @returns Adapter name, restriction flag, and model list
   */
  static async getAdapterModels(
    adapterName: string,
    clientAdapterName: string
  ): Promise<AdapterModelsResponse> {
    const api = await getApi();
    const client = new api.ApiClient({ apiUrl: '', adapterName: clientAdapterName });
    if (!client.getAdapterModels) {
      throw new Error('getAdapterModels is not available on this API client');
    }
    return client.getAdapterModels(adapterName);
  }

  /**
   * List all models available across all enabled inference providers.
   *
   * Useful for building a global model picker that is not scoped to a specific adapter.
   *
   * @param clientAdapterName - Adapter name associated with the API key (for auth header)
   * @returns Flat list of all available models
   */
  static async getAllModels(clientAdapterName: string): Promise<AllModelsResponse> {
    const api = await getApi();
    const client = new api.ApiClient({ apiUrl: '', adapterName: clientAdapterName });
    if (!client.getAllModels) {
      throw new Error('getAllModels is not available on this API client');
    }
    return client.getAllModels();
  }

  /**
   * Convenience helper: returns just the models array for an adapter.
   * Returns an empty array if the adapter has no restrictions and no default.
   */
  static async listAdapterModels(
    adapterName: string,
    clientAdapterName: string
  ): Promise<AllowedModel[]> {
    const result = await ModelsService.getAdapterModels(adapterName, clientAdapterName);
    return result.models;
  }
}
