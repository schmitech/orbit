import React from 'react';
import { Phone, Mail, MapPin, Clock, MessageSquare, HelpCircle, AlertTriangle } from 'lucide-react';

const Contact: React.FC = () => {
  const departments = [
    {
      name: 'General Inquiries',
      phone: '(555) 123-4567',
      email: 'info@cityofMaple.gov',
      hours: 'Mon-Fri: 8:00 AM - 5:00 PM'
    },
    {
      name: 'Emergency Services',
      phone: '911',
      email: 'emergency@cityofMaple.gov',
      hours: '24/7'
    },
    {
      name: 'Public Works',
      phone: '(555) 234-5678',
      email: 'publicworks@cityofMaple.gov',
      hours: 'Mon-Fri: 7:00 AM - 4:00 PM'
    }
  ];

  return (
    <div className="min-h-screen bg-gray-50 py-12">
      <div className="container mx-auto px-4">
        <div className="max-w-6xl mx-auto">
          {/* Hero Section */}
          <div className="bg-gradient-to-r from-blue-900 to-blue-700 text-white rounded-lg p-8 mb-12">
            <h1 className="text-4xl font-bold mb-4">Contact Us</h1>
            <p className="text-xl opacity-90">
              We're here to help. Reach out to us with any questions or concerns.
            </p>
          </div>

          {/* Contact Form */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 mb-12">
            <section className="bg-white rounded-lg shadow-md p-6">
              <h2 className="text-2xl font-bold mb-6">Send Us a Message</h2>
              <form className="space-y-6">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Name
                  </label>
                  <input
                    type="text"
                    className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Email
                  </label>
                  <input
                    type="email"
                    className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Department
                  </label>
                  <select className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500">
                    <option>Select a department</option>
                    <option>General Inquiries</option>
                    <option>Public Works</option>
                    <option>Parks & Recreation</option>
                    <option>City Planning</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Message
                  </label>
                  <textarea
                    rows={4}
                    className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  ></textarea>
                </div>
                <button
                  type="submit"
                  className="w-full bg-blue-600 text-white py-2 px-4 rounded-lg hover:bg-blue-700 transition"
                >
                  Send Message
                </button>
              </form>
            </section>

            <section className="space-y-8">
              {/* Department Contacts */}
              <div className="bg-white rounded-lg shadow-md p-6">
                <h2 className="text-2xl font-bold mb-6">Department Contacts</h2>
                <div className="space-y-6">
                  {departments.map(dept => (
                    <div key={dept.name} className="border-b pb-4 last:border-b-0 last:pb-0">
                      <h3 className="font-semibold mb-2">{dept.name}</h3>
                      <div className="space-y-2 text-gray-600">
                        <p className="flex items-center">
                          <Phone className="w-4 h-4 mr-2" />
                          {dept.phone}
                        </p>
                        <p className="flex items-center">
                          <Mail className="w-4 h-4 mr-2" />
                          {dept.email}
                        </p>
                        <p className="flex items-center">
                          <Clock className="w-4 h-4 mr-2" />
                          {dept.hours}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Location */}
              <div className="bg-white rounded-lg shadow-md p-6">
                <h2 className="text-2xl font-bold mb-6">Visit Us</h2>
                <div className="space-y-4">
                  <p className="flex items-start space-x-3">
                    <MapPin className="w-5 h-5 text-blue-600 flex-shrink-0" />
                    <span className="text-gray-600">
                      123 Main Street<br />
                      Maple, ST 12345
                    </span>
                  </p>
                  <div className="aspect-w-16 aspect-h-9">
                    {/* Add map iframe here if needed */}
                    <div className="w-full h-48 bg-gray-200 rounded-lg"></div>
                  </div>
                </div>
              </div>
            </section>
          </div>

          {/* Quick Links */}
          <section className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <a href="/faq" className="bg-white p-6 rounded-lg shadow-md hover:shadow-lg transition">
              <HelpCircle className="w-6 h-6 text-blue-600 mb-3" />
              <h3 className="font-semibold mb-2">FAQ</h3>
              <p className="text-gray-600">Find answers to common questions</p>
            </a>
            <a href="/report" className="bg-white p-6 rounded-lg shadow-md hover:shadow-lg transition">
              <AlertTriangle className="w-6 h-6 text-blue-600 mb-3" />
              <h3 className="font-semibold mb-2">Report an Issue</h3>
              <p className="text-gray-600">Submit maintenance requests</p>
            </a>
            <a href="/feedback" className="bg-white p-6 rounded-lg shadow-md hover:shadow-lg transition">
              <MessageSquare className="w-6 h-6 text-blue-600 mb-3" />
              <h3 className="font-semibold mb-2">Feedback</h3>
              <p className="text-gray-600">Share your suggestions</p>
            </a>
          </section>
        </div>
      </div>
    </div>
  );
};

export default Contact;