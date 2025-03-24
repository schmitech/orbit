import React from 'react';
import { Trees as Tree, MapPin, Calendar, Users } from 'lucide-react';

const Parks: React.FC = () => {
  const parks = [
    {
      name: 'Central Park',
      description: 'Our largest urban park featuring walking trails, sports facilities, and a botanical garden.',
      amenities: ['Playground', 'Tennis Courts', 'Picnic Areas', 'Botanical Garden'],
      hours: '6:00 AM - 10:00 PM',
      image: 'https://images.unsplash.com/photo-1568515387631-8b650bbcdb90?auto=format&fit=crop&q=80&w=1200'
    },
    {
      name: 'Riverside Park',
      description: 'Scenic waterfront park with cycling paths and outdoor performance spaces.',
      amenities: ['Bike Trail', 'Amphitheater', 'Fishing Dock', 'Exercise Stations'],
      hours: '5:00 AM - 11:00 PM',
      image: 'https://images.unsplash.com/photo-1534246357846-40b04ef57fb2?auto=format&fit=crop&q=80&w=1200'
    }
  ];

  return (
    <div className="min-h-screen bg-gray-50 py-12">
      <div className="container mx-auto px-4">
        <div className="max-w-6xl mx-auto">
          {/* Hero Section */}
          <div className="bg-gradient-to-r from-green-800 to-green-600 text-white rounded-lg p-8 mb-12">
            <h1 className="text-4xl font-bold mb-4">Parks & Recreation</h1>
            <p className="text-xl opacity-90">
              Discover our city's beautiful parks and recreational facilities
            </p>
          </div>

          {/* Parks List */}
          <div className="space-y-8">
            {parks.map(park => (
              <div key={park.name} className="bg-white rounded-lg shadow-md overflow-hidden">
                <div className="md:flex">
                  <div className="md:w-1/3">
                    <img
                      src={park.image}
                      alt={park.name}
                      className="h-full w-full object-cover"
                    />
                  </div>
                  <div className="p-6 md:w-2/3">
                    <h2 className="text-2xl font-bold mb-4">{park.name}</h2>
                    <p className="text-gray-600 mb-4">{park.description}</p>
                    
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <h3 className="font-semibold mb-2 flex items-center">
                          <Tree className="w-5 h-5 mr-2 text-green-600" />
                          Amenities
                        </h3>
                        <ul className="list-disc list-inside text-gray-600">
                          {park.amenities.map(amenity => (
                            <li key={amenity}>{amenity}</li>
                          ))}
                        </ul>
                      </div>
                      <div>
                        <h3 className="font-semibold mb-2 flex items-center">
                          <Calendar className="w-5 h-5 mr-2 text-green-600" />
                          Hours
                        </h3>
                        <p className="text-gray-600">{park.hours}</p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Quick Links */}
          <div className="mt-12 grid grid-cols-1 md:grid-cols-3 gap-6">
            <a href="/parks/events" className="bg-white p-6 rounded-lg shadow-md hover:shadow-lg transition">
              <Calendar className="w-6 h-6 text-green-600 mb-3" />
              <h3 className="font-semibold mb-2">Park Events</h3>
              <p className="text-gray-600">View upcoming activities and programs</p>
            </a>
            <a href="/parks/facilities" className="bg-white p-6 rounded-lg shadow-md hover:shadow-lg transition">
              <MapPin className="w-6 h-6 text-green-600 mb-3" />
              <h3 className="font-semibold mb-2">Facility Rentals</h3>
              <p className="text-gray-600">Reserve spaces for your events</p>
            </a>
            <a href="/parks/programs" className="bg-white p-6 rounded-lg shadow-md hover:shadow-lg transition">
              <Users className="w-6 h-6 text-green-600 mb-3" />
              <h3 className="font-semibold mb-2">Recreation Programs</h3>
              <p className="text-gray-600">Register for classes and activities</p>
            </a>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Parks;