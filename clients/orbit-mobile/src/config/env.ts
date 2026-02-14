export interface AppConfig {
  orbitHost: string;
  apiKey: string;
  enableAudioOutput: boolean;
  appTitle: string;
}

export function getConfig(): AppConfig {
  const host = process.env.EXPO_PUBLIC_ORBIT_HOST;
  const key = process.env.EXPO_PUBLIC_ORBIT_API_KEY;

  if (!host) {
    throw new Error(
      'EXPO_PUBLIC_ORBIT_HOST is not set. Create a .env file with your ORBIT server URL.'
    );
  }

  if (!key) {
    throw new Error(
      'EXPO_PUBLIC_ORBIT_API_KEY is not set. Create a .env file with your API key.'
    );
  }

  const audioOutput = process.env.EXPO_PUBLIC_ENABLE_AUDIO_OUTPUT;
  const appTitle = process.env.EXPO_PUBLIC_APP_TITLE || 'ORBIT Chat';

  return {
    orbitHost: host.endsWith('/') ? host.slice(0, -1) : host,
    apiKey: key,
    enableAudioOutput: audioOutput === 'true',
    appTitle,
  };
}
