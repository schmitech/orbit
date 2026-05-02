import { getApi } from '../apiClient';
import type { SkillInfo } from '../types';

export class SkillsService {
  static async getAdapterSkills(
    adapterName: string,
    clientAdapterName: string
  ): Promise<string[]> {
    const api = await getApi();
    const client = new api.ApiClient({ apiUrl: '', adapterName: clientAdapterName });
    if (!client.getAdapterSkills) {
      return [];
    }
    const result = await client.getAdapterSkills(adapterName);
    return result.available_skills;
  }

  static async getAllSkills(clientAdapterName: string): Promise<SkillInfo[]> {
    const api = await getApi();
    const client = new api.ApiClient({ apiUrl: '', adapterName: clientAdapterName });
    if (!client.getAllSkills) {
      return [];
    }
    const result = await client.getAllSkills();
    return result.skills;
  }
}
