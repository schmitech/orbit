import React from 'react';
import { BookOpen, GraduationCap, Users, ArrowRight } from 'lucide-react';
import { Link } from 'react-router-dom';

export default function AdultEducation() {
  return (
    <div className="bg-white">
      {/* Hero Section */}
      <div 
        className="bg-[#2C3E50] text-white py-20"
        style={{
          backgroundImage: 'url(https://images.unsplash.com/photo-1524178232363-1fb2b075b655?auto=format&fit=crop&q=80&w=1920)',
          backgroundSize: 'cover',
          backgroundPosition: 'center',
          position: 'relative'
        }}
      >
        <div className="absolute inset-0 bg-[#2C3E50] opacity-90"></div>
        <div className="container mx-auto px-4 relative">
          <h1 className="text-4xl md:text-5xl font-bold mb-4">Adult Education</h1>
          <p className="text-xl text-gray-300 max-w-2xl">
            Empowering adults through lifelong learning opportunities. Our programs help you
            develop new skills, advance your career, and achieve your educational goals.
          </p>
        </div>
      </div>

      {/* Main Content */}
      <div className="container mx-auto px-4 py-12">
        {/* Core Programs */}
        <section className="mb-16">
          <h2 className="text-3xl font-bold text-[#2C3E50] mb-6">Core Programs</h2>
          <div className="grid md:grid-cols-2 gap-8">
            <div>
              <p className="text-gray-600 mb-6">
                Our adult education programs are designed to meet the diverse needs of adult
                learners. Whether you're looking to improve your language skills, prepare for
                higher education, or enhance your professional capabilities, we have a program
                for you.
              </p>
              <ul className="space-y-3 text-gray-600">
                <li className="flex items-start">
                  <ArrowRight className="text-orange-500 mt-1 mr-2" size={20} />
                  <span>ESL classes for all proficiency levels</span>
                </li>
                <li className="flex items-start">
                  <ArrowRight className="text-orange-500 mt-1 mr-2" size={20} />
                  <span>GED preparation and testing</span>
                </li>
                <li className="flex items-start">
                  <ArrowRight className="text-orange-500 mt-1 mr-2" size={20} />
                  <span>Basic computer skills training</span>
                </li>
                <li className="flex items-start">
                  <ArrowRight className="text-orange-500 mt-1 mr-2" size={20} />
                  <span>Professional development workshops</span>
                </li>
                <li className="flex items-start">
                  <ArrowRight className="text-orange-500 mt-1 mr-2" size={20} />
                  <span>Career counseling services</span>
                </li>
              </ul>
            </div>
            <div>
              <img 
                src="https://images.unsplash.com/photo-1522202176988-66273c2fd55f?auto=format&fit=crop&q=80&w=1920" 
                alt="Adult students in a classroom setting" 
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
              <BookOpen className="text-orange-500 mb-4" size={32} />
              <h3 className="text-xl font-semibold text-[#2C3E50] mb-3">Flexible Learning</h3>
              <p className="text-gray-600">
                Evening and weekend classes available to accommodate
                work schedules and family commitments.
              </p>
            </div>
            <div className="bg-gray-50 p-6 rounded-lg">
              <GraduationCap className="text-orange-500 mb-4" size={32} />
              <h3 className="text-xl font-semibold text-[#2C3E50] mb-3">Expert Instructors</h3>
              <p className="text-gray-600">
                Learn from experienced educators dedicated to
                adult learning and student success.
              </p>
            </div>
            <div className="bg-gray-50 p-6 rounded-lg">
              <Users className="text-orange-500 mb-4" size={32} />
              <h3 className="text-xl font-semibold text-[#2C3E50] mb-3">Small Classes</h3>
              <p className="text-gray-600">
                Small class sizes ensure individual attention
                and personalized learning support.
              </p>
            </div>
          </div>
        </section>

        {/* Career Development */}
        <section className="mb-16">
          <h2 className="text-3xl font-bold text-[#2C3E50] mb-6">Career Development</h2>
          <div className="bg-gray-50 p-8 rounded-lg">
            <div className="grid md:grid-cols-2 gap-8">
              <div>
                <h3 className="text-2xl font-semibold text-[#2C3E50] mb-4">
                  Professional Skills Training
                </h3>
                <p className="text-gray-600 mb-6">
                  Enhance your employability with our career-focused training programs.
                  Learn practical skills that employers value and get support in your
                  job search journey.
                </p>
                <ul className="space-y-3 text-gray-600 mb-6">
                  <li className="flex items-start">
                    <ArrowRight className="text-orange-500 mt-1 mr-2" size={20} />
                    <span>Resume writing workshops</span>
                  </li>
                  <li className="flex items-start">
                    <ArrowRight className="text-orange-500 mt-1 mr-2" size={20} />
                    <span>Interview preparation</span>
                  </li>
                  <li className="flex items-start">
                    <ArrowRight className="text-orange-500 mt-1 mr-2" size={20} />
                    <span>Digital skills training</span>
                  </li>
                  <li className="flex items-start">
                    <ArrowRight className="text-orange-500 mt-1 mr-2" size={20} />
                    <span>Networking opportunities</span>
                  </li>
                </ul>
                <Link
                  to="/contact"
                  className="inline-block bg-orange-500 text-white px-6 py-3 rounded-md hover:bg-orange-600 transition-colors"
                >
                  Start Your Career Journey
                </Link>
              </div>
              <div>
                <img 
                  src="https://images.unsplash.com/photo-1434030216411-0b793f4b4173?auto=format&fit=crop&q=80&w=1920" 
                  alt="Professional development workshop in progress" 
                  className="rounded-lg shadow-lg"
                />
              </div>
            </div>
          </div>
        </section>

        {/* Registration CTA */}
        <section className="bg-[#2C3E50] text-white p-8 rounded-lg">
          <div className="text-center">
            <h2 className="text-3xl font-bold mb-4">Ready to Start Learning?</h2>
            <p className="text-gray-300 mb-8 max-w-2xl mx-auto">
              Take the first step towards achieving your educational and career goals.
              Join our supportive learning community today.
            </p>
            <div className="space-x-4">
              <Link
                to="/contact"
                className="inline-block bg-orange-500 text-white px-8 py-3 rounded-full hover:bg-orange-600 transition-colors"
              >
                Enroll Now
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