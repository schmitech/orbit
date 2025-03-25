import React from 'react';
import { ChatbotWidget } from './components/ChatbotWidget';
import { initChatbot } from './lib/initChatbot';
import { Sparkles, Users, Shield, Zap, Globe, Code, MessageSquare } from 'lucide-react';

// Example configuration
const config = {
  theme: {
    primaryColor: '#0066cc',
    size: 'medium' as const,
    font: 'Inter, sans-serif',
  },
  messages: {
    greeting: 'Hi there! 👋 How can I assist you today?',
    title: 'Customer Support',
  },
  position: {
    bottom: 20,
    right: 20,
  },
  dimensions: {
    width: 350,
    height: 500,
  },
  api: {
    endpoint: 'http://localhost:3001',
  },
};

const features = [
  {
    icon: <Sparkles className="w-6 h-6" />,
    title: 'Customizable Theme',
    description: 'Fully customizable theme with support for custom colors, sizes, and fonts.',
  },
  {
    icon: <Users className="w-6 h-6" />,
    title: 'User-Friendly',
    description: 'Intuitive interface designed for the best user experience.',
  },
  {
    icon: <Shield className="w-6 h-6" />,
    title: 'Secure',
    description: 'Built with security in mind, ensuring your conversations are protected.',
  },
  {
    icon: <Zap className="w-6 h-6" />,
    title: 'Fast & Responsive',
    description: 'Lightning-fast responses and smooth animations.',
  },
  {
    icon: <Globe className="w-6 h-6" />,
    title: 'Cross-Platform',
    description: 'Works seamlessly across all devices and platforms.',
  },
  {
    icon: <Code className="w-6 h-6" />,
    title: 'Developer Friendly',
    description: 'Easy to integrate with comprehensive documentation.',
  },
];

function App() {
  React.useEffect(() => {
    initChatbot(config);
  }, []);

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Hero Section */}
      <div className="bg-gradient-to-b from-blue-50 to-white py-20">
        <div className="container mx-auto px-4">
          <h1 className="text-5xl font-bold text-center mb-6">
            Welcome to Our Chat Platform
          </h1>
          <p className="text-xl text-gray-600 text-center max-w-2xl mx-auto">
            Experience the next generation of customer support with our intelligent
            chatbot solution. Try it out by clicking the chat button in the bottom right!
          </p>
        </div>
      </div>

      {/* Features Grid */}
      <div className="py-20 bg-white">
        <div className="container mx-auto px-4">
          <h2 className="text-3xl font-bold text-center mb-12">
            Powerful Features for Your Business
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
            {features.map((feature, index) => (
              <div
                key={index}
                className="p-6 bg-white rounded-xl shadow-md hover:shadow-lg transition-shadow"
              >
                <div className="text-blue-600 mb-4">{feature.icon}</div>
                <h3 className="text-xl font-semibold mb-2">{feature.title}</h3>
                <p className="text-gray-600">{feature.description}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Statistics Section */}
      <div className="py-20 bg-blue-50">
        <div className="container mx-auto px-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8 text-center">
            <div className="p-6">
              <div className="text-4xl font-bold text-blue-600 mb-2">99.9%</div>
              <div className="text-gray-600">Uptime Guarantee</div>
            </div>
            <div className="p-6">
              <div className="text-4xl font-bold text-blue-600 mb-2">24/7</div>
              <div className="text-gray-600">Support Available</div>
            </div>
            <div className="p-6">
              <div className="text-4xl font-bold text-blue-600 mb-2">1M+</div>
              <div className="text-gray-600">Happy Users</div>
            </div>
          </div>
        </div>
      </div>

      {/* Testimonials */}
      <div className="py-20 bg-white">
        <div className="container mx-auto px-4">
          <h2 className="text-3xl font-bold text-center mb-12">
            What Our Customers Say
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="p-6 bg-white rounded-xl shadow-md hover:shadow-lg transition-shadow"
              >
                <div className="flex items-center mb-4">
                  <img
                    src={`https://i.pravatar.cc/40?img=${i}`}
                    alt={`User ${i}`}
                    className="rounded-full"
                  />
                  <div className="ml-4">
                    <div className="font-semibold">John Doe</div>
                    <div className="text-gray-500 text-sm">CEO at TechCorp</div>
                  </div>
                </div>
                <p className="text-gray-600">
                  "This chatbot has transformed how we handle customer support.
                  It's intuitive, fast, and our customers love it!"
                </p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* CTA Section */}
      <div className="py-20 bg-blue-600">
        <div className="container mx-auto px-4 text-center">
          <h2 className="text-3xl font-bold text-white mb-6">
            Ready to Transform Your Customer Support?
          </h2>
          <p className="text-xl text-blue-100 mb-8 max-w-2xl mx-auto">
            Join thousands of businesses that have already improved their customer
            experience with our chatbot solution.
          </p>
          <button className="bg-white text-blue-600 px-8 py-3 rounded-lg font-semibold hover:bg-blue-50 transition-colors">
            Get Started Today
          </button>
        </div>
      </div>

      <ChatbotWidget />
    </div>
  );
}

export default App;