import React from 'react';
import { Users, Building, FileText, Vote, MessageSquare, Briefcase, Calendar } from 'lucide-react';

const Government: React.FC = () => {
  const councilMembers = [
    {
      name: 'Sarah Chen',
      role: 'Mayor',
      ward: 'City Wide',
      image: 'https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?auto=format&fit=crop&q=80&w=400',
      bio: 'Serving since 2022, Mayor Chen has focused on sustainable development and community engagement.'
    },
    {
      name: 'Michael Rodriguez',
      role: 'Deputy Mayor',
      ward: 'Ward 1',
      image: 'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?auto=format&fit=crop&q=80&w=400',
      bio: 'Councilor Rodriguez brings 15 years of urban planning experience to city leadership.'
    }
  ];

  const upcomingMeetings = [
    {
      date: '2024-03-25',
      time: '19:00',
      title: 'City Council Regular Meeting',
      type: 'In-Person & Virtual',
      agenda: 'Budget Review, Zoning Amendments'
    },
    {
      date: '2024-03-27',
      time: '14:00',
      title: 'Planning Committee',
      type: 'Virtual',
      agenda: 'Downtown Development Plan'
    }
  ];

  const departments = [
    {
      name: 'Finance',
      director: 'Robert Walsh',
      description: 'Manages city budget, financial planning, and procurement.',
      keyProjects: [
        'Annual Budget: $324M',
        'New Financial Management System',
        'Cost Optimization Initiative'
      ]
    },
    {
      name: 'Urban Planning',
      director: 'Dr. Lisa Patel',
      description: 'Oversees city development, zoning, and long-term planning.',
      keyProjects: [
        'Downtown Revitalization',
        'Sustainable Growth Plan 2030',
        'Transit-Oriented Development'
      ]
    }
  ];

  return (
    <div className="min-h-screen bg-gray-50 py-12">
      <div className="container mx-auto px-4">
        <div className="max-w-6xl mx-auto">
          {/* Hero Section */}
          <div className="bg-blue-900 text-white rounded-lg p-8 mb-12">
            <h1 className="text-4xl font-bold mb-4">City Government</h1>
            <p className="text-xl opacity-90">
              Transparent, accountable, and responsive governance for our community
            </p>
          </div>

          {/* City Council Section */}
          <section className="bg-white rounded-lg shadow-md p-8 mb-12">
            <div className="flex items-center space-x-3 mb-6">
              <Users className="w-6 h-6 text-blue-600" />
              <h2 className="text-2xl font-bold">City Council</h2>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-8 mb-8">
              {councilMembers.map(member => (
                <div key={member.name} className="flex space-x-4">
                  <img
                    src={member.image}
                    alt={member.name}
                    className="w-32 h-32 rounded-lg object-cover"
                  />
                  <div>
                    <h3 className="text-xl font-semibold">{member.name}</h3>
                    <p className="text-blue-600">{member.role}</p>
                    <p className="text-gray-600">{member.ward}</p>
                    <p className="mt-2 text-gray-700">{member.bio}</p>
                  </div>
                </div>
              ))}
            </div>

            {/* Upcoming Meetings */}
            <div className="border-t pt-8">
              <div className="flex items-center space-x-3 mb-6">
                <Calendar className="w-6 h-6 text-blue-600" />
                <h3 className="text-xl font-bold">Upcoming Meetings</h3>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {upcomingMeetings.map(meeting => (
                  <div key={meeting.date} className="bg-gray-50 rounded-lg p-4">
                    <div className="flex justify-between items-start mb-2">
                      <div>
                        <h4 className="font-semibold">{meeting.title}</h4>
                        <p className="text-gray-600">{meeting.type}</p>
                      </div>
                      <span className="bg-blue-100 text-blue-800 px-2 py-1 rounded text-sm">
                        {new Date(meeting.date).toLocaleDateString()} {meeting.time}
                      </span>
                    </div>
                    <p className="text-gray-700">Agenda: {meeting.agenda}</p>
                  </div>
                ))}
              </div>
            </div>
          </section>

          {/* Departments Section */}
          <section className="bg-white rounded-lg shadow-md p-8 mb-12">
            <div className="flex items-center space-x-3 mb-6">
              <Building className="w-6 h-6 text-blue-600" />
              <h2 className="text-2xl font-bold">City Departments</h2>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
              {departments.map(dept => (
                <div key={dept.name} className="border rounded-lg p-6">
                  <h3 className="text-xl font-semibold mb-2">{dept.name}</h3>
                  <p className="text-blue-600 mb-2">Director: {dept.director}</p>
                  <p className="text-gray-700 mb-4">{dept.description}</p>
                  <h4 className="font-semibold mb-2">Key Projects:</h4>
                  <ul className="list-disc list-inside text-gray-700">
                    {dept.keyProjects.map(project => (
                      <li key={project}>{project}</li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </section>

          {/* Quick Links */}
          <section className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <a href="/government/budget" className="bg-white p-6 rounded-lg shadow-md hover:shadow-lg transition">
              <FileText className="w-6 h-6 text-blue-600 mb-3" />
              <h3 className="font-semibold mb-2">Budget & Finance</h3>
              <p className="text-gray-600">Access financial reports and budget documents</p>
            </a>
            <a href="/government/elections" className="bg-white p-6 rounded-lg shadow-md hover:shadow-lg transition">
              <Vote className="w-6 h-6 text-blue-600 mb-3" />
              <h3 className="font-semibold mb-2">Elections</h3>
              <p className="text-gray-600">Voter information and election resources</p>
            </a>
            <a href="/government/jobs" className="bg-white p-6 rounded-lg shadow-md hover:shadow-lg transition">
              <Briefcase className="w-6 h-6 text-blue-600 mb-3" />
              <h3 className="font-semibold mb-2">Employment</h3>
              <p className="text-gray-600">Browse and apply for city positions</p>
            </a>
          </section>
        </div>
      </div>
    </div>
  );
};

export default Government;