import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ApiClient } from '../api';
import { TEST_API_KEY, TEST_API_URL } from './config';

describe('Auth endpoints', () => {
  let client: ApiClient;

  beforeEach(() => {
    vi.restoreAllMocks();
    client = new ApiClient({ apiUrl: TEST_API_URL, apiKey: TEST_API_KEY });
  });

  describe('login', () => {
    it('should return token and user on success', async () => {
      const mockResponse = { token: 'abc123', user: { id: 'u1', username: 'admin', role: 'admin' } };
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(mockResponse) });

      const result = await client.login('admin', 'password');

      expect(result.token).toBe('abc123');
      expect(result.user.username).toBe('admin');
      const [url, opts] = (global.fetch as any).mock.calls[0];
      expect(url).toBe(`${TEST_API_URL}/auth/login`);
      expect(opts.method).toBe('POST');
      expect(JSON.parse(opts.body)).toEqual({ username: 'admin', password: 'password' });
    });

    it('should throw on HTTP error', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 401, text: () => Promise.resolve('Unauthorized') });
      await expect(client.login('bad', 'creds')).rejects.toThrow('Login failed');
    });
  });

  describe('logout', () => {
    it('should call logout endpoint with bearer token', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ message: 'Logged out' }) });

      const result = await client.logout('mytoken');

      expect(result.message).toBe('Logged out');
      const [url, opts] = (global.fetch as any).mock.calls[0];
      expect(url).toBe(`${TEST_API_URL}/auth/logout`);
      expect(opts.method).toBe('POST');
      expect(opts.headers.Authorization).toBe('Bearer mytoken');
    });

    it('should call logout without token when not provided', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ message: 'Logged out' }) });
      await client.logout();
      const [, opts] = (global.fetch as any).mock.calls[0];
      expect(opts.headers.Authorization).toBeUndefined();
    });
  });

  describe('getCurrentUser', () => {
    it('should return user info', async () => {
      const mockUser = { id: 'u1', username: 'alice', role: 'user' };
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(mockUser) });

      const result = await client.getCurrentUser('token123');

      expect(result.username).toBe('alice');
      const [url, opts] = (global.fetch as any).mock.calls[0];
      expect(url).toBe(`${TEST_API_URL}/auth/me`);
      expect(opts.headers.Authorization).toBe('Bearer token123');
    });
  });

  describe('registerUser', () => {
    it('should register a new user', async () => {
      const mockResponse = { id: 'u2', username: 'bob', role: 'user' };
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(mockResponse) });

      const result = await client.registerUser({ username: 'bob', password: 'pass123' }, 'admintoken');

      expect(result.username).toBe('bob');
      const [url, opts] = (global.fetch as any).mock.calls[0];
      expect(url).toBe(`${TEST_API_URL}/auth/register`);
      expect(JSON.parse(opts.body)).toEqual({ username: 'bob', password: 'pass123', role: 'user' });
    });

    it('should use provided role', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ id: 'u3', username: 'charlie', role: 'admin' }) });
      await client.registerUser({ username: 'charlie', password: 'pass', role: 'admin' }, 'token');
      const [, opts] = (global.fetch as any).mock.calls[0];
      expect(JSON.parse(opts.body).role).toBe('admin');
    });
  });

  describe('listUsers', () => {
    it('should list users with no filters', async () => {
      const mockUsers = [{ id: 'u1', username: 'alice', role: 'user' }];
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(mockUsers) });

      const result = await client.listUsers({}, 'admintoken');

      expect(result).toHaveLength(1);
      const [url] = (global.fetch as any).mock.calls[0];
      expect(url).toBe(`${TEST_API_URL}/auth/users`);
    });

    it('should pass query params for filters', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve([]) });
      await client.listUsers({ role: 'admin', active_only: true, limit: 10, offset: 5 }, 'token');
      const [url] = (global.fetch as any).mock.calls[0];
      expect(url).toContain('role=admin');
      expect(url).toContain('active_only=true');
      expect(url).toContain('limit=10');
      expect(url).toContain('offset=5');
    });
  });

  describe('getUserByUsername', () => {
    it('should call correct endpoint', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ id: 'u1', username: 'alice', role: 'user' }) });
      await client.getUserByUsername('alice', 'token');
      const [url] = (global.fetch as any).mock.calls[0];
      expect(url).toContain(`${TEST_API_URL}/auth/users/by-username`);
      expect(url).toContain('username=alice');
    });
  });

  describe('deleteUser', () => {
    it('should call DELETE on user endpoint', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ message: 'Deleted', user_id: 'u1' }) });
      const result = await client.deleteUser('u1', 'token');
      expect(result.user_id).toBe('u1');
      const [url, opts] = (global.fetch as any).mock.calls[0];
      expect(url).toBe(`${TEST_API_URL}/auth/users/u1`);
      expect(opts.method).toBe('DELETE');
    });
  });

  describe('changePassword', () => {
    it('should post to change-password endpoint', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ message: 'Password changed' }) });
      await client.changePassword('old', 'new', 'token');
      const [url, opts] = (global.fetch as any).mock.calls[0];
      expect(url).toBe(`${TEST_API_URL}/auth/change-password`);
      expect(JSON.parse(opts.body)).toEqual({ current_password: 'old', new_password: 'new' });
    });
  });

  describe('resetUserPassword', () => {
    it('should post to reset-password endpoint', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ message: 'Reset', user_id: 'u1' }) });
      await client.resetUserPassword('u1', 'newpass', 'admintoken');
      const [url, opts] = (global.fetch as any).mock.calls[0];
      expect(url).toBe(`${TEST_API_URL}/auth/reset-password`);
      expect(JSON.parse(opts.body)).toEqual({ user_id: 'u1', new_password: 'newpass' });
    });
  });

  describe('deactivateUser / activateUser', () => {
    it('should POST to deactivate endpoint', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ message: 'Deactivated', user_id: 'u1' }) });
      await client.deactivateUser('u1', 'token');
      const [url, opts] = (global.fetch as any).mock.calls[0];
      expect(url).toBe(`${TEST_API_URL}/auth/users/u1/deactivate`);
      expect(opts.method).toBe('POST');
    });

    it('should POST to activate endpoint', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ message: 'Activated', user_id: 'u1' }) });
      await client.activateUser('u1', 'token');
      const [url, opts] = (global.fetch as any).mock.calls[0];
      expect(url).toBe(`${TEST_API_URL}/auth/users/u1/activate`);
      expect(opts.method).toBe('POST');
    });
  });
});
