import React from 'react';
import { Building2, TrendingUp, FileText, Store, Briefcase, Handshake as HandShake, Globe } from 'lucide-react';

const Business: React.FC = () => {
  const resources = [
    {
      id: 'starting',
      title: 'Starting a Business',
      icon: Store,
      content: `Launch your business with confidence using our comprehensive startup guide. Our Economic Development team provides:
• Business plan review
• Location selection assistance
• Permit and license guidance
• Connection to local resources`,
      stats: [
        { label: 'New Businesses (2023)', value: '450+' },
        { label: 'Average Processing Time', value: '15 days' },
        { label: 'Success Rate', value: '85%' }
      ]
    },
    {
      id: 'incentives',
      title: 'Business Incentives',
      icon: TrendingUp,
      content: `Take advantage of our business incentive programs designed to help your business thrive:
• Tax increment financing
• Job creation credits
• Facade improvement grants
• Small business loans`,
      stats: [
        { label: 'Available Funding', value: '$5M' },
        { label: 'Businesses Supported', value: '200+' },
        { label: 'Jobs Created', value: '1,200' }
      ]
    }
  ];

  const opportunities = [
    {
      title: 'Downtown Development',
      description: 'Prime retail and office space available in our revitalized downtown district',
      image: 'https://images.unsplash.com/photo-1449824913935-59a10b8d2000?auto=format&fit=crop&q=80&w=1200'
    },
    {
      title: 'Innovation District',
      description: 'Join our growing tech and research hub with state-of-the-art facilities',
      image: 'https://images.unsplash.com/photo-1497366216548-37526070297c?auto=format&fit=crop&q=80&w=1200'
    }
  ];

  return (
    <div className="min-h-screen bg-gray-50 py-12">
      <div className="container mx-auto px-4">
        <div className="max-w-6xl mx-auto">
          {/* Hero Section */}
          <div className="bg-gradient-to-r from-blue-900 to-blue-700 text-white rounded-lg p-8 mb-12">
            <h1 className="text-4xl font-bold mb-4">Business Hub</h1>
            <p className="text-xl opacity-90">
              Resources and support for businesses of all sizes
            </p>
          </div>

          {/* Featured Opportunities */}
          <section className="mb-12">
            <h2 className="text-2xl font-bold mb-6">Featured Opportunities</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {opportunities.map(opportunity => (
                <div key={opportunity.title} className="relative overflow-hidden rounded-lg group">
                  <img
                    src={opportunity.image}
                    alt={opportunity.title}
                    className="w-full h-64 object-cover"
                  />
                  <div className="absolute inset-0 bg-gradient-to-t from-black to-transparent opacity-70" />
                  <div className="absolute bottom-0 left-0 right-0 p-6">
                    <h3 className="text-xl font-bold text-white mb-2">{opportunity.title}</h3>
                    <p className="text-white opacity-90">{opportunity.description}</p>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* Business Resources */}
          <div className="space-y-8">
            {resources.map(resource => (
              <section key={resource.id} className="bg-white rounded-lg shadow-md overflow-hidden">
                <div className="p-6 border-b border-gray-200">
                  <div className="flex items-center space-x-4">
                    <resource.icon className="w-8 h-8 text-blue-600" />
                    <h2 className="text-2xl font-bold">{resource.title}</h2>
                  </div>
                </div>
                <div className="p-6">
                  <p className="text-gray-700 whitespace-pre-wrap mb-6">{resource.content}</p>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    {resource.stats.map(stat => (
                      <div key={stat.label} className="bg-blue-50 p-4 rounded-lg">
                        <p className="text-sm text-gray-600">{stat.label}</p>
                        <p className="text-2xl font-bold text-blue-600">{stat.value}</p>
                      </div>
                    ))}
                  </div>
                </div>
              </section>
            ))}
          </div>

          {/* Quick Links */}
          <section className="mt-12 grid grid-cols-1 md:grid-cols-3 gap-6">
            <a href="/business/directory" className="bg-white p-6 rounded-lg shadow-md hover:shadow-lg transition">
              <Building2 className="w-6 h-6 text-blue-600 mb-3" />
              <h3 className="font-semibold mb-2">Business Directory</h3>
              <p className="text-gray-600">Connect with local businesses</p>
            </a>
            <a href="/business/events" className="bg-white p-6 rounded-lg shadow-md hover:shadow-lg transition">
              <HandShake className="w-6 h-6 text-blue-600 mb-3" />
              <h3 className="font-semibold mb-2">Networking Events</h3>
              <p className="text-gray-600">Join business community events</p>
            </a>
            <a href="/business/international" className="bg-white p-6 rounded-lg shadow-md hover:shadow-lg transition">
              <Globe className="w-6 h-6 text-blue-600 mb-3" />
              <h3 className="font-semibold mb-2">International Trade</h3>
              <p className="text-gray-600">Global business opportunities</p>
            </a>
          </section>
        </div>
      </div>
    </div>
  );
};

export default Business;