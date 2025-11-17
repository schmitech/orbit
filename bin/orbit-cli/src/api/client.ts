import axios, { AxiosInstance, AxiosError } from 'axios';
import { ConfigManager } from '../config/manager';

export class OrbitError extends Error {
  constructor(
    message: string,
    public statusCode?: number,
    public code?: string
  ) {
    super(message);
    this.name = 'OrbitError';
  }
}

export class AuthenticationError extends OrbitError {
  constructor(message: string = 'Authentication failed') {
    super(message, 401);
    this.name = 'AuthenticationError';
  }
}

export class NetworkError extends OrbitError {
  constructor(message: string = 'Network error') {
    super(message);
    this.name = 'NetworkError';
  }
}

export interface LoginResponse {
  token: string;
  user: {
    id: string;
    username: string;
    role: string;
    active: boolean;
  };
}

export interface User {
  id: string;
  username: string;
  role: string;
  active: boolean;
  created_at?: string;
  last_login?: string;
}

export interface ApiKey {
  api_key: string;
  client_name: string;
  adapter_name?: string;
  collection_name?: string;
  notes?: string;
  active: boolean;
  created_at?: number;
  system_prompt_id?: string;
}

export interface SystemPrompt {
  id: string;
  name: string;
  prompt: string;
  version: string;
  created_at?: number;
  updated_at?: number;
}

export interface HealthStatus {
  status: string;
  components?: Record<string, any>;
}

export interface SystemStatus {
  status: string;
  fault_tolerance?: {
    enabled: boolean;
    adapters?: Record<string, any>;
  };
}

export class ApiClient {
  private client: AxiosInstance;
  private configManager: ConfigManager;
  private retryAttempts: number = 3;
  private timeout: number = 30000;

  constructor(configManager: ConfigManager) {
    this.configManager = configManager;
    this.client = axios.create({
      timeout: this.timeout,
      headers: {
        'Content-Type': 'application/json'
      }
    });

    // Add request interceptor to inject auth token
    this.client.interceptors.request.use((config) => {
      const token = this.configManager.getAuthToken();
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
      return config;
    });

    // Add response interceptor for error handling
    this.client.interceptors.response.use(
      (response) => response,
      async (error: AxiosError) => {
        return this.handleError(error);
      }
    );
  }

  private async handleError(error: AxiosError): Promise<never> {
    if (!error.response) {
      // Network error
      throw new NetworkError(
        `Failed to connect to server at ${this.configManager.getServerUrl()}`
      );
    }

    const status = error.response.status;
    const data = error.response.data as any;

    switch (status) {
      case 401:
        throw new AuthenticationError(
          data?.detail || 'Authentication failed. Please run "login" first.'
        );
      case 403:
        throw new OrbitError(
          data?.detail || 'Permission denied. Admin privileges may be required.',
          403
        );
      case 404:
        throw new OrbitError(data?.detail || 'Resource not found', 404);
      case 409:
        throw new OrbitError(
          data?.detail || 'Resource already exists or conflict detected',
          409
        );
      case 400:
        throw new OrbitError(
          data?.detail || 'Bad request',
          400
        );
      case 503:
        throw new OrbitError(
          data?.detail || 'Service unavailable',
          503
        );
      default:
        throw new OrbitError(
          data?.detail || `Request failed: ${status}`,
          status
        );
    }
  }

  private getBaseUrl(): string {
    return this.configManager.getServerUrl().replace(/\/$/, '');
  }

  // Authentication endpoints
  async login(username: string, password: string): Promise<LoginResponse> {
    const response = await this.client.post<LoginResponse>(
      `${this.getBaseUrl()}/auth/login`,
      { username, password }
    );
    return response.data;
  }

  async logout(): Promise<{ message: string }> {
    const response = await this.client.post<{ message: string }>(
      `${this.getBaseUrl()}/auth/logout`
    );
    return response.data;
  }

  async getCurrentUser(): Promise<User> {
    const response = await this.client.get<User>(
      `${this.getBaseUrl()}/auth/me`
    );
    return response.data;
  }

  async registerUser(
    username: string,
    password: string,
    role: string = 'user'
  ): Promise<{ id: string; username: string; role: string }> {
    const response = await this.client.post<{ id: string; username: string; role: string }>(
      `${this.getBaseUrl()}/auth/register`,
      { username, password, role }
    );
    return response.data;
  }

  // User management endpoints
  async listUsers(params?: {
    role?: string;
    active_only?: boolean;
    limit?: number;
    offset?: number;
  }): Promise<User[]> {
    const response = await this.client.get<User[]>(
      `${this.getBaseUrl()}/auth/users`,
      { params }
    );
    return response.data;
  }

  async getUserByUsername(username: string): Promise<{ id: string; username: string; role: string; active: boolean }> {
    const response = await this.client.get<{ id: string; username: string; role: string; active: boolean }>(
      `${this.getBaseUrl()}/auth/users/by-username`,
      { params: { username } }
    );
    return response.data;
  }

  async resetUserPassword(userId: string, newPassword: string): Promise<{ message: string; user_id: string }> {
    const response = await this.client.post<{ message: string; user_id: string }>(
      `${this.getBaseUrl()}/auth/reset-password`,
      { user_id: userId, new_password: newPassword }
    );
    return response.data;
  }

  async changePassword(
    currentPassword: string,
    newPassword: string
  ): Promise<{ message: string }> {
    const response = await this.client.post<{ message: string }>(
      `${this.getBaseUrl()}/auth/change-password`,
      { current_password: currentPassword, new_password: newPassword }
    );
    return response.data;
  }

  async deleteUser(userId: string): Promise<{ message: string; user_id: string }> {
    const response = await this.client.delete<{ message: string; user_id: string }>(
      `${this.getBaseUrl()}/auth/users/${userId}`
    );
    return response.data;
  }

  async activateUser(userId: string): Promise<{ message: string; user_id: string }> {
    const response = await this.client.post<{ message: string; user_id: string }>(
      `${this.getBaseUrl()}/auth/users/${userId}/activate`
    );
    return response.data;
  }

  async deactivateUser(userId: string): Promise<{ message: string; user_id: string }> {
    const response = await this.client.post<{ message: string; user_id: string }>(
      `${this.getBaseUrl()}/auth/users/${userId}/deactivate`
    );
    return response.data;
  }

  // API Key endpoints
  async createApiKey(data: {
    client_name: string;
    adapter_name?: string;
    notes?: string;
    system_prompt_id?: string;
  }): Promise<ApiKey> {
    const response = await this.client.post<ApiKey>(
      `${this.getBaseUrl()}/admin/api-keys`,
      data
    );
    return response.data;
  }

  async listApiKeys(params?: {
    active_only?: boolean;
    limit?: number;
    offset?: number;
    adapter?: string;
  }): Promise<ApiKey[]> {
    const response = await this.client.get<ApiKey[]>(
      `${this.getBaseUrl()}/admin/api-keys`,
      { params }
    );
    return response.data;
  }

  async getApiKeyStatus(apiKey: string): Promise<ApiKey & { last_used?: string }> {
    const response = await this.client.get<ApiKey & { last_used?: string }>(
      `${this.getBaseUrl()}/admin/api-keys/${apiKey}/status`
    );
    return response.data;
  }

  async testApiKey(apiKey: string): Promise<any> {
    try {
      const response = await axios.get(
        `${this.getBaseUrl()}/health`,
        {
          headers: { 'X-API-Key': apiKey },
          timeout: this.timeout
        }
      );
      return { status: 'success', message: 'API key is valid and active', server_response: response.data };
    } catch (error: any) {
      if (error.response?.status === 401) {
        return { status: 'error', error: 'API key is invalid or deactivated' };
      }
      if (error.response?.status === 403) {
        return { status: 'error', error: 'API key is valid but access forbidden' };
      }
      throw new NetworkError('Failed to test API key');
    }
  }

  async renameApiKey(oldApiKey: string, newApiKey: string): Promise<{ status: string; message: string; new_api_key: string }> {
    const response = await this.client.patch<{ status: string; message: string; new_api_key: string }>(
      `${this.getBaseUrl()}/admin/api-keys/${oldApiKey}/rename`,
      null,
      { params: { new_api_key: newApiKey } }
    );
    return response.data;
  }

  async deactivateApiKey(apiKey: string): Promise<{ status: string; message: string }> {
    const response = await this.client.post<{ status: string; message: string }>(
      `${this.getBaseUrl()}/admin/api-keys/deactivate`,
      { api_key: apiKey }
    );
    return response.data;
  }

  async deleteApiKey(apiKey: string): Promise<{ status: string; message: string }> {
    const response = await this.client.delete<{ status: string; message: string }>(
      `${this.getBaseUrl()}/admin/api-keys/${apiKey}`
    );
    return response.data;
  }

  // System Prompt endpoints
  async createPrompt(
    name: string,
    prompt: string,
    version: string = '1.0'
  ): Promise<SystemPrompt> {
    const response = await this.client.post<SystemPrompt>(
      `${this.getBaseUrl()}/admin/prompts`,
      { name, prompt, version }
    );
    return response.data;
  }

  async listPrompts(params?: {
    name_filter?: string;
    limit?: number;
    offset?: number;
  }): Promise<SystemPrompt[]> {
    const response = await this.client.get<SystemPrompt[]>(
      `${this.getBaseUrl()}/admin/prompts`,
      { params }
    );
    return response.data;
  }

  async getPrompt(promptId: string): Promise<SystemPrompt> {
    const response = await this.client.get<SystemPrompt>(
      `${this.getBaseUrl()}/admin/prompts/${promptId}`
    );
    return response.data;
  }

  async updatePrompt(
    promptId: string,
    prompt: string,
    version?: string
  ): Promise<SystemPrompt> {
    const data: any = { prompt };
    if (version) {
      data.version = version;
    }
    const response = await this.client.put<SystemPrompt>(
      `${this.getBaseUrl()}/admin/prompts/${promptId}`,
      data
    );
    return response.data;
  }

  async deletePrompt(promptId: string): Promise<{ status: string; message: string }> {
    const response = await this.client.delete<{ status: string; message: string }>(
      `${this.getBaseUrl()}/admin/prompts/${promptId}`
    );
    return response.data;
  }

  async associatePromptWithApiKey(
    apiKey: string,
    promptId: string
  ): Promise<{ status: string; message: string }> {
    const response = await this.client.post<{ status: string; message: string }>(
      `${this.getBaseUrl()}/admin/api-keys/${apiKey}/prompt`,
      { prompt_id: promptId }
    );
    return response.data;
  }

  // Admin endpoints
  async reloadAdapters(adapterName?: string): Promise<{
    status: string;
    message: string;
    summary: any;
    timestamp: string;
  }> {
    const params = adapterName ? { adapter_name: adapterName } : {};
    const response = await this.client.post<{
      status: string;
      message: string;
      summary: any;
      timestamp: string;
    }>(
      `${this.getBaseUrl()}/admin/reload-adapters`,
      null,
      { params }
    );
    return response.data;
  }

  // Health/Server endpoints
  async getHealth(): Promise<HealthStatus> {
    const response = await axios.get<HealthStatus>(
      `${this.getBaseUrl()}/health`
    );
    return response.data;
  }

  async getSystemStatus(): Promise<SystemStatus> {
    const response = await axios.get<SystemStatus>(
      `${this.getBaseUrl()}/health/system`
    );
    return response.data;
  }

  async getAdapterHealth(): Promise<any> {
    const response = await axios.get(
      `${this.getBaseUrl()}/health/adapters`
    );
    return response.data;
  }
}

