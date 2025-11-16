export const configureApi = () => {
  throw new Error('Local API stub loaded while VITE_USE_LOCAL_API=false.');
};

export const streamChat = async function* () {
  throw new Error('Local API stub loaded while VITE_USE_LOCAL_API=false.');
};

export class ApiClient {
  constructor() {
    throw new Error('Local API stub loaded while VITE_USE_LOCAL_API=false.');
  }
}
