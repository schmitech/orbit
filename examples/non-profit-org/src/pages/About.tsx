import React from 'react';
import { Users, Heart, BookOpen } from 'lucide-react';

export default function About() {
  return (
    <div className="bg-white">
      {/* Hero Section */}
      <div className="bg-[#2C3E50] text-white py-20">
        <div className="container mx-auto px-4">
          <h1 className="text-4xl md:text-5xl font-bold mb-4">About Us</h1>
          <p className="text-xl text-gray-300">Building a stronger community through service and support</p>
        </div>
      </div>

      {/* Mission & Vision */}
      <section className="py-16">
        <div className="container mx-auto px-4">
          <div className="grid md:grid-cols-2 gap-12">
            <div>
              <h2 className="text-3xl font-bold text-[#2C3E50] mb-6">Our Mission</h2>
              <p className="text-gray-600 text-lg leading-relaxed">
                To empower and strengthen our community by providing quality educational programs,
                social services, and cultural activities that enhance the lives of individuals and
                families in our diverse neighborhood.
              </p>
            </div>
            <div>
              <h2 className="text-3xl font-bold text-[#2C3E50] mb-6">Our Vision</h2>
              <p className="text-gray-600 text-lg leading-relaxed">
                We envision a vibrant, inclusive community where all members have access to the
                resources and opportunities they need to thrive and reach their full potential.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Core Values */}
      <section className="bg-gray-50 py-16">
        <div className="container mx-auto px-4">
          <h2 className="text-3xl font-bold text-[#2C3E50] text-center mb-12">Our Core Values</h2>
          <div className="grid md:grid-cols-3 gap-8">
            <div className="text-center">
              <div className="text-orange-500 mb-4 flex justify-center">
                <Users size={48} />
              </div>
              <h3 className="text-xl font-semibold text-[#2C3E50] mb-3">Community First</h3>
              <p className="text-gray-600">
                We prioritize the needs of our community members and work collaboratively
                to create positive change.
              </p>
            </div>
            <div className="text-center">
              <div className="text-orange-500 mb-4 flex justify-center">
                <Heart size={48} />
              </div>
              <h3 className="text-xl font-semibold text-[#2C3E50] mb-3">Compassion</h3>
              <p className="text-gray-600">
                We serve with empathy and understanding, recognizing the dignity and
                worth of every individual.
              </p>
            </div>
            <div className="text-center">
              <div className="text-orange-500 mb-4 flex justify-center">
                <BookOpen size={48} />
              </div>
              <h3 className="text-xl font-semibold text-[#2C3E50] mb-3">Lifelong Learning</h3>
              <p className="text-gray-600">
                We believe in the transformative power of education and continuous
                personal growth.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* History */}
      <section className="py-16">
        <div className="container mx-auto px-4">
          <h2 className="text-3xl font-bold text-[#2C3E50] mb-8">Our History</h2>
          <div className="prose max-w-none text-gray-600">
            <p className="mb-4 text-lg">
              Founded in 1985, the City Community Center began as a small gathering place
              for neighborhood residents. Over the years, we've grown into a comprehensive
              community resource center, serving thousands of individuals and families
              annually.
            </p>
            <p className="mb-4 text-lg">
              Through decades of service, we've expanded our programs to meet the evolving
              needs of our community, from after-school youth programs to senior services
              and adult education initiatives.
            </p>
            <p className="text-lg">
              Today, we continue to build on our legacy of service, adapting to meet new
              challenges while maintaining our commitment to community empowerment and
              support.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}