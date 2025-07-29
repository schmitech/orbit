# Chatbot Widget React Test

This is a minimal React application to test the ORBIT chatbot widget.

## Setup

1. Install dependencies:
```bash
npm install
```

2. Configure environment variables:
   - Copy `.env.example` to `.env`
   - Update the values in `.env`:
     - `VITE_API_URL`: Your chatbot API endpoint URL
     - `VITE_API_KEY`: Your API authentication key

3. Start the development server:
```bash
npm run dev
```

4. Open http://localhost:3001 in your browser

## Environment Variables

The application uses the following environment variables (prefixed with `VITE_` for Vite):

- `VITE_API_URL`: The URL of your chatbot API server (default: http://localhost:3000)
- `VITE_API_KEY`: Your API authentication key (default: test-api-key)

These values are loaded at build time and can be configured in the `.env` file.