import type { AdapterInfo, ApiClient } from '@schmitech/chatbot-api';

export interface AgentChoice {
  label: string;
  /** undefined selects the key's own adapter (the default) rather than a skill. */
  skill: string | undefined;
  adapterName: string;
}

/**
 * List the key's own adapter plus every enabled skill actually available to
 * it, per the roadmap's `/agents` design: the chat adapter is fixed by the
 * API key, but a skill re-targets a turn to that skill's own adapter (see
 * docs/roadmap/orbit-cli-repl.md's "`/agents` — what it can and cannot do").
 *
 * `getAllSkills()` is global — every skill registered anywhere on the
 * server, regardless of the calling key. Offering all of them let a turn
 * "succeed" at switching agents and then fail server-side on the next
 * message ("Skill 'Video' is not available for adapter 'simple-chat'").
 * `getAdapterSkills()` is the key-scoped counterpart (same endpoint
 * OrbitChat's `useSkills` hook calls): it returns the current adapter's
 * `available_skills` allowlist, which we intersect with `getAllSkills()`'s
 * metadata (name/description) the same way OrbitChat does. Skill discovery
 * is best-effort — a server with none registered, or a failing call (either
 * call, since an unfiltered list would just reintroduce the bug this
 * intersection exists to prevent), just leaves the single default adapter.
 */
export async function listAgents(client: ApiClient, ownAdapter: AdapterInfo): Promise<AgentChoice[]> {
  const choices: AgentChoice[] = [
    { label: `${ownAdapter.client_name} (default)`, skill: undefined, adapterName: ownAdapter.adapter_name },
  ];

  try {
    const [{ skills }, { available_skills }] = await Promise.all([
      client.getAllSkills(),
      client.getAdapterSkills(ownAdapter.adapter_name),
    ]);
    const allowed = new Set(available_skills);
    for (const skill of skills.filter((s) => s.enabled && allowed.has(s.name))) {
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
