import React from 'react';
import { Vote, Calendar, MapPin, FileText, HelpCircle } from 'lucide-react';

const Elections: React.FC = () => {
  const upcomingElections = [
    {
      title: 'Municipal General Election',
      date: 'November 5, 2024',
      type: 'General Election',
      positions: [
        'Mayor',
        'City Council (Districts 2, 4, 6)',
        'City Treasurer'
      ]
    },
    {
      title: 'Special Bond Referendum',
      date: 'September 15, 2024',
      type: 'Special Election',
      description: 'Infrastructure improvement bonds for road and bridge repairs'
    }
  ];

  const votingLocations = [
    {
      name: 'City Hall',
      address: '123 Main Street',
      hours: '7:00 AM - 8:00 PM',
      accessibility: ['Wheelchair Access', 'Parking Available']
    },
    {
      name: 'Community Center',
      address: '456 Park Avenue',
      hours: '7:00 AM - 8:00 PM',
      accessibility: ['Wheelchair Access', 'Public Transit Access']
    }
  ];

  return (
    <div className="min-h-screen bg-gray-50 py-12">
      <div className="container mx-auto px-4">
        <div className="max-w-6xl mx-auto">
          {/* Hero Section */}
          <div className="bg-gradient-to-r from-purple-900 to-purple-700 text-white rounded-lg p-8 mb-12">
            <h1 className="text-4xl font-bold mb-4">Elections</h1>
            <p className="text-xl opacity-90">
              Your voice matters. Learn about upcoming elections and how to participate.
            </p>
          </div>

          {/* Upcoming Elections */}
          <section className="bg-white rounded-lg shadow-md p-6 mb-12">
            <div className="flex items-center space-x-3 mb-6">
              <Calendar className="w-6 h-6 text-purple-600" />
              <h2 className="text-2xl font-bold">Upcoming Elections</h2>
            </div>
            <div className="space-y-6">
              {upcomingElections.map(election => (
                <div key={election.title} className="border-b pb-6 last:border-b-0 last:pb-0">
                  <h3 className="text-xl font-semibold mb-2">{election.title}</h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <p className="text-gray-600">
                        <span className="font-semibold">Date:</span> {election.date}
                      </p>
                      <p className="text-gray-600">
                        <span className="font-semibold">Type:</span> {election.type}
                      </p>
                    </div>
                    <div>
                      {election.positions ? (
                        <div>
                          <p className="font-semibold">Positions:</p>
                          <ul className="list-disc list-inside text-gray-600">
                            {election.positions.map(position => (
                              <li key={position}>{position}</li>
                            ))}
                          </ul>
                        </div>
                      ) : (
                        <p className="text-gray-600">{election.description}</p>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* Voting Locations */}
          <section className="bg-white rounded-lg shadow-md p-6 mb-12">
            <div className="flex items-center space-x-3 mb-6">
              <MapPin className="w-6 h-6 text-purple-600" />
              <h2 className="text-2xl font-bold">Voting Locations</h2>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {votingLocations.map(location => (
                <div key={location.name} className="border rounded-lg p-4">
                  <h3 className="font-semibold mb-2">{location.name}</h3>
                  <p className="text-gray-600">{location.address}</p>
                  <p className="text-gray-600">Hours: {location.hours}</p>
                  <div className="mt-2">
                    <p className="font-semibold">Accessibility:</p>
                    <ul className="list-disc list-inside text-gray-600">
                      {location.accessibility.map(feature => (
                        <li key={feature}>{feature}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* Quick Links */}
          <section className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <a href="/elections/register" className="bg-white p-6 rounded-lg shadow-md hover:shadow-lg transition">
              <Vote className="w-6 h-6 text-purple-600 mb-3" />
              <h3 className="font-semibold mb-2">Voter Registration</h3>
              <p className="text-gray-600">Register to vote or check your status</p>
            </a>
            <a href="/elections/information" className="bg-white p-6 rounded-lg shadow-md hover:shadow-lg transition">
              <FileText className="w-6 h-6 text-purple-600 mb-3" />
              <h3 className="font-semibold mb-2">Voter Information</h3>
              <p className="text-gray-600">View sample ballots and candidate info</p>
            </a>
            <a href="/elections/faq" className="bg-white p-6 rounded-lg shadow-md hover:shadow-lg transition">
              <HelpCircle className="w-6 h-6 text-purple-600 mb-3" />
              <h3 className="font-semibold mb-2">Election FAQ</h3>
              <p className="text-gray-600">Common questions about voting</p>
            </a>
          </section>
        </div>
      </div>
    </div>
  );
};

export default Elections;