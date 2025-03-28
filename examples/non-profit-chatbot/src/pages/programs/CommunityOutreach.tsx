import React from 'react';
import { Users, Heart, HandHeart, ArrowRight } from 'lucide-react';
import { Link } from 'react-router-dom';

export default function CommunityOutreach() {
  return (
    <div className="bg-white">
      {/* Hero Section */}
      <div 
        className="bg-[#2C3E50] text-white py-20"
        style={{
          backgroundImage: 'url(https://images.unsplash.com/photo-1559027615-cd4628902d4a?auto=format&fit=crop&q=80&w=1920)',
          backgroundSize: 'cover',
          backgroundPosition: 'center',
          position: 'relative'
        }}
      >
        <div className="absolute inset-0 bg-[#2C3E50] opacity-90"></div>
        <div className="container mx-auto px-4 relative">
          <h1 className="text-4xl md:text-5xl font-bold mb-4">Community Outreach</h1>
          <p className="text-xl text-gray-300 max-w-2xl">
            Making a difference through community engagement and volunteer initiatives.
            Join us in building a stronger, more connected community.
          </p>
        </div>
      </div>

      {/* Main Content */}
      <div className="container mx-auto px-4 py-12">
        {/* Volunteer Programs */}
        <section className="mb-16">
          <h2 className="text-3xl font-bold text-[#2C3E50] mb-6">Volunteer Programs</h2>
          <div className="grid md:grid-cols-2 gap-8">
            <div>
              <p className="text-gray-600 mb-6">
                Our volunteer programs connect passionate individuals with meaningful
                opportunities to serve the community. Whether you have a few hours or
                want to make a long-term commitment, we have a place for you.
              </p>
              <ul className="space-y-3 text-gray-600">
                <li className="flex items-start">
                  <ArrowRight className="text-orange-500 mt-1 mr-2" size={20} />
                  <span>Youth mentoring programs</span>
                </li>
                <li className="flex items-start">
                  <ArrowRight className="text-orange-500 mt-1 mr-2" size={20} />
                  <span>Senior companion services</span>
                </li>
                <li className="flex items-start">
                  <ArrowRight className="text-orange-500 mt-1 mr-2" size={20} />
                  <span>Food bank and meal delivery</span>
                </li>
                <li className="flex items-start">
                  <ArrowRight className="text-orange-500 mt-1 mr-2" size={20} />
                  <span>Community clean-up events</span>
                </li>
                <li className="flex items-start">
                  <ArrowRight className="text-orange-500 mt-1 mr-2" size={20} />
                  <span>Educational tutoring</span>
                </li>
              </ul>
            </div>
            <div>
              <img 
                src="https://images.unsplash.com/photo-1593113598332-cd288d649433?auto=format&fit=crop&q=80&w=1920" 
                alt="Volunteers working together" 
                className="rounded-lg shadow-lg"
              />
            </div>
          </div>
        </section>

        {/* Program Features */}
        <section className="mb-16">
          <h2 className="text-3xl font-bold text-[#2C3E50] mb-8">Our Impact</h2>
          <div className="grid md:grid-cols-3 gap-8">
            <div className="bg-gray-50 p-6 rounded-lg">
              <Users className="text-orange-500 mb-4" size={32} />
              <h3 className="text-xl font-semibold text-[#2C3E50] mb-3">Community Building</h3>
              <p className="text-gray-600">
                Creating connections and fostering a sense
                of belonging in our community.
              </p>
            </div>
            <div className="bg-gray-50 p-6 rounded-lg">
              <Heart className="text-orange-500 mb-4" size={32} />
              <h3 className="text-xl font-semibold text-[#2C3E50] mb-3">Support Services</h3>
              <p className="text-gray-600">
                Providing essential services to those in
                need throughout our community.
              </p>
            </div>
            <div className="bg-gray-50 p-6 rounded-lg">
              <HandHeart className="text-orange-500 mb-4" size={32} />
              <h3 className="text-xl font-semibold text-[#2C3E50] mb-3">Volunteer Growth</h3>
              <p className="text-gray-600">
                Developing leadership skills and personal
                growth through volunteer service.
              </p>
            </div>
          </div>
        </section>

        {/* Community Initiatives */}
        <section className="mb-16">
          <h2 className="text-3xl font-bold text-[#2C3E50] mb-6">Community Initiatives</h2>
          <div className="bg-gray-50 p-8 rounded-lg">
            <div className="grid md:grid-cols-2 gap-8">
              <div>
                <h3 className="text-2xl font-semibold text-[#2C3E50] mb-4">
                  Making a Difference Together
                </h3>
                <p className="text-gray-600 mb-6">
                  Our community initiatives bring people together to address local
                  needs and create positive change. Join us in making our community
                  a better place for everyone.
                </p>
                <ul className="space-y-3 text-gray-600 mb-6">
                  <li className="flex items-start">
                    <ArrowRight className="text-orange-500 mt-1 mr-2" size={20} />
                    <span>Neighborhood improvement projects</span>
                  </li>
                  <li className="flex items-start">
                    <ArrowRight className="text-orange-500 mt-1 mr-2" size={20} />
                    <span>Emergency assistance programs</span>
                  </li>
                  <li className="flex items-start">
                    <ArrowRight className="text-orange-500 mt-1 mr-2" size={20} />
                    <span>Health and wellness fairs</span>
                  </li>
                  <li className="flex items-start">
                    <ArrowRight className="text-orange-500 mt-1 mr-2" size={20} />
                    <span>Cultural celebration events</span>
                  </li>
                </ul>
                <Link
                  to="/contact"
                  className="inline-block bg-orange-500 text-white px-6 py-3 rounded-md hover:bg-orange-600 transition-colors"
                >
                  Get Involved
                </Link>
              </div>
              <div>
                <img 
                  src="https://images.unsplash.com/photo-1531206715517-5c0ba140b2b8?auto=format&fit=crop&q=80&w=1920" 
                  alt="Community members working on a local project" 
                  className="rounded-lg shadow-lg"
                />
              </div>
            </div>
          </div>
        </section>

        {/* Volunteer CTA */}
        <section className="bg-[#2C3E50] text-white p-8 rounded-lg">
          <div className="text-center">
            <h2 className="text-3xl font-bold mb-4">Make a Difference Today</h2>
            <p className="text-gray-300 mb-8 max-w-2xl mx-auto">
              Your time and talents can help create positive change in our community.
              Join our team of dedicated volunteers and make an impact.
            </p>
            <div className="space-x-4">
              <Link
                to="/contact"
                className="inline-block bg-orange-500 text-white px-8 py-3 rounded-full hover:bg-orange-600 transition-colors"
              >
                Volunteer Now
              </Link>
              <Link
                to="/programs"
                className="inline-block bg-transparent border-2 border-white text-white px-8 py-3 rounded-full hover:bg-white hover:text-[#2C3E50] transition-colors"
              >
                View All Programs
              </Link>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}