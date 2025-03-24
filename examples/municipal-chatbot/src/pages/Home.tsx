import React from 'react';
import WeatherWidget from '../components/WeatherWidget';
import EventCalendar from '../components/EventCalendar';
import NewsSection from '../components/NewsSection';
import { ChevronRight, Building2, FileText, Car, Phone } from 'lucide-react';

const Home: React.FC = () => {
  return (
    <div>
      {/* Hero Section */}
      <div 
        className="bg-cover bg-center h-[500px] relative"
        style={{
          backgroundImage: 'url(https://images.unsplash.com/photo-1449824913935-59a10b8d2000?auto=format&fit=crop&q=80&w=1920)'
        }}
      >
        <div className="absolute inset-0 bg-black bg-opacity-50" />
        <div className="container mx-auto px-4 h-full relative">
          <div className="flex flex-col justify-center h-full text-white">
            <h1 className="text-4xl md:text-6xl font-bold mb-4">
              Welcome to Maple
            </h1>
            <p className="text-xl md:text-2xl mb-8 max-w-2xl">
              A vibrant community where innovation meets tradition. Discover city services, 
              upcoming events, and everything our beautiful city has to offer.
            </p>
            <div className="flex flex-wrap gap-4">
              <button className="bg-blue-600 text-white px-6 py-3 rounded-lg hover:bg-blue-700 transition">
                Report an Issue
              </button>
              <button className="bg-white text-blue-900 px-6 py-3 rounded-lg hover:bg-gray-100 transition">
                Pay Bills Online
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Quick Links Grid */}
      <div className="container mx-auto px-4 -mt-16 relative z-10">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {[
            { icon: Building2, title: 'Building Permits', link: '/services/permits' },
            { icon: FileText, title: 'Property Taxes', link: '/services/taxes' },
            { icon: Car, title: 'Parking', link: '/services/parking' },
            { icon: Phone, title: 'Contact Us', link: '/contact' },
          ].map((item, index) => (
            <a
              key={index}
              href={item.link}
              className="bg-white rounded-lg shadow-md p-6 flex items-center justify-between hover:bg-gray-50 transition"
            >
              <div className="flex items-center space-x-4">
                <item.icon className="w-6 h-6 text-blue-600" />
                <span className="font-semibold">{item.title}</span>
              </div>
              <ChevronRight className="w-5 h-5 text-gray-400" />
            </a>
          ))}
        </div>
      </div>

      {/* Main Content Grid */}
      <div className="container mx-auto px-4 mt-12">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Weather and Events Column */}
          <div className="lg:col-span-1 space-y-8">
            <WeatherWidget />
            <EventCalendar />
          </div>

          {/* News Column */}
          <div className="lg:col-span-2">
            <NewsSection />
          </div>
        </div>

        {/* Mayor's Message */}
        <div className="mt-12 bg-white rounded-lg shadow-md p-8">
          <div className="flex flex-col md:flex-row items-center md:items-start space-y-6 md:space-y-0 md:space-x-8">
            <img
              src="https://images.unsplash.com/photo-1560250097-0b93528c311a?auto=format&fit=crop&q=80&w=400"
              alt="Mayor James Wilson"
              className="w-48 h-48 rounded-full object-cover"
            />
            <div>
              <h2 className="text-2xl font-bold mb-4">Mayor's Welcome Message</h2>
              <p className="text-gray-600 mb-4">
                Welcome to our city's digital front door. As your mayor, I'm committed to making
                our community more accessible, transparent, and responsive to your needs. This
                website serves as your gateway to city services, community updates, and civic
                engagement opportunities.
              </p>
              <p className="text-gray-600 mb-6">
                Whether you're a longtime resident, new to our community, or planning to visit,
                I invite you to explore all that our city has to offer. Together, we're building
                a brighter future for all our residents.
              </p>
              <p className="font-semibold">James Wilson</p>
              <p className="text-gray-600">Mayor of Maple</p>
            </div>
          </div>
        </div>

        {/* Newsletter Signup */}
        <div className="mt-12 bg-blue-900 text-white rounded-lg shadow-md p-8">
          <div className="text-center max-w-2xl mx-auto">
            <h2 className="text-2xl font-bold mb-4">Stay Connected</h2>
            <p className="mb-6">
              Subscribe to our newsletter to receive updates about city news, events, and services.
            </p>
            <form className="flex flex-col md:flex-row gap-4">
              <input
                type="email"
                placeholder="Enter your email address"
                className="flex-1 px-4 py-2 rounded-lg text-gray-900"
              />
              <button
                type="submit"
                className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 transition"
              >
                Subscribe
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Home;