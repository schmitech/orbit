import React, { useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import Home from './pages/Home';
import Services from './pages/Services';
import Government from './pages/Government';
import Residents from './pages/Residents';
import Business from './pages/Business';
import Parks from './pages/Parks';
import Transportation from './pages/Transportation';
import Elections from './pages/Elections';
import Budget from './pages/Budget';
import BusinessDirectory from './pages/BusinessDirectory';
import Parking from './pages/Parking';
import PropertyTaxes from './pages/PropertyTaxes';
import Contact from './pages/Contact';
import Employment from './pages/Employment';
import { useRef } from 'react';

declare global {
  interface Window {
    initChatbotWidget?: (config: {
      apiUrl: string,
      apiKey: string,
      containerSelector?: string,
      widgetConfig?: {
        header?: {
          title: string
        },
        welcome?: {
          title: string,
          description: string
        },
        suggestedQuestions?: Array<{
          text: string,
          query: string
        }>,
        theme?: {
          primary: string,
          secondary: string,
          background: string,
          text: {
            primary: string,
            secondary: string,
            inverse: string
          },
          input: {
            background: string,
            border: string
          },
          message: {
            user: string,
            assistant: string,
            userText: string
          },
          suggestedQuestions: {
            background: string,
            hoverBackground: string,
            text: string
          },
          iconColor: string
        },
        icon?: string
      }
    }) => void;
    ChatbotWidget?: {
      updateWidgetConfig: (config: any) => void;
    };
  }
}

function App() {
  // Use a ref to track if the widget has been initialized
  const widgetInitialized = useRef(false);

  useEffect(() => {
    // Initialize the widget only once when component mounts
    if (typeof window !== 'undefined' && window.initChatbotWidget && !widgetInitialized.current) {
      console.log('Initializing chatbot widget...');
      
      try {
        window.initChatbotWidget({
          apiUrl: import.meta.env.VITE_API_ENDPOINT || 'http://localhost:3000',
          apiKey: import.meta.env.VITE_API_KEY || 'api_jHqzRZygpKojK4bOGAlmjUb6bkVzreWu',
          widgetConfig: {
            header: {
              title: "Community Services Help Center"
            },
            welcome: {
              title: "Welcome to Our Community Services!",
              description: "I can help you with information about youth programs, senior services, adult education, family services, and more."
            },
            suggestedQuestions: [
              {
                text: "What youth programs are available?",
                query: "Tell me about the youth programs"
              },
              {
                text: "Senior services information",
                query: "What services are available for seniors?"
              },
              {
                text: "Adult education courses",
                query: "What adult education courses do you offer?"
              }
            ],
            theme: {
              primary: '#2C3E50',
              secondary: '#f97316',
              background: '#ffffff',
              text: {
                primary: '#1a1a1a',
                secondary: '#666666',
                inverse: '#ffffff'
              },
              input: {
                background: '#f9fafb',
                border: '#e5e7eb'
              },
              message: {
                user: '#2C3E50',
                assistant: '#ffffff',
                userText: '#ffffff'
              },
              suggestedQuestions: {
                background: '#fff7ed',
                hoverBackground: '#ffedd5',
                text: '#2C3E50'
              },
              iconColor: '#f97316'
            },
            icon: "message-square"
          }
        });
        widgetInitialized.current = true;
      } catch (error) {
        console.error('Failed to initialize chatbot widget:', error);
      }
    }
  }, []); // Empty dependency array ensures this runs only once
  
  return (
    <Router>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Home />} />
          <Route path="/services" element={<Services />} />
          <Route path="/government" element={<Government />} />
          <Route path="/residents" element={<Residents />} />
          <Route path="/business" element={<Business />} />
          <Route path="/parks" element={<Parks />} />
          <Route path="/transportation" element={<Transportation />} />
          <Route path="/government/elections" element={<Elections />} />
          <Route path="/government/budget" element={<Budget />} />
          <Route path="/business/directory" element={<BusinessDirectory />} />
          <Route path="/services/parking" element={<Parking />} />
          <Route path="/services/property-taxes" element={<PropertyTaxes />} />
          <Route path="/contact" element={<Contact />} />
          <Route path="/jobs" element={<Employment />} />
        </Route>
      </Routes>
    </Router>
  );
}

export default App;