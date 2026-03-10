import { getAccessToken } from './tokenStore';
import { getAuthenticatedUserId } from './authState';

const GUEST_USER_ID_KEY = 'orbitchat-guest-user-id';

type JwtPayload = {
  sub?: unknown;
  user_id?: unknown;
  email?: unknown;
  preferred_username?: unknown;
};

function toNonEmptyString(value: unknown): string | null {
  if (typeof value !== 'string') {
    return null;
  }

  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function decodeJwtPayload(token: string): JwtPayload | null {
  const parts = token.split('.');
  if (parts.length < 2) {
    return null;
  }

  try {
    const normalized = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, '=');
    const decoded = atob(padded);
    return JSON.parse(decoded) as JwtPayload;
  } catch {
    return null;
  }
}

function getGuestUserId(): string {
  if (typeof window === 'undefined') {
    return 'guest:orbitchat:server';
  }

  const stored = window.localStorage.getItem(GUEST_USER_ID_KEY);
  if (stored && stored.trim().length > 0) {
    return stored;
  }

  const guestUserId = `guest:orbitchat:${Date.now()}_${Math.random().toString(36).slice(2, 11)}`;
  window.localStorage.setItem(GUEST_USER_ID_KEY, guestUserId);
  return guestUserId;
}

export async function getUserIdHeaderValue(): Promise<string> {
  const authenticatedUserId = getAuthenticatedUserId();
  if (authenticatedUserId) {
    return authenticatedUserId;
  }

  const token = await getAccessToken();
  if (token) {
    const payload = decodeJwtPayload(token);
    const tokenUserId =
      toNonEmptyString(payload?.sub) ||
      toNonEmptyString(payload?.user_id) ||
      toNonEmptyString(payload?.preferred_username) ||
      toNonEmptyString(payload?.email);

    if (tokenUserId) {
      return tokenUserId;
    }
  }

  return getGuestUserId();
}
