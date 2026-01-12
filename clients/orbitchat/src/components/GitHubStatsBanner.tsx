import { Github, Star, GitBranch } from 'lucide-react';
import { useGitHubStats } from '../hooks/useGitHubStats';
import { getGitHubOwner, getGitHubRepo, getShowGitHubStats } from '../utils/runtimeConfig';

interface GitHubStatsBannerProps {
  className?: string;
}

export function GitHubStatsBanner({ className = '' }: GitHubStatsBannerProps) {
  const showStats = getShowGitHubStats();
  const owner = getGitHubOwner();
  const repo = getGitHubRepo();
  const githubStats = useGitHubStats(owner, repo);

  if (!showStats) {
    return null;
  }

  const repoUrl = `https://github.com/${owner}/${repo}`;

  const renderStats = () => {
    if (githubStats.isLoading) {
      return (
        <div className="flex items-center gap-2 text-xs font-medium text-gray-600 dark:text-[#bfc2cd]">
          <div className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-gray-300 border-t-transparent dark:border-[#4a4b54] dark:border-t-transparent" />
          <span>Loading…</span>
        </div>
      );
    }

    if (githubStats.error) {
      return (
        <div className="text-xs font-medium text-red-600 dark:text-red-400">
          Failed to load stats.
        </div>
      );
    }

    return (
      <div className="flex flex-wrap items-center justify-center gap-2 text-xs font-semibold text-gray-800 dark:text-[#ececf1]">
        <span className="inline-flex items-center gap-1 rounded-full bg-white/80 px-2.5 py-0.5 text-gray-800 shadow-sm dark:bg-[#2c2f36] dark:text-[#ececf1]">
          <Star className="h-3.5 w-3.5 text-yellow-500 dark:text-yellow-300" />
          {githubStats.stars.toLocaleString()}
        </span>
        <span className="inline-flex items-center gap-1 rounded-full bg-white/80 px-2.5 py-0.5 text-gray-800 shadow-sm dark:bg-[#2c2f36] dark:text-[#ececf1]">
          <GitBranch className="h-3.5 w-3.5 text-blue-500 dark:text-blue-300" />
          {githubStats.forks.toLocaleString()}
        </span>
      </div>
    );
  };

  return (
    <a
      href={repoUrl}
      target="_blank"
      rel="noopener noreferrer"
      className={`inline-flex flex-col items-center gap-1 text-sm text-gray-700 transition hover:text-blue-700 dark:text-[#ececf1] dark:hover:text-blue-300 ${className}`}
    >
      <div className="flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wide text-blue-600 dark:text-blue-300">
        <Github className="h-3.5 w-3.5" />
        <span>Powered by ORBIT</span>
      </div>
      {renderStats()}
    </a>
  );
}
