import React from 'react';
import { Briefcase, GraduationCap, Heart, DollarSign, Users, Clock } from 'lucide-react';

const Employment: React.FC = () => {
  const jobs = [
    {
      title: 'Civil Engineer',
      department: 'Public Works',
      type: 'Full-time',
      salary: '$75,000 - $95,000',
      posted: '2024-03-01',
      deadline: '2024-03-31',
      requirements: [
        "Bachelor's degree in Civil Engineering",
        '5+ years experience',
        'PE license required'
      ]
    },
    {
      title: 'Parks Maintenance Worker',
      department: 'Parks & Recreation',
      type: 'Full-time',
      salary: '$45,000 - $55,000',
      posted: '2024-03-05',
      deadline: '2024-03-25',
      requirements: [
        'High school diploma or equivalent',
        'Valid driver\'s license',
        '2+ years landscape maintenance experience'
      ]
    },
    {
      title: 'IT Systems Administrator',
      department: 'Information Technology',
      type: 'Full-time',
      salary: '$65,000 - $85,000',
      posted: '2024-03-10',
      deadline: '2024-04-10',
      requirements: [
        "Bachelor's degree in Computer Science or related field",
        '3+ years systems administration experience',
        'MCSA certification preferred'
      ]
    }
  ];

  const benefits = [
    {
      title: 'Health Insurance',
      icon: Heart,
      description: 'Comprehensive medical, dental, and vision coverage'
    },
    {
      title: 'Retirement',
      icon: DollarSign,
      description: 'Generous pension plan and 457(b) options'
    },
    {
      title: 'Professional Development',
      icon: GraduationCap,
      description: 'Training programs and tuition reimbursement'
    },
    {
      title: 'Work-Life Balance',
      icon: Clock,
      description: 'Flexible schedules and paid time off'
    }
  ];

  return (
    <div className="min-h-screen bg-gray-50 py-12">
      <div className="container mx-auto px-4">
        <div className="max-w-6xl mx-auto">
          {/* Hero Section */}
          <div className="bg-gradient-to-r from-blue-900 to-blue-700 text-white rounded-lg p-8 mb-12">
            <h1 className="text-4xl font-bold mb-4">Career Opportunities</h1>
            <p className="text-xl opacity-90">
              Join our team and make a difference in our community
            </p>
          </div>

          {/* Current Openings */}
          <section className="bg-white rounded-lg shadow-md p-6 mb-12">
            <div className="flex items-center space-x-3 mb-6">
              <Briefcase className="w-6 h-6 text-blue-600" />
              <h2 className="text-2xl font-bold">Current Openings</h2>
            </div>
            <div className="space-y-6">
              {jobs.map(job => (
                <div key={job.title} className="border rounded-lg p-6">
                  <div className="flex flex-col md:flex-row md:items-start md:justify-between mb-4">
                    <div>
                      <h3 className="text-xl font-bold mb-2">{job.title}</h3>
                      <p className="text-gray-600">{job.department}</p>
                    </div>
                    <div className="mt-4 md:mt-0">
                      <span className="bg-blue-100 text-blue-800 px-3 py-1 rounded-full text-sm">
                        {job.type}
                      </span>
                    </div>
                  </div>
                  
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                    <div>
                      <p className="text-gray-600">
                        <span className="font-semibold">Salary Range:</span> {job.salary}
                      </p>
                      <p className="text-gray-600">
                        <span className="font-semibold">Posted:</span> {new Date(job.posted).toLocaleDateString()}
                      </p>
                    </div>
                    <div>
                      <p className="text-gray-600">
                        <span className="font-semibold">Application Deadline:</span><br />
                        {new Date(job.deadline).toLocaleDateString()}
                      </p>
                    </div>
                  </div>

                  <div>
                    <h4 className="font-semibold mb-2">Requirements:</h4>
                    <ul className="list-disc list-inside text-gray-600">
                      {job.requirements.map((req, index) => (
                        <li key={index}>{req}</li>
                      ))}
                    </ul>
                  </div>

                  <div className="mt-6">
                    <button className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 transition">
                      Apply Now
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* Benefits */}
          <section className="bg-white rounded-lg shadow-md p-6 mb-12">
            <div className="flex items-center space-x-3 mb-6">
              <Users className="w-6 h-6 text-blue-600" />
              <h2 className="text-2xl font-bold">Employee Benefits</h2>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {benefits.map(benefit => (
                <div key={benefit.title} className="flex items-start space-x-4">
                  <benefit.icon className="w-8 h-8 text-blue-600" />
                  <div>
                    <h3 className="font-semibold mb-2">{benefit.title}</h3>
                    <p className="text-gray-600">{benefit.description}</p>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* Application Process */}
          <section className="bg-white rounded-lg shadow-md p-6">
            <h2 className="text-2xl font-bold mb-6">Application Process</h2>
            <div className="space-y-4">
              <div>
                <h3 className="font-semibold mb-2">1. Submit Application</h3>
                <p className="text-gray-600">
                  Complete the online application form and upload required documents.
                </p>
              </div>
              <div>
                <h3 className="font-semibold mb-2">2. Initial Review</h3>
                <p className="text-gray-600">
                  Our HR team will review your application and qualifications.
                </p>
              </div>
              <div>
                <h3 className="font-semibold mb-2">3. Interview Process</h3>
                <p className="text-gray-600">
                  Qualified candidates will be contacted for interviews.
                </p>
              </div>
              <div>
                <h3 className="font-semibold mb-2">4. Background Check</h3>
                <p className="text-gray-600">
                  Final candidates will undergo a background check and reference verification.
                </p>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
};

export default Employment;