import { Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import Home from './pages/Home';
import About from './pages/About';
import Contact from './pages/Contact';
import Events from './pages/Events';
import YouthPrograms from './pages/programs/YouthPrograms.tsx';
import SeniorServices from './pages/programs/SeniorServices.tsx';
import AdultEducation from './pages/programs/AdultEducation.tsx';
import FamilyServices from './pages/programs/FamilyServices.tsx';
import FinancialLiteracy from './pages/programs/FinancialLiteracy.tsx';
import CommunityOutreach from './pages/programs/CommunityOutreach.tsx';
import { useEffect, useRef } from 'react';

// Add type definitions for window properties
declare global {
  interface Window {
    initChatbotWidget?: (config: {
      apiUrl: string,
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
                text: "How can I volunteer for your disaster relief efforts?",
                query: "How can I volunteer for your disaster relief efforts?"
              },
              {
                text: "What youth leadership opportunities do you offer?",
                query: "What youth leadership opportunities do you offer?"
              },
              {
                text: "How can I access your mobile food pantry?",
                query: "How can I access your mobile food pantry?"
              },
              {
                text: "What adult education programs are available?",
                query: "What adult education programs are available?"
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
    <Layout>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/about" element={<About />} />
        <Route path="/contact" element={<Contact />} />
        <Route path="/events" element={<Events />} />
        <Route path="/programs/youth" element={<YouthPrograms />} />
        <Route path="/programs/seniors" element={<SeniorServices />} />
        <Route path="/programs/adult-education" element={<AdultEducation />} />
        <Route path="/programs/family" element={<FamilyServices />} />
        <Route path="/programs/financial" element={<FinancialLiteracy />} />
        <Route path="/programs/outreach" element={<CommunityOutreach />} />
      </Routes>
    </Layout>
  );
}

export default App;