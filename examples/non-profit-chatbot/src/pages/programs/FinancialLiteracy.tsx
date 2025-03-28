import React from 'react';
import { DollarSign, TrendingUp, Shield, ArrowRight } from 'lucide-react';
import { Link } from 'react-router-dom';

export default function FinancialLiteracy() {
  return (
    <div className="bg-white">
      {/* Hero Section */}
      <div 
        className="bg-[#2C3E50] text-white py-20"
        style={{
          backgroundImage: 'url(https://images.unsplash.com/photo-1554224155-6726b3ff858f?auto=format&fit=crop&q=80&w=1920)',
          backgroundSize: 'cover',
          backgroundPosition: 'center',
          position: 'relative'
        }}
      >
        <div className="absolute inset-0 bg-[#2C3E50] opacity-90"></div>
        <div className="container mx-auto px-4 relative">
          <h1 className="text-4xl md:text-5xl font-bold mb-4">Financial Literacy</h1>
          <p className="text-xl text-gray-300 max-w-2xl">
            Build a strong financial foundation through education and practical skills.
            Our programs help you make informed financial decisions and achieve your
            financial goals.
          </p>
        </div>
      </div>

      {/* Main Content */}
      <div className="container mx-auto px-4 py-12">
        {/* Core Programs */}
        <section className="mb-16">
          <h2 className="text-3xl font-bold text-[#2C3E50] mb-6">Financial Education Programs</h2>
          <div className="grid md:grid-cols-2 gap-8">
            <div>
              <p className="text-gray-600 mb-6">
                Our comprehensive financial literacy programs provide the knowledge and
                tools you need to manage your money effectively. Learn from experienced
                financial educators in a supportive environment.
              </p>
              <ul className="space-y-3 text-gray-600">
                <li className="flex items-start">
                  <ArrowRight className="text-orange-500 mt-1 mr-2" size={20} />
                  <span>Basic budgeting and money management</span>
                </li>
                <li className="flex items-start">
                  <ArrowRight className="text-orange-500 mt-1 mr-2" size={20} />
                  <span>Credit building and debt management</span>
                </li>
                <li className="flex items-start">
                  <ArrowRight className="text-orange-500 mt-1 mr-2" size={20} />
                  <span>Investment basics and retirement planning</span>
                </li>
                <li className="flex items-start">
                  <ArrowRight className="text-orange-500 mt-1 mr-2" size={20} />
                  <span>Home buying education</span>
                </li>
                <li className="flex items-start">
                  <ArrowRight className="text-orange-500 mt-1 mr-2" size={20} />
                  <span>Small business financial planning</span>
                </li>
              </ul>
            </div>
            <div>
              <img 
                src="https://images.unsplash.com/photo-1554224154-26032ffc0d07?auto=format&fit=crop&q=80&w=1920" 
                alt="Financial planning session" 
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
              <DollarSign className="text-orange-500 mb-4" size={32} />
              <h3 className="text-xl font-semibold text-[#2C3E50] mb-3">Personal Finance</h3>
              <p className="text-gray-600">
                Learn essential money management skills for
                personal and family financial success.
              </p>
            </div>
            <div className="bg-gray-50 p-6 rounded-lg">
              <TrendingUp className="text-orange-500 mb-4" size={32} />
              <h3 className="text-xl font-semibold text-[#2C3E50] mb-3">Investment Education</h3>
              <p className="text-gray-600">
                Understand investment options and strategies
                for long-term financial growth.
              </p>
            </div>
            <div className="bg-gray-50 p-6 rounded-lg">
              <Shield className="text-orange-500 mb-4" size={32} />
              <h3 className="text-xl font-semibold text-[#2C3E50] mb-3">Financial Security</h3>
              <p className="text-gray-600">
                Learn to protect your assets and plan for
                a secure financial future.
              </p>
            </div>
          </div>
        </section>

        {/* Workshops */}
        <section className="mb-16">
          <h2 className="text-3xl font-bold text-[#2C3E50] mb-6">Financial Workshops</h2>
          <div className="bg-gray-50 p-8 rounded-lg">
            <div className="grid md:grid-cols-2 gap-8">
              <div>
                <h3 className="text-2xl font-semibold text-[#2C3E50] mb-4">
                  Practical Financial Skills
                </h3>
                <p className="text-gray-600 mb-6">
                  Join our interactive workshops to develop practical financial skills
                  and learn from financial experts. Our hands-on approach helps you
                  apply what you learn to your personal financial situation.
                </p>
                <ul className="space-y-3 text-gray-600 mb-6">
                  <li className="flex items-start">
                    <ArrowRight className="text-orange-500 mt-1 mr-2" size={20} />
                    <span>Monthly budget creation</span>
                  </li>
                  <li className="flex items-start">
                    <ArrowRight className="text-orange-500 mt-1 mr-2" size={20} />
                    <span>Debt reduction strategies</span>
                  </li>
                  <li className="flex items-start">
                    <ArrowRight className="text-orange-500 mt-1 mr-2" size={20} />
                    <span>Savings and investment planning</span>
                  </li>
                  <li className="flex items-start">
                    <ArrowRight className="text-orange-500 mt-1 mr-2" size={20} />
                    <span>Credit score improvement</span>
                  </li>
                </ul>
                <Link
                  to="/contact"
                  className="inline-block bg-orange-500 text-white px-6 py-3 rounded-md hover:bg-orange-600 transition-colors"
                >
                  Register for Workshops
                </Link>
              </div>
              <div>
                <img 
                  src="https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?auto=format&fit=crop&q=80&w=1920" 
                  alt="Financial workshop in progress" 
                  className="rounded-lg shadow-lg"
                />
              </div>
            </div>
          </div>
        </section>

        {/* Registration CTA */}
        <section className="bg-[#2C3E50] text-white p-8 rounded-lg">
          <div className="text-center">
            <h2 className="text-3xl font-bold mb-4">Take Control of Your Finances</h2>
            <p className="text-gray-300 mb-8 max-w-2xl mx-auto">
              Start your journey to financial literacy and independence. Our expert
              instructors are here to guide you every step of the way.
            </p>
            <div className="space-x-4">
              <Link
                to="/contact"
                className="inline-block bg-orange-500 text-white px-8 py-3 rounded-full hover:bg-orange-600 transition-colors"
              >
                Get Started
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