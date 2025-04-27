import React from 'react';
import { Car, Book, Map, Bell, ChevronFirst as FirstAid, Shield, Construction } from 'lucide-react';

const Residents: React.FC = () => {
  const resources = [
    {
      id: 'parking',
      title: 'Parking & Transportation',
      icon: Car,
      content: `Manage your parking permits, find parking locations, and stay informed about road closures. Our smart parking system helps you find available spots in real-time.

Current Permit Types:
• Residential Parking Permit: $60/year
• Visitor Parking Pass: $5/day
• Downtown Business Permit: $100/month`,
      actions: [
        { label: 'Apply for Permit', link: '/parking/permits' },
        { label: 'View Parking Map', link: '/parking/map' },
        { label: 'Pay Parking Ticket', link: '/parking/tickets' }
      ]
    },
    {
      id: 'libraries',
      title: 'Library Services',
      icon: Book,
      content: `Access our network of 5 public libraries with over 500,000 items in circulation. Your library card gives you access to:
• Digital resources and e-books
• Meeting room reservations
• Educational programs
• Computer and internet access`,
      actions: [
        { label: 'Search Catalog', link: '/library/catalog' },
        { label: 'Get Library Card', link: '/library/card' },
        { label: 'Reserve Room', link: '/library/rooms' }
      ]
    }
  ];

  const alerts = [
    {
      type: 'construction',
      title: 'Road Construction',
      description: 'Main Street renovation between 5th and 7th Avenue. Expected completion: April 2024',
      date: '2024-03-15'
    },
    {
      type: 'event',
      title: 'Community Festival',
      description: 'Annual Spring Festival at Central Park. Free admission, family activities, and local food vendors.',
      date: '2024-04-01'
    }
  ];

  return (
    <div className="min-h-screen bg-gray-50 py-12">
      <div className="container mx-auto px-4">
        <div className="max-w-6xl mx-auto">
          {/* Hero Section */}
          <div className="bg-gradient-to-r from-blue-900 to-blue-700 text-white rounded-lg p-8 mb-12">
            <h1 className="text-4xl font-bold mb-4">Resident Resources</h1>
            <p className="text-xl opacity-90">
              Everything you need to live, work, and thrive in our community
            </p>
          </div>

          {/* Community Alerts */}
          <section className="bg-white rounded-lg shadow-md p-6 mb-12">
            <div className="flex items-center space-x-3 mb-6">
              <Bell className="w-6 h-6 text-blue-600" />
              <h2 className="text-2xl font-bold">Community Updates</h2>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {alerts.map(alert => (
                <div key={alert.type} className="border rounded-lg p-4">
                  <div className="flex items-start space-x-3">
                    {alert.type === 'construction' ? (
                      <Construction className="w-5 h-5 text-orange-500" />
                    ) : (
                      <Bell className="w-5 h-5 text-blue-500" />
                    )}
                    <div>
                      <h3 className="font-semibold">{alert.title}</h3>
                      <p className="text-gray-600 text-sm mb-2">{alert.description}</p>
                      <p className="text-sm text-gray-500">
                        Posted: {new Date(alert.date).toLocaleDateString()}
                      </p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* Resource Sections */}
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
                  <div className="flex flex-wrap gap-4">
                    {resource.actions.map(action => (
                      <a
                        key={action.label}
                        href={action.link}
                        className="bg-blue-50 text-blue-700 px-4 py-2 rounded-lg hover:bg-blue-100 transition"
                      >
                        {action.label}
                      </a>
                    ))}
                  </div>
                </div>
              </section>
            ))}
          </div>

          {/* Emergency Services */}
          <section className="mt-12 grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="bg-red-50 p-6 rounded-lg">
              <div className="flex items-center space-x-3 mb-4">
                <FirstAid className="w-6 h-6 text-red-600" />
                <h2 className="text-xl font-bold">Emergency Services</h2>
              </div>
              <p className="text-gray-700 mb-4">
                For emergencies, dial 911. Our emergency services are available 24/7.
              </p>
              <div className="space-y-2">
                <p className="flex items-center space-x-2">
                  <span className="font-semibold">Police (non-emergency):</span>
                  <span>(555) 123-4567</span>
                </p>
                <p className="flex items-center space-x-2">
                  <span className="font-semibold">Fire Department:</span>
                  <span>(555) 123-4568</span>
                </p>
              </div>
            </div>

            <div className="bg-blue-50 p-6 rounded-lg">
              <div className="flex items-center space-x-3 mb-4">
                <Shield className="w-6 h-6 text-blue-600" />
                <h2 className="text-xl font-bold">Public Safety</h2>
              </div>
              <p className="text-gray-700 mb-4">
                Stay informed about public safety initiatives and community programs.
              </p>
              <div className="space-y-2">
                <a href="/safety/crime-prevention" className="text-blue-600 hover:underline block">
                  Crime Prevention Tips
                </a>
                <a href="/safety/neighborhood-watch" className="text-blue-600 hover:underline block">
                  Neighborhood Watch Program
                </a>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
};

export default Residents;