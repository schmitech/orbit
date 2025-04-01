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
import { useEffect } from 'react';

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
  }
}

function App() {
  useEffect(() => {
    // Initialize the widget when component mounts
    if (typeof window !== 'undefined' && window.initChatbotWidget) {
      console.log('Initializing chatbot widget...');
      setTimeout(() => {
        try {
          window.initChatbotWidget!({
            apiUrl: import.meta.env.VITE_API_ENDPOINT,
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
          console.log('Chatbot widget initialized successfully');
        } catch (error) {
          console.error('Failed to initialize chatbot widget:', error);
        }
      }, 1000); // Increased delay to 1 second
    } else {
      console.error('Chatbot widget initialization function not found');
    }
  }, []);

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