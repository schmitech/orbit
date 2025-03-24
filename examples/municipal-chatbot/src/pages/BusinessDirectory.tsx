import React from 'react';
import { Building2, Search, MapPin, Phone, Globe, Filter } from 'lucide-react';

const BusinessDirectory: React.FC = () => {
  const businesses = [
    {
      name: 'Tech Innovation Hub',
      category: 'Technology',
      address: '789 Innovation Drive',
      phone: '(555) 234-5678',
      website: 'www.techhub.com',
      description: 'Leading technology research and development center',
      hours: 'Mon-Fri: 9:00 AM - 6:00 PM'
    },
    {
      name: 'Green Earth Market',
      category: 'Retail',
      address: '456 Eco Street',
      phone: '(555) 876-5432',
      website: 'www.greenearthmarket.com',
      description: 'Organic grocery store and café',
      hours: 'Daily: 7:00 AM - 9:00 PM'
    },
    {
      name: 'Metropolitan Bank',
      category: 'Financial Services',
      address: '321 Commerce Avenue',
      phone: '(555) 345-6789',
      website: 'www.metrobank.com',
      description: 'Full-service banking and financial solutions',
      hours: 'Mon-Fri: 8:30 AM - 5:00 PM'
    }
  ];

  const categories = [
    'All Categories',
    'Technology',
    'Retail',
    'Financial Services',
    'Healthcare',
    'Restaurants',
    'Professional Services'
  ];

  return (
    <div className="min-h-screen bg-gray-50 py-12">
      <div className="container mx-auto px-4">
        <div className="max-w-6xl mx-auto">
          {/* Hero Section */}
          <div className="bg-gradient-to-r from-blue-900 to-blue-700 text-white rounded-lg p-8 mb-12">
            <h1 className="text-4xl font-bold mb-4">Business Directory</h1>
            <p className="text-xl opacity-90">
              Discover local businesses in our community
            </p>
          </div>

          {/* Search and Filter */}
          <div className="bg-white rounded-lg shadow-md p-6 mb-8">
            <div className="flex flex-col md:flex-row gap-4">
              <div className="flex-1 relative">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400" />
                <input
                  type="text"
                  placeholder="Search businesses..."
                  className="w-full pl-10 pr-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
              </div>
              <div className="md:w-64">
                <select className="w-full p-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500">
                  {categories.map(category => (
                    <option key={category}>{category}</option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          {/* Business Listings */}
          <div className="space-y-6">
            {businesses.map(business => (
              <div key={business.name} className="bg-white rounded-lg shadow-md p-6">
                <div className="flex flex-col md:flex-row md:items-start md:justify-between">
                  <div className="flex-1">
                    <h2 className="text-xl font-bold mb-2">{business.name}</h2>
                    <p className="text-gray-600 mb-4">{business.description}</p>
                    
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div className="flex items-start space-x-2">
                        <MapPin className="w-5 h-5 text-blue-600 flex-shrink-0" />
                        <span className="text-gray-600">{business.address}</span>
                      </div>
                      <div className="flex items-start space-x-2">
                        <Phone className="w-5 h-5 text-blue-600 flex-shrink-0" />
                        <span className="text-gray-600">{business.phone}</span>
                      </div>
                      <div className="flex items-start space-x-2">
                        <Globe className="w-5 h-5 text-blue-600 flex-shrink-0" />
                        <a href={`https://${business.website}`} className="text-blue-600 hover:underline">
                          {business.website}
                        </a>
                      </div>
                      <div className="flex items-start space-x-2">
                        <Clock className="w-5 h-5 text-blue-600 flex-shrink-0" />
                        <span className="text-gray-600">{business.hours}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Add Business CTA */}
          <div className="mt-12 bg-blue-50 rounded-lg p-8 text-center">
            <h2 className="text-2xl font-bold mb-4">Own a Business?</h2>
            <p className="text-gray-600 mb-6">
              Add your business to our directory and connect with the community.
            </p>
            <button className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 transition">
              Add Your Business
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default BusinessDirectory;