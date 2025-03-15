import React from 'react';
import { Calendar, Clock, MapPin } from 'lucide-react';

const upcomingEvents = [
  {
    title: "Summer Youth Program Registration",
    date: "May 15, 2024",
    time: "9:00 AM - 5:00 PM",
    description: "Early registration for our comprehensive summer youth program. Activities include STEM workshops, arts & crafts, sports, and field trips.",
    location: "Main Center",
    
    category: "Youth"
  },
  {
    title: "Community Health Fair",
    date: "June 1, 2024",
    time: "10:00 AM - 3:00 PM",
    description: "Free health screenings, wellness workshops, nutrition counseling, and fitness demonstrations for all community members.",
    location: "Community Hall",
    category: "Health"
  },
  {
    title: "Senior Social Club",
    date: "Weekly on Wednesdays",
    time: "1:00 PM - 4:00 PM",
    description: "Join us for board games, crafts, and social activities. Light refreshments provided.",
    location: "Senior Center",
    category: "Senior"
  },
  {
    title: "ESL Conversation Circle",
    date: "Every Tuesday & Thursday",
    time: "6:00 PM - 7:30 PM",
    description: "Practice English conversation skills in a friendly, supportive environment.",
    location: "Education Room",
    category: "Education"
  },
  {
    title: "Family Game Night",
    date: "Last Friday of each month",
    time: "6:00 PM - 8:30 PM",
    description: "Bring the whole family for an evening of fun board games, activities, and light refreshments.",
    location: "Community Hall",
    category: "Family"
  },
  {
    title: "Computer Skills Workshop",
    date: "Every Monday",
    time: "10:00 AM - 12:00 PM",
    description: "Learn basic computer skills, internet navigation, and common software applications.",
    location: "Computer Lab",
    category: "Education"
  }
];

const categories = [
  "All",
  "Youth",
  "Senior",
  "Health",
  "Education",
  "Family",
  "Community"
];

export default function Events() {
  return (
    <div className="bg-white">
      {/* Hero Section */}
      <div className="bg-[#2C3E50] text-white py-20">
        <div className="container mx-auto px-4">
          <h1 className="text-4xl md:text-5xl font-bold mb-4">Events Calendar</h1>
          <p className="text-xl text-gray-300">Join us for upcoming events and activities</p>
        </div>
      </div>

      {/* Events Section */}
      <section className="py-16">
        <div className="container mx-auto px-4">
          {/* Categories */}
          <div className="mb-12">
            <div className="flex flex-wrap gap-4">
              {categories.map((category, index) => (
                <button
                  key={index}
                  className={`px-6 py-2 rounded-full text-sm font-medium transition-colors
                    ${index === 0 
                      ? 'bg-orange-500 text-white' 
                      : 'bg-gray-100 text-gray-700 hover:bg-orange-100'
                    }`}
                >
                  {category}
                </button>
              ))}
            </div>
          </div>

          {/* Events Grid */}
          <div className="grid md:grid-cols-2 gap-8">
            {upcomingEvents.map((event, index) => (
              <div key={index} className="bg-gray-50 p-6 rounded-lg">
                <span className="inline-block bg-orange-100 text-orange-800 text-sm font-medium px-3 py-1 rounded-full mb-4">
                  {event.category}
                </span>
                <h3 className="text-xl font-semibold text-[#2C3E50] mb-3">
                  {event.title}
                </h3>
                <div className="flex items-center text-gray-600 mb-3">
                  <Calendar size={18} className="mr-2" />
                  {event.date}
                </div>
                <div className="flex items-center text-gray-600 mb-3">
                  <Clock size={18} className="mr-2" />
                  {event.time}
                </div>
                <div className="flex items-center text-gray-600 mb-4">
                  <MapPin size={18} className="mr-2" />
                  {event.location}
                </div>
                <p className="text-gray-600 mb-4">{event.description}</p>
                <button className="text-orange-500 hover:text-orange-600 font-medium inline-flex items-center">
                  Register Now
                  <svg className="w-4 h-4 ml-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                  </svg>
                </button>
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}