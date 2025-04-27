import React from 'react';
import { Car, CreditCard, MapPin, Clock, AlertTriangle } from 'lucide-react';

const Parking: React.FC = () => {
  const parkingLocations = [
    {
      name: 'Downtown Garage',
      address: '123 Main Street',
      spaces: '450 spaces',
      rates: {
        hourly: '$2/hour',
        daily: '$15/day',
        monthly: '$150/month'
      },
      features: ['24/7 Access', 'Security Cameras', 'EV Charging']
    },
    {
      name: 'City Center Lot',
      address: '456 Market Street',
      spaces: '200 spaces',
      rates: {
        hourly: '$1.50/hour',
        daily: '$12/day',
        monthly: '$120/month'
      },
      features: ['Well-lit', 'Pay Station', 'Handicap Accessible']
    }
  ];

  const permits = [
    {
      type: 'Residential',
      price: '$60/year',
      description: 'For residents in permit-required zones',
      requirements: ['Proof of residency', 'Vehicle registration', 'Valid ID']
    },
    {
      type: 'Business',
      price: '$100/month',
      description: 'For downtown business employees',
      requirements: ['Business verification', 'Employee ID', 'Vehicle registration']
    }
  ];

  return (
    <div className="min-h-screen bg-gray-50 py-12">
      <div className="container mx-auto px-4">
        <div className="max-w-6xl mx-auto">
          {/* Hero Section */}
          <div className="bg-gradient-to-r from-blue-900 to-blue-700 text-white rounded-lg p-8 mb-12">
            <h1 className="text-4xl font-bold mb-4">Parking Services</h1>
            <p className="text-xl opacity-90">
              Find parking, get permits, and manage citations
            </p>
          </div>

          {/* Quick Actions */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-12">
            <a href="/parking/pay" className="bg-white p-6 rounded-lg shadow-md hover:shadow-lg transition">
              <CreditCard className="w-6 h-6 text-blue-600 mb-3" />
              <h3 className="font-semibold mb-2">Pay for Parking</h3>
              <p className="text-gray-600">Pay for parking or citations online</p>
            </a>
            <a href="/parking/permits" className="bg-white p-6 rounded-lg shadow-md hover:shadow-lg transition">
              <Car className="w-6 h-6 text-blue-600 mb-3" />
              <h3 className="font-semibold mb-2">Get Permits</h3>
              <p className="text-gray-600">Apply for parking permits</p>
            </a>
            <a href="/parking/map" className="bg-white p-6 rounded-lg shadow-md hover:shadow-lg transition">
              <MapPin className="w-6 h-6 text-blue-600 mb-3" />
              <h3 className="font-semibold mb-2">Find Parking</h3>
              <p className="text-gray-600">View parking locations and availability</p>
            </a>
          </div>

          {/* Parking Locations */}
          <section className="bg-white rounded-lg shadow-md p-6 mb-12">
            <h2 className="text-2xl font-bold mb-6">Parking Locations</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {parkingLocations.map(location => (
                <div key={location.name} className="border rounded-lg p-4">
                  <h3 className="font-semibold text-lg mb-2">{location.name}</h3>
                  <p className="text-gray-600 mb-2">{location.address}</p>
                  <p className="text-gray-600 mb-4">Available: {location.spaces}</p>
                  
                  <div className="mb-4">
                    <h4 className="font-semibold mb-2">Rates:</h4>
                    <ul className="text-gray-600">
                      <li>Hourly: {location.rates.hourly}</li>
                      <li>Daily: {location.rates.daily}</li>
                      <li>Monthly: {location.rates.monthly}</li>
                    </ul>
                  </div>

                  <div>
                    <h4 className="font-semibold mb-2">Features:</h4>
                    <ul className="text-gray-600">
                      {location.features.map(feature => (
                        <li key={feature}>{feature}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* Parking Permits */}
          <section className="bg-white rounded-lg shadow-md p-6">
            <h2 className="text-2xl font-bold mb-6">Parking Permits</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {permits.map(permit => (
                <div key={permit.type} className="border rounded-lg p-4">
                  <h3 className="font-semibold text-lg mb-2">{permit.type} Permit</h3>
                  <p className="text-blue-600 font-semibold mb-2">{permit.price}</p>
                  <p className="text-gray-600 mb-4">{permit.description}</p>
                  
                  <div>
                    <h4 className="font-semibold mb-2">Requirements:</h4>
                    <ul className="list-disc list-inside text-gray-600">
                      {permit.requirements.map(req => (
                        <li key={req}>{req}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              ))}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
};

export default Parking;