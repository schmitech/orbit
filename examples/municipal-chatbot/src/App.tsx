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

declare global {
  interface Window {
    initChatbotWidget?: (config: {
      apiUrl: string,
      containerSelector?: string,
      widgetConfig?: {
        header?: {
          title: string,
          color?: string
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
  // Initialize the widget when component mounts
  useEffect(() => {
    if (typeof window !== 'undefined' && window.initChatbotWidget) {
      setTimeout(() => {
        window.initChatbotWidget!({
          apiUrl: import.meta.env.VITE_API_ENDPOINT,
          widgetConfig: {
            header: {
              title: "City of Maple Services",
              color: '#ffffff'
            },
            welcome: {
              title: "Welcome to the City of Maple!",
              description: "Explore our services, get information on parking, taxes, and more."
            },
            suggestedQuestions: [
              {
                text: "How can I pay my property taxes?",
                query: "Tell me about property tax payment"
              },
              {
                text: "Parking information",
                query: "Where can I find parking information?"
              },
              {
                text: "Public transportation options",
                query: "Show me public transportation options"
              }
            ],
            theme: {
              primary: '#312e81',
        secondary: '#8b5cf6',
        background: '#ffffff',
        text: {
            primary: '#1e293b',
            secondary: '#666666',
            inverse: '#ffffff'
        },
        input: {
            background: '#f9fafb',
            border: '#e5e7eb'
        },
        message: {
            user: '#312e81',
            assistant: '#eef2ff',
            userText: '#ffffff'
        },
        suggestedQuestions: {
            background: '#eef2ff',
            hoverBackground: '#f1f3f8',
            text: '#312e81'
        },
        iconColor: '#8b5cf6'
            },
            icon: "message-square"
          }
        });
      }, 500); // Small delay to ensure DOM and scripts are fully loaded
    }
  }, []);
  
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