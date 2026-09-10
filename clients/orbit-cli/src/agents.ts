import type { AdapterInfo, ApiClient } from '@schmitech/chatbot-api';

export interface AgentChoice {
  label: string;
  /** undefined selects the key's own adapter (the default) rather than a skill. */
  skill: string | undefined;
  adapterName: string;
}

/**
 * List the key's own adapter plus every enabled skill, per the roadmap's
 * `/agents` design: the chat adapter is fixed by the API key, but a skill
 * re-targets a turn to that skill's own adapter (see
 * docs/roadmap/orbit-cli-repl.md's "`/agents` — what it can and cannot do").
 * Skill discovery is best-effort — a server with none registered, or a
 * failing call, just leaves the single default adapter.
 */
export async function listAgents(client: ApiClient, ownAdapter: AdapterInfo): Promise<AgentChoice[]> {
  const choices: AgentChoice[] = [
    { label: `${ownAdapter.client_name} (default)`, skill: undefined, adapterName: ownAdapter.adapter_name },
  ];

  try {
    const { skills } = await client.getAllSkills();
    for (const skill of skills.filter((s) => s.enabled)) {
      choices.push({
        label: `${skill.name} — ${skill.description}`,
        skill: skill.name,
        adapterName: skill.adapter_name,
      });
    }
  } catch {
    // No skills registered, or discovery failed — single-agent is fine.
  }

  return choices;
}

export function findAgent(agents: AgentChoice[], query: string): AgentChoice | undefined {
  const index = Number(query);
  if (Number.isInteger(index) && index >= 1 && index <= agents.length) {
    return agents[index - 1];
  }
  return agents.find((a) => a.skill?.toLowerCase() === query.toLowerCase());
}
