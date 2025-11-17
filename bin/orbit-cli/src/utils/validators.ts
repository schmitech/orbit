export function isValidUrl(url: string): boolean {
  try {
    new URL(url);
    return true;
  } catch {
    return false;
  }
}

export function validateServerUrl(url: string): string {
  if (!url) {
    throw new Error('Server URL is required');
  }

  // Add protocol if missing
  if (!url.startsWith('http://') && !url.startsWith('https://')) {
    url = `http://${url}`;
  }

  if (!isValidUrl(url)) {
    throw new Error('Invalid server URL format');
  }

  return url;
}

export function validateUsername(username: string): string {
  if (!username || username.trim().length === 0) {
    throw new Error('Username is required');
  }
  if (username.length < 3) {
    throw new Error('Username must be at least 3 characters');
  }
  return username.trim();
}

export function validatePassword(password: string): string {
  if (!password || password.length === 0) {
    throw new Error('Password is required');
  }
  if (password.length < 6) {
    throw new Error('Password must be at least 6 characters');
  }
  return password;
}

export function validateApiKey(apiKey: string): string {
  if (!apiKey || apiKey.trim().length === 0) {
    throw new Error('API key is required');
  }
  if (apiKey.length < 10) {
    throw new Error('API key format is invalid');
  }
  return apiKey.trim();
}

export function validatePromptId(promptId: string): string {
  if (!promptId || promptId.trim().length === 0) {
    throw new Error('Prompt ID is required');
  }
  return promptId.trim();
}

export function validateUserId(userId: string): string {
  if (!userId || userId.trim().length === 0) {
    throw new Error('User ID is required');
  }
  return userId.trim();
}

export function maskApiKey(apiKey: string): string {
  if (!apiKey || apiKey.length < 4) {
    return '***';
  }
  return `***${apiKey.slice(-4)}`;
}

export function formatDate(date: number | string | undefined): string {
  if (!date) {
    return 'N/A';
  }

  let timestamp: number;
  if (typeof date === 'string') {
    timestamp = new Date(date).getTime() / 1000;
  } else {
    timestamp = date;
  }

  const d = new Date(timestamp * 1000);
  return d.toISOString().split('T')[0];
}

export function formatUptime(seconds: number): string {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);

  const parts: string[] = [];
  if (days > 0) parts.push(`${days}d`);
  if (hours > 0) parts.push(`${hours}h`);
  if (minutes > 0) parts.push(`${minutes}m`);

  return parts.length > 0 ? parts.join(' ') : '< 1m';
}

