import React from 'react';
import { Calendar, BookOpen, Users, ArrowRight } from 'lucide-react';
import { Link } from 'react-router-dom';

export default function YouthPrograms() {
  return (
    <div className="bg-white">
      {/* Hero Section */}
      <div 
        className="bg-[#2C3E50] text-white py-20"
        style={{
          backgroundImage: 'url(https://images.unsplash.com/photo-1587729927069-dca7d5d15b22?auto=format&fit=crop&q=80&w=1920)',
          backgroundSize: 'cover',
          backgroundPosition: 'center',
          position: 'relative'
        }}
      >
        <div className="absolute inset-0 bg-[#2C3E50] opacity-90"></div>
        <div className="container mx-auto px-4 relative">
          <h1 className="text-4xl md:text-5xl font-bold mb-4">Youth Programs</h1>
          <p className="text-xl text-gray-300 max-w-2xl">
            Empowering young minds through engaging activities, educational support, and creative exploration. 
            Our youth programs foster growth, learning, and development in a safe, nurturing environment.
          </p>
        </div>
      </div>

      {/* Main Content */}
      <div className="container mx-auto px-4 py-12">
        {/* After School Programs */}
        <section className="mb-16">
          <h2 className="text-3xl font-bold text-[#2C3E50] mb-6">After School Programs</h2>
          <div className="grid md:grid-cols-2 gap-8">
            <div>
              <p className="text-gray-600 mb-6">
                Our comprehensive after-school programs provide a balanced mix of academic support,
                enrichment activities, and supervised recreation. Students receive homework help,
                participate in engaging activities, and develop important social skills.
              </p>
              <ul className="space-y-3 text-gray-600">
                <li className="flex items-start">
                  <ArrowRight className="text-orange-500 mt-1 mr-2" size={20} />
                  <span>Homework assistance and tutoring in core subjects</span>
                </li>
                <li className="flex items-start">
                  <ArrowRight className="text-orange-500 mt-1 mr-2" size={20} />
                  <span>STEM activities and hands-on learning projects</span>
                </li>
                <li className="flex items-start">
                  <ArrowRight className="text-orange-500 mt-1 mr-2" size={20} />
                  <span>Arts and crafts workshops</span>
                </li>
                <li className="flex items-start">
                  <ArrowRight className="text-orange-500 mt-1 mr-2" size={20} />
                  <span>Physical activities and organized sports</span>
                </li>
                <li className="flex items-start">
                  <ArrowRight className="text-orange-500 mt-1 mr-2" size={20} />
                  <span>Healthy snacks and nutrition education</span>
                </li>
              </ul>
            </div>
            <div>
              <img 
                src="https://images.unsplash.com/photo-1427504494785-3a9ca7044f45?auto=format&fit=crop&q=80&w=1920" 
                alt="Students working together on an after-school project" 
                className="rounded-lg shadow-lg"
              />
            </div>
          </div>
        </section>

        {/* Program Features */}
        <section className="mb-16">
          <h2 className="text-3xl font-bold text-[#2C3E50] mb-8">Program Features</h2>
          <div className="grid md:grid-cols-3 gap-8">
            <div className="bg-gray-50 p-6 rounded-lg">
              <Calendar className="text-orange-500 mb-4" size={32} />
              <h3 className="text-xl font-semibold text-[#2C3E50] mb-3">Flexible Scheduling</h3>
              <p className="text-gray-600">
                Programs available Monday through Friday, with options for full-time
                or part-time attendance to accommodate various family needs.
              </p>
            </div>
            <div className="bg-gray-50 p-6 rounded-lg">
              <BookOpen className="text-orange-500 mb-4" size={32} />
              <h3 className="text-xl font-semibold text-[#2C3E50] mb-3">Expert Staff</h3>
              <p className="text-gray-600">
                Qualified educators and youth development professionals who are
                passionate about helping children learn and grow.
              </p>
            </div>
            <div className="bg-gray-50 p-6 rounded-lg">
              <Users className="text-orange-500 mb-4" size={32} />
              <h3 className="text-xl font-semibold text-[#2C3E50] mb-3">Small Groups</h3>
              <p className="text-gray-600">
                Low student-to-staff ratios ensure individual attention and
                create a supportive learning environment.
              </p>
            </div>
          </div>
        </section>

        {/* Summer Programs */}
        <section className="mb-16">
          <h2 className="text-3xl font-bold text-[#2C3E50] mb-6">Summer Programs</h2>
          <div className="bg-gray-50 p-8 rounded-lg">
            <div className="grid md:grid-cols-2 gap-8">
              <div>
                <h3 className="text-2xl font-semibold text-[#2C3E50] mb-4">
                  Summer Learning Adventures
                </h3>
                <p className="text-gray-600 mb-6">
                  Our summer programs combine academic enrichment with fun activities
                  to prevent summer learning loss while ensuring children have an
                  enjoyable and memorable experience.
                </p>
                <ul className="space-y-3 text-gray-600 mb-6">
                  <li className="flex items-start">
                    <ArrowRight className="text-orange-500 mt-1 mr-2" size={20} />
                    <span>Weekly themed activities and projects</span>
                  </li>
                  <li className="flex items-start">
                    <ArrowRight className="text-orange-500 mt-1 mr-2" size={20} />
                    <span>Field trips to educational and cultural venues</span>
                  </li>
                  <li className="flex items-start">
                    <ArrowRight className="text-orange-500 mt-1 mr-2" size={20} />
                    <span>Outdoor activities and sports</span>
                  </li>
                  <li className="flex items-start">
                    <ArrowRight className="text-orange-500 mt-1 mr-2" size={20} />
                    <span>Reading and math enrichment</span>
                  </li>
                </ul>
                <Link
                  to="/contact"
                  className="inline-block bg-orange-500 text-white px-6 py-3 rounded-md hover:bg-orange-600 transition-colors"
                >
                  Inquire About Summer Programs
                </Link>
              </div>
              <div>
                <img 
                  src="https://images.unsplash.com/photo-1516627145497-ae6968895b74?auto=format&fit=crop&q=80&w=1920" 
                  alt="Children enjoying summer activities outdoors" 
                  className="rounded-lg shadow-lg"
                />
              </div>
            </div>
          </div>
        </section>

        {/* Registration CTA */}
        <section className="bg-[#2C3E50] text-white p-8 rounded-lg">
          <div className="text-center">
            <h2 className="text-3xl font-bold mb-4">Ready to Join Our Programs?</h2>
            <p className="text-gray-300 mb-8 max-w-2xl mx-auto">
              Give your child the opportunity to learn, grow, and thrive in our
              supportive and engaging youth programs. Space is limited, so register today!
            </p>
            <div className="space-x-4">
              <Link
                to="/contact"
                className="inline-block bg-orange-500 text-white px-8 py-3 rounded-full hover:bg-orange-600 transition-colors"
              >
                Contact Us
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