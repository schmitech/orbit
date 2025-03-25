// Get the API mode from environment variable
const USE_LOCAL_API = import.meta.env.VITE_USE_LOCAL_API === 'true';
console.log(`🔄 API Configuration: Using ${USE_LOCAL_API ? 'LOCAL DEVELOPMENT' : 'NPM PACKAGE'} version`);
console.log(`🔍 ${USE_LOCAL_API ? 'Using Vite-resolved local API module' : 'Using @schmitech/chatbot-api from npm'}`);

// Import from the appropriate source based on the flag
import * as npmApi from '@schmitech/chatbot-api';
// We need to use dynamic imports for the local version to avoid issues with mjs imports
// This is handled at runtime

// Type definition for StreamResponse
interface StreamResponse {
  text?: string;
  content?: string;
  done?: boolean;
  type?: string;
}

// Function to dynamically import the local module
async function getLocalApi() {
  try {
    // Try the Vite alias first
    return await import('api-local');
  } catch (e) {
    console.error('Failed to load via alias, trying direct import...');
    // Use direct import from the API module
    // @ts-ignore
    return await import('../../../../api/dist/api.mjs');
  }
}

// Export the appropriate API
export async function* streamChat(message: string, voiceEnabled: boolean): AsyncGenerator<StreamResponse> {
  if (USE_LOCAL_API) {
    try {
      console.log('🚀 Attempting to use LOCAL API version for streamChat...');
      const localApiModule = await getLocalApi();
      console.log('✅ Successfully loaded LOCAL API module!');
      const generator = localApiModule.streamChat(message, voiceEnabled);
      for await (const chunk of generator) {
        yield chunk;
      }
    } catch (error) {
      console.error('❌ Failed to load local API:', error);
      console.log('⚠️ Falling back to NPM package version...');
      const generator = npmApi.streamChat(message, voiceEnabled);
      for await (const chunk of generator) {
        yield chunk;
      }
    }
  } else {
    console.log('🚀 Using NPM package version for streamChat');
    const generator = npmApi.streamChat(message, voiceEnabled);
    for await (const chunk of generator) {
      yield chunk;
    }
  }
};

export const configureApi = (apiUrl: string) => {
  if (USE_LOCAL_API) {
    try {
      console.log('🔧 Attempting to configure LOCAL API with endpoint:', apiUrl);
      // We need to immediately invoke this async function
      (async () => {
        const localApiModule = await getLocalApi();
        localApiModule.configureApi(apiUrl);
        console.log('✅ Successfully configured LOCAL API module!');
      })().catch(error => {
        console.error('❌ Failed to configure local API:', error);
        console.log('⚠️ Falling back to configuring NPM package version...');
        npmApi.configureApi(apiUrl);
      });
    } catch (error) {
      console.error('❌ Failed to load local API:', error);
      console.log('⚠️ Falling back to configuring NPM package version...');
      npmApi.configureApi(apiUrl);
    }
  } else {
    console.log('🔧 Configuring NPM package version with endpoint:', apiUrl);
    npmApi.configureApi(apiUrl);
  }
}; 