const DEFAULT_TEST_API_URL = 'http://localhost:3000';
const DEFAULT_TEST_API_KEY = 'chat-key';
const DEFAULT_TEST_SESSION_ID = 'test-session';

const trimTrailingSlash = (value: string): string => value.replace(/\/+$/, '');

export const TEST_API_URL = trimTrailingSlash(process.env.TEST_API_URL || DEFAULT_TEST_API_URL);
export const TEST_API_KEY = process.env.TEST_API_KEY || DEFAULT_TEST_API_KEY;
export const TEST_SESSION_ID = process.env.TEST_SESSION_ID || DEFAULT_TEST_SESSION_ID;
