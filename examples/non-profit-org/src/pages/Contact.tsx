import React from 'react';
import { Mail, Phone, MapPin, Clock } from 'lucide-react';

export default function Contact() {
  return (
    <div className="bg-white">
      {/* Hero Section */}
      <div className="bg-[#2C3E50] text-white py-20">
        <div className="container mx-auto px-4">
          <h1 className="text-4xl md:text-5xl font-bold mb-4">Contact Us</h1>
          <p className="text-xl text-gray-300">We're here to help and answer any questions you may have</p>
        </div>
      </div>

      {/* Contact Information */}
      <section className="py-16">
        <div className="container mx-auto px-4">
          <div className="grid md:grid-cols-2 gap-12">
            <div>
              <h2 className="text-3xl font-bold text-[#2C3E50] mb-8">Get in Touch</h2>
              
              <div className="space-y-6">
                <div className="flex items-start gap-4">
                  <MapPin size={24} className="text-orange-500 mt-1" />
                  <div>
                    <h3 className="font-semibold text-lg text-[#2C3E50] mb-2">Address</h3>
                    <p className="text-gray-600">
                      123 Community Ave<br />
                      Demo City, ST 12345
                    </p>
                  </div>
                </div>

                <div className="flex items-start gap-4">
                  <Phone size={24} className="text-orange-500 mt-1" />
                  <div>
                    <h3 className="font-semibold text-lg text-[#2C3E50] mb-2">Phone</h3>
                    <p className="text-gray-600">(555) 123-4567</p>
                  </div>
                </div>

                <div className="flex items-start gap-4">
                  <Mail size={24} className="text-orange-500 mt-1" />
                  <div>
                    <h3 className="font-semibold text-lg text-[#2C3E50] mb-2">Email</h3>
                    <p className="text-gray-600">info@democenter.org</p>
                  </div>
                </div>

                <div className="flex items-start gap-4">
                  <Clock size={24} className="text-orange-500 mt-1" />
                  <div>
                    <h3 className="font-semibold text-lg text-[#2C3E50] mb-2">Hours of Operation</h3>
                    <ul className="text-gray-600 space-y-1">
                      <li>Monday - Friday: 8:00 AM - 8:00 PM</li>
                      <li>Saturday: 9:00 AM - 5:00 PM</li>
                      <li>Sunday: Closed</li>
                    </ul>
                  </div>
                </div>
              </div>
            </div>

            <div>
              <h2 className="text-3xl font-bold text-[#2C3E50] mb-8">Send Us a Message</h2>
              <form className="space-y-6">
                <div>
                  <label htmlFor="name" className="block text-sm font-medium text-gray-700 mb-1">
                    Name
                  </label>
                  <input
                    type="text"
                    id="name"
                    name="name"
                    className="w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-orange-500 focus:border-orange-500"
                  />
                </div>

                <div>
                  <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-1">
                    Email
                  </label>
                  <input
                    type="email"
                    id="email"
                    name="email"
                    className="w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-orange-500 focus:border-orange-500"
                  />
                </div>

                <div>
                  <label htmlFor="subject" className="block text-sm font-medium text-gray-700 mb-1">
                    Subject
                  </label>
                  <input
                    type="text"
                    id="subject"
                    name="subject"
                    className="w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-orange-500 focus:border-orange-500"
                  />
                </div>

                <div>
                  <label htmlFor="message" className="block text-sm font-medium text-gray-700 mb-1">
                    Message
                  </label>
                  <textarea
                    id="message"
                    name="message"
                    rows={6}
                    className="w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-orange-500 focus:border-orange-500"
                  ></textarea>
                </div>

                <button
                  type="submit"
                  className="w-full bg-orange-500 text-white py-3 px-6 rounded-md hover:bg-orange-600 transition-colors font-semibold"
                >
                  Send Message
                </button>
              </form>
            </div>
          </div>
        </div>
      </section>

      {/* Map */}
      <section className="py-16 bg-gray-50">
        <div className="container mx-auto px-4">
          <h2 className="text-3xl font-bold text-[#2C3E50] mb-8">Location</h2>
          <div className="aspect-w-16 aspect-h-9 bg-gray-200 rounded-lg">
            {/* Add your map component here */}
            <div className="w-full h-[400px] bg-gray-200 rounded-lg flex items-center justify-center">
              <p className="text-gray-600">Map placeholder - Integration required</p>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}