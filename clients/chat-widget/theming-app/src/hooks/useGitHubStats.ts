import { useState, useEffect } from 'react';

interface GitHubStats {
  stars: number;
  forks: number;
  license: string;
  description: string;
  isLoading: boolean;
  error: string | null;
}

export const useGitHubStats = (owner: string, repo: string): GitHubStats => {
  const [stats, setStats] = useState<GitHubStats>({
    stars: 0,
    forks: 0,
    license: 'Apache-2.0',
    description: 'An adaptable, open-source context-aware inference engine designed for privacy, control, and independence from proprietary models.',
    isLoading: true,
    error: null
  });

  useEffect(() => {
    const fetchGitHubStats = async () => {
      try {
        const response = await fetch(`https://api.github.com/repos/${owner}/${repo}`);
        
        if (!response.ok) {
          throw new Error(`GitHub API error: ${response.status}`);
        }

        const data = await response.json();
        
        setStats({
          stars: data.stargazers_count || 0,
          forks: data.forks_count || 0,
          license: data.license?.name || 'Apache-2.0',
          description: data.description || 'An adaptable, open-source context-aware inference engine designed for privacy, control, and independence from proprietary models.',
          isLoading: false,
          error: null
        });
      } catch (error) {
        console.warn('Failed to fetch GitHub stats:', error);
        // Fallback to default values if API fails
        setStats({
          stars: 104,
          forks: 19,
          license: 'Apache-2.0',
          description: 'An adaptable, open-source context-aware inference engine designed for privacy, control, and independence from proprietary models.',
          isLoading: false,
          error: error instanceof Error ? error.message : 'Failed to fetch stats'
        });
      }
    };

    fetchGitHubStats();
  }, [owner, repo]);

  return stats;
};
