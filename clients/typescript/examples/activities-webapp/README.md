# Municipal Programs Chatbot

A web application for browsing Recreation Programs programs with an integrated chatbot assistant.

## Features

- Browse and filter recreation activities
- Chat with an AI assistant to get information about programs
- Real-time streaming responses from the chatbot

## Setup

1. Install dependencies:
   ```bash
   npm install
   ```

2. Generate mock data (optional, if you don't already have data):
   ```bash
   npm run generate-mock-data 50
   ```

3. Build the api interface:
```bash
cd ../../api
npm install
npm test
npm run build
```

4. Start the frontend:
   ```bash
   npm run dev
   ```

5. Open your browser and navigate to the URL shown in the terminal (typically http://localhost:5173)

## How It Works

The application consists of two main parts:

1. **Frontend**: A React application that displays recreation activities and includes a chat widget for interacting with the AI assistant.

2. **API**: The application connects to an external server running on port 3000 that handles chat requests and streams responses back to the frontend.

The chat functionality uses a streaming API to provide real-time responses as they are generated, creating a more interactive user experience.

## Technologies Used

- React
- TypeScript
- Tailwind CSS
- Zustand (for state management)

## Customization

### Tailwind Theme

The application uses a custom Tailwind theme defined in `tailwind.config.js`. You can modify the colors, fonts, and other design tokens to match your municipality's branding.

### Mock Data

The application uses mock data for demonstration purposes. In a production environment, you would replace the mock data with API calls to your backend services. The mock data is loaded from `data/activities.json` and processed in `src/data/activityData.ts`.

#### Generating Mock Data

You can generate mock activity data and save it to a JSON file using the provided script:

```bash
# Generate the default number of activities (120)
npm run generate-mock-data

# Generate a specific number of activities (e.g., 50)
npm run generate-mock-data -- 50
```

This will create a `data/activities.json` file containing the generated mock activities, which can be used for testing or development purposes.

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the Apache 2.0 License - see the LICENSE file on parent project directory for details.

## Acknowledgments

- Images from [Unsplash](https://unsplash.com/)
- Icons from [Lucide](https://lucide.dev/)