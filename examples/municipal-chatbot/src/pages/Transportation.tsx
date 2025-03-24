import React from 'react';
import { Bus, Train, Car, Bike, AlertTriangle, Clock, MapPin } from 'lucide-react';

const Transportation: React.FC = () => {
  const services = [
    {
      type: 'Bus',
      icon: Bus,
      routes: ['Route 1: Downtown Express', 'Route 2: University Line', 'Route 3: Airport Shuttle'],
      schedule: '5:00 AM - 12:00 AM',
      fare: '$2.50 per ride'
    },
    {
      type: 'Light Rail',
      icon: Train,
      routes: ['Blue Line: East-West', 'Green Line: North-South'],
      schedule: '4:30 AM - 1:00 AM',
      fare: '$3.00 per ride'
    }
  ];

  const alerts = [
    {
      route: 'Blue Line',
      message: 'Track maintenance between Central and Park stations. Expect 10-minute delays.',
      severity: 'warning'
    },
    {
      route: 'Route 2',
      message: 'Detour in effect due to road construction on University Ave.',
      severity: 'info'
    }
  ];

  return (
    <div className="min-h-screen bg-gray-50 py-12">
      <div className="container mx-auto px-4">
        <div className="max-w-6xl mx-auto">
          {/* Hero Section */}
          <div className="bg-gradient-to-r from-blue-900 to-blue-700 text-white rounded-lg p-8 mb-12">
            <h1 className="text-4xl font-bold mb-4">Public Transportation</h1>
            <p className="text-xl opacity-90">
              Connecting our community with reliable public transit options
            </p>
          </div>

          {/* Service Alerts */}
          <section className="bg-white rounded-lg shadow-md p-6 mb-12">
            <div className="flex items-center space-x-3 mb-6">
              <AlertTriangle className="w-6 h-6 text-yellow-500" />
              <h2 className="text-2xl font-bold">Service Alerts</h2>
            </div>
            <div className="space-y-4">
              {alerts.map((alert, index) => (
                <div
                  key={index}
                  className={`p-4 rounded-lg ${
                    alert.severity === 'warning' ? 'bg-yellow-50' : 'bg-blue-50'
                  }`}
                >
                  <h3 className="font-semibold">{alert.route}</h3>
                  <p className="text-gray-600">{alert.message}</p>
                </div>
              ))}
            </div>
          </section>

          {/* Transit Services */}
          <div className="space-y-8">
            {services.map(service => (
              <section key={service.type} className="bg-white rounded-lg shadow-md overflow-hidden">
                <div className="p-6 border-b border-gray-200">
                  <div className="flex items-center space-x-4">
                    <service.icon className="w-8 h-8 text-blue-600" />
                    <h2 className="text-2xl font-bold">{service.type}</h2>
                  </div>
                </div>
                <div className="p-6">
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                    <div>
                      <h3 className="font-semibold mb-2 flex items-center">
                        <MapPin className="w-5 h-5 mr-2 text-blue-600" />
                        Routes
                      </h3>
                      <ul className="space-y-2 text-gray-600">
                        {service.routes.map(route => (
                          <li key={route}>{route}</li>
                        ))}
                      </ul>
                    </div>
                    <div>
                      <h3 className="font-semibold mb-2 flex items-center">
                        <Clock className="w-5 h-5 mr-2 text-blue-600" />
                        Schedule
                      </h3>
                      <p className="text-gray-600">{service.schedule}</p>
                    </div>
                    <div>
                      <h3 className="font-semibold mb-2">Fare</h3>
                      <p className="text-gray-600">{service.fare}</p>
                    </div>
                  </div>
                </div>
              </section>
            ))}
          </div>

          {/* Quick Links */}
          <section className="mt-12 grid grid-cols-1 md:grid-cols-3 gap-6">
            <a href="/transportation/fares" className="bg-white p-6 rounded-lg shadow-md hover:shadow-lg transition">
              <Car className="w-6 h-6 text-blue-600 mb-3" />
              <h3 className="font-semibold mb-2">Fares & Passes</h3>
              <p className="text-gray-600">View fare options and purchase passes</p>
            </a>
            <a href="/transportation/bike" className="bg-white p-6 rounded-lg shadow-md hover:shadow-lg transition">
              <Bike className="w-6 h-6 text-blue-600 mb-3" />
              <h3 className="font-semibold mb-2">Bike Share</h3>
              <p className="text-gray-600">Learn about our city bike program</p>
            </a>
            <a href="/transportation/planner" className="bg-white p-6 rounded-lg shadow-md hover:shadow-lg transition">
              <MapPin className="w-6 h-6 text-blue-600 mb-3" />
              <h3 className="font-semibold mb-2">Trip Planner</h3>
              <p className="text-gray-600">Plan your journey across the city</p>
            </a>
          </section>
        </div>
      </div>
    </div>
  );
};

export default Transportation;