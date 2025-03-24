import React from 'react';
import { FileText, Clock, DollarSign, CheckSquare, HelpCircle, AlertTriangle, Search } from 'lucide-react';

const BuildingPermits: React.FC = () => {
  const permitTypes = [
    {
      title: 'Residential Construction',
      description: 'New homes, additions, renovations',
      timeframe: '15-20 business days',
      fee: 'Starting at $150',
      requirements: [
        'Building plans',
        'Site plan',
        'Property survey',
        'Contractor information'
      ]
    },
    {
      title: 'Commercial Construction',
      description: 'New buildings, tenant improvements',
      timeframe: '20-30 business days',
      fee: 'Starting at $500',
      requirements: [
        'Architectural plans',
        'Engineering documents',
        'Environmental assessment',
        'Fire safety plan'
      ]
    },
    {
      title: 'Minor Renovations',
      description: 'Kitchen, bathroom, basement finishing',
      timeframe: '5-10 business days',
      fee: 'Starting at $75',
      requirements: [
        'Project description',
        'Basic floor plan',
        'Contractor details'
      ]
    }
  ];

  return (
    <div className="min-h-screen bg-gray-50 py-12">
      <div className="container mx-auto px-4">
        <div className="max-w-6xl mx-auto">
          {/* Hero Section */}
          <div className="bg-gradient-to-r from-blue-900 to-blue-700 text-white rounded-lg p-8 mb-12">
            <h1 className="text-4xl font-bold mb-4">Building Permits</h1>
            <p className="text-xl opacity-90">
              Everything you need to know about obtaining building permits in our city
            </p>
          </div>

          {/* Quick Actions */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-12">
            <a href="/permits/apply" className="bg-white p-6 rounded-lg shadow-md hover:shadow-lg transition">
              <FileText className="w-6 h-6 text-blue-600 mb-3" />
              <h3 className="font-semibold mb-2">Apply Online</h3>
              <p className="text-gray-600">Submit permit applications</p>
            </a>
            <a href="/permits/status" className="bg-white p-6 rounded-lg shadow-md hover:shadow-lg transition">
              <Search className="w-6 h-6 text-blue-600 mb-3" />
              <h3 className="font-semibold mb-2">Check Status</h3>
              <p className="text-gray-600">Track your application</p>
            </a>
            <a href="/permits/schedule" className="bg-white p-6 rounded-lg shadow-md hover:shadow-lg transition">
              <Clock className="w-6 h-6 text-blue-600 mb-3" />
              <h3 className="font-semibold mb-2">Schedule Inspection</h3>
              <p className="text-gray-600">Book or modify inspections</p>
            </a>
          </div>

          {/* Permit Types */}
          <section className="bg-white rounded-lg shadow-md p-6 mb-12">
            <h2 className="text-2xl font-bold mb-6">Permit Types</h2>
            <div className="space-y-6">
              {permitTypes.map(permit => (
                <div key={permit.title} className="border rounded-lg p-6">
                  <h3 className="text-xl font-semibold mb-2">{permit.title}</h3>
                  <p className="text-gray-600 mb-4">{permit.description}</p>
                  
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                    <div>
                      <p className="flex items-center text-gray-600">
                        <Clock className="w-5 h-5 text-blue-600 mr-2" />
                        Processing Time: {permit.timeframe}
                      </p>
                    </div>
                    <div>
                      <p className="flex items-center text-gray-600">
                        <DollarSign className="w-5 h-5 text-blue-600 mr-2" />
                        Fee: {permit.fee}
                      </p>
                    </div>
                  </div>

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

          {/* Process Steps */}
          <section className="bg-white rounded-lg shadow-md p-6 mb-12">
            <h2 className="text-2xl font-bold mb-6">Application Process</h2>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
              <div className="text-center">
                <div className="bg-blue-100 w-12 h-12 rounded-full flex items-center justify-center mx-auto mb-4">
                  <FileText className="w-6 h-6 text-blue-600" />
                </div>
                <h3 className="font-semibold mb-2">1. Submit Application</h3>
                <p className="text-gray-600">Complete and submit your permit application with required documents</p>
              </div>
              <div className="text-center">
                <div className="bg-blue-100 w-12 h-12 rounded-full flex items-center justify-center mx-auto mb-4">
                  <CheckSquare className="w-6 h-6 text-blue-600" />
                </div>
                <h3 className="font-semibold mb-2">2. Review Process</h3>
                <p className="text-gray-600">City staff reviews your application and plans</p>
              </div>
              <div className="text-center">
                <div className="bg-blue-100 w-12 h-12 rounded-full flex items-center justify-center mx-auto mb-4">
                  <DollarSign className="w-6 h-6 text-blue-600" />
                </div>
                <h3 className="font-semibold mb-2">3. Pay Fees</h3>
                <p className="text-gray-600">Pay applicable permit fees</p>
              </div>
              <div className="text-center">
                <div className="bg-blue-100 w-12 h-12 rounded-full flex items-center justify-center mx-auto mb-4">
                  <CheckSquare className="w-6 h-6 text-blue-600" />
                </div>
                <h3 className="font-semibold mb-2">4. Receive Permit</h3>
                <p className="text-gray-600">Get your approved permit and begin work</p>
              </div>
            </div>
          </section>

          {/* Help Section */}
          <section className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="bg-yellow-50 p-6 rounded-lg">
              <div className="flex items-center space-x-3 mb-4">
                <HelpCircle className="w-6 h-6 text-yellow-600" />
                <h2 className="text-xl font-bold">Need Help?</h2>
              </div>
              <p className="text-gray-700 mb-4">
                Our permit specialists are available to assist you with your application.
              </p>
              <p className="text-gray-700">
                Call: (555) 123-4567<br />
                Email: permits@cityofMaple.gov
              </p>
            </div>

            <div className="bg-blue-50 p-6 rounded-lg">
              <div className="flex items-center space-x-3 mb-4">
                <AlertTriangle className="w-6 h-6 text-blue-600" />
                <h2 className="text-xl font-bold">Important Notice</h2>
              </div>
              <p className="text-gray-700">
                Work conducted without proper permits may result in fines and require
                removal or correction of non-compliant construction.
              </p>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
};

export default BuildingPermits;