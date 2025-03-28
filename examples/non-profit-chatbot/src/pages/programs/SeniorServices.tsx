import React from 'react';
import { Heart, Users, Coffee, ArrowRight } from 'lucide-react';
import { Link } from 'react-router-dom';

export default function SeniorServices() {
  return (
    <div className="bg-white">
      {/* Hero Section */}
      <div 
        className="bg-[#2C3E50] text-white py-20"
        style={{
          backgroundImage: 'url(https://images.unsplash.com/photo-1516307365426-d1e27a9bf41c?auto=format&fit=crop&q=80&w=1920)',
          backgroundSize: 'cover',
          backgroundPosition: 'center',
          position: 'relative'
        }}
      >
        <div className="absolute inset-0 bg-[#2C3E50] opacity-90"></div>
        <div className="container mx-auto px-4 relative">
          <h1 className="text-4xl md:text-5xl font-bold mb-4">Senior Services</h1>
          <p className="text-xl text-gray-300 max-w-2xl">
            Enriching the lives of our senior community members through social connection,
            wellness programs, and engaging activities. We provide a welcoming space where
            seniors can stay active, make friends, and enjoy their golden years.
          </p>
        </div>
      </div>

      {/* Main Content */}
      <div className="container mx-auto px-4 py-12">
        {/* Social Activities */}
        <section className="mb-16">
          <h2 className="text-3xl font-bold text-[#2C3E50] mb-6">Social Activities</h2>
          <div className="grid md:grid-cols-2 gap-8">
            <div>
              <p className="text-gray-600 mb-6">
                Our senior social programs create opportunities for meaningful connections
                and enjoyable activities. We offer a variety of events and gatherings
                designed to combat isolation and promote active social engagement.
              </p>
              <ul className="space-y-3 text-gray-600">
                <li className="flex items-start">
                  <ArrowRight className="text-orange-500 mt-1 mr-2" size={20} />
                  <span>Weekly coffee and conversation groups</span>
                </li>
                <li className="flex items-start">
                  <ArrowRight className="text-orange-500 mt-1 mr-2" size={20} />
                  <span>Book clubs and discussion groups</span>
                </li>
                <li className="flex items-start">
                  <ArrowRight className="text-orange-500 mt-1 mr-2" size={20} />
                  <span>Card games and board game sessions</span>
                </li>
                <li className="flex items-start">
                  <ArrowRight className="text-orange-500 mt-1 mr-2" size={20} />
                  <span>Arts and crafts workshops</span>
                </li>
                <li className="flex items-start">
                  <ArrowRight className="text-orange-500 mt-1 mr-2" size={20} />
                  <span>Monthly themed social events</span>
                </li>
              </ul>
            </div>
            <div>
              <img 
                src="https://images.unsplash.com/photo-1573497019940-1c28c88b4f3e?auto=format&fit=crop&q=80&w=1920" 
                alt="Seniors enjoying a social gathering" 
                className="rounded-lg shadow-lg"
              />
            </div>
          </div>
        </section>

        {/* Program Features */}
        <section className="mb-16">
          <h2 className="text-3xl font-bold text-[#2C3E50] mb-8">Our Services</h2>
          <div className="grid md:grid-cols-3 gap-8">
            <div className="bg-gray-50 p-6 rounded-lg">
              <Heart className="text-orange-500 mb-4" size={32} />
              <h3 className="text-xl font-semibold text-[#2C3E50] mb-3">Health & Wellness</h3>
              <p className="text-gray-600">
                Regular health screenings, exercise classes, and wellness workshops
                designed specifically for seniors.
              </p>
            </div>
            <div className="bg-gray-50 p-6 rounded-lg">
              <Coffee className="text-orange-500 mb-4" size={32} />
              <h3 className="text-xl font-semibold text-[#2C3E50] mb-3">Social Events</h3>
              <p className="text-gray-600">
                Regular gatherings, holiday celebrations, and special events to
                foster community connections.
              </p>
            </div>
            <div className="bg-gray-50 p-6 rounded-lg">
              <Users className="text-orange-500 mb-4" size={32} />
              <h3 className="text-xl font-semibold text-[#2C3E50] mb-3">Support Services</h3>
              <p className="text-gray-600">
                Resource referrals, transportation assistance, and advocacy
                services for seniors in need.
              </p>
            </div>
          </div>
        </section>

        {/* Wellness Programs */}
        <section className="mb-16">
          <h2 className="text-3xl font-bold text-[#2C3E50] mb-6">Wellness Programs</h2>
          <div className="bg-gray-50 p-8 rounded-lg">
            <div className="grid md:grid-cols-2 gap-8">
              <div>
                <h3 className="text-2xl font-semibold text-[#2C3E50] mb-4">
                  Active Aging Programs
                </h3>
                <p className="text-gray-600 mb-6">
                  Stay active and healthy with our range of wellness programs designed
                  specifically for seniors. Our certified instructors ensure safe and
                  effective exercise routines for all ability levels.
                </p>
                <ul className="space-y-3 text-gray-600 mb-6">
                  <li className="flex items-start">
                    <ArrowRight className="text-orange-500 mt-1 mr-2" size={20} />
                    <span>Gentle yoga and chair exercises</span>
                  </li>
                  <li className="flex items-start">
                    <ArrowRight className="text-orange-500 mt-1 mr-2" size={20} />
                    <span>Balance and fall prevention classes</span>
                  </li>
                  <li className="flex items-start">
                    <ArrowRight className="text-orange-500 mt-1 mr-2" size={20} />
                    <span>Walking groups and outdoor activities</span>
                  </li>
                  <li className="flex items-start">
                    <ArrowRight className="text-orange-500 mt-1 mr-2" size={20} />
                    <span>Nutrition workshops and cooking demos</span>
                  </li>
                </ul>
                <Link
                  to="/contact"
                  className="inline-block bg-orange-500 text-white px-6 py-3 rounded-md hover:bg-orange-600 transition-colors"
                >
                  Join Our Wellness Programs
                </Link>
              </div>
              <div>
                <img 
                  src="https://images.unsplash.com/photo-1571019613454-1cb2f99b2d8b?auto=format&fit=crop&q=80&w=1920" 
                  alt="Seniors participating in a gentle exercise class" 
                  className="rounded-lg shadow-lg"
                />
              </div>
            </div>
          </div>
        </section>

        {/* Registration CTA */}
        <section className="bg-[#2C3E50] text-white p-8 rounded-lg">
          <div className="text-center">
            <h2 className="text-3xl font-bold mb-4">Join Our Senior Community</h2>
            <p className="text-gray-300 mb-8 max-w-2xl mx-auto">
              Discover the joy of active aging and social connection. Our senior
              programs are designed to enrich your life and foster meaningful relationships.
            </p>
            <div className="space-x-4">
              <Link
                to="/contact"
                className="inline-block bg-orange-500 text-white px-8 py-3 rounded-full hover:bg-orange-600 transition-colors"
              >
                Contact Us
              </Link>
              <Link
                to="/events"
                className="inline-block bg-transparent border-2 border-white text-white px-8 py-3 rounded-full hover:bg-white hover:text-[#2C3E50] transition-colors"
              >
                View Calendar
              </Link>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}