import React, { useState, useEffect } from 'react';
import { Users, Heart, BookOpen, Calendar, DollarSign, Clock, MapPin } from 'lucide-react';
import { Link } from 'react-router-dom';

const bannerImages = [
  'https://images.unsplash.com/photo-1577896851231-70ef18881754?auto=format&fit=crop&q=80&w=1920',
  'https://images.unsplash.com/photo-1581078426770-6d336e5de7bf?auto=format&fit=crop&q=80&w=1920',
  'https://images.unsplash.com/photo-1509062522246-3755977927d7?auto=format&fit=crop&q=80&w=1920'
];

const programs = [
  {
    icon: <Users size={32} />,
    title: "Youth Programs",
    description: "After-school activities, tutoring services, and summer camps for children aged 5-18.",
    link: "/programs/youth"
  },
  {
    icon: <Heart size={32} />,
    title: "Senior Services",
    description: "Social activities, health programs, and support services for our senior community members.",
    link: "/programs/seniors"
  },
  {
    icon: <BookOpen size={32} />,
    title: "Adult Education",
    description: "ESL classes, computer literacy, job training, and professional development workshops.",
    link: "/programs/adult-education"
  },
  {
    icon: <Calendar size={32} />,
    title: "Family Services",
    description: "Counseling, parenting workshops, and family support programs.",
    link: "/programs/family"
  },
  {
    icon: <DollarSign size={32} />,
    title: "Financial Literacy",
    description: "Budget planning, investment education, and financial counseling services.",
    link: "/programs/financial"
  },
  {
    icon: <Users size={32} />,
    title: "Community Outreach",
    description: "Volunteer opportunities, community events, and neighborhood improvement initiatives.",
    link: "/programs/outreach"
  }
];

const events = [
  {
    title: "Summer Youth Program Registration",
    date: "May 15, 2024",
    time: "9:00 AM - 5:00 PM",
    description: "Early registration for our comprehensive summer youth program. Activities include STEM workshops, arts & crafts, sports, and field trips.",
    location: "Main Center"
  },
  {
    title: "Community Health Fair",
    date: "June 1, 2024",
    time: "10:00 AM - 3:00 PM",
    description: "Free health screenings, wellness workshops, nutrition counseling, and fitness demonstrations for all community members.",
    location: "Community Hall"
  },
  {
    title: "Senior Social Club",
    date: "Weekly on Wednesdays",
    time: "1:00 PM - 4:00 PM",
    description: "Join us for board games, crafts, and social activities. Light refreshments provided.",
    location: "Senior Center"
  },
  {
    title: "ESL Conversation Circle",
    date: "Every Tuesday & Thursday",
    time: "6:00 PM - 7:30 PM",
    description: "Practice English conversation skills in a friendly, supportive environment.",
    location: "Education Room"
  }
];

export default function Home() {
  const [currentBanner, setCurrentBanner] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setCurrentBanner((prev) => (prev + 1) % bannerImages.length);
    }, 5000);
    return () => clearInterval(timer);
  }, []);

  return (
    <>
      {/* Hero Banner */}
      <div className="relative h-[500px] overflow-hidden">
        <div 
          className="absolute inset-0 transition-opacity duration-1000"
          style={{
            backgroundImage: `url(${bannerImages[currentBanner]})`,
            backgroundSize: 'cover',
            backgroundPosition: 'center'
          }}
        >
          <div className="absolute inset-0 bg-black bg-opacity-40 flex items-center justify-center">
            <div className="text-center text-white px-4">
              <h1 className="text-4xl md:text-6xl font-bold mb-4">
                Empowering Our Community
              </h1>
              <p className="text-xl md:text-2xl mb-8">
                Building stronger connections through education and support
              </p>
              <div className="space-x-4">
                <Link to="/programs" className="bg-orange-500 hover:bg-orange-600 text-white px-8 py-3 rounded-full text-lg font-semibold transition-colors inline-block">
                  Our Programs
                </Link>
                <Link to="/donate" className="bg-transparent border-2 border-white hover:bg-white hover:text-[#2C3E50] text-white px-8 py-3 rounded-full text-lg font-semibold transition-colors inline-block">
                  Support Us
                </Link>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Programs Section */}
      <section className="py-16 bg-gray-50">
        <div className="container mx-auto px-4">
          <h2 className="text-3xl font-bold text-[#2C3E50] text-center mb-12">
            Our Programs
          </h2>
          <div className="grid md:grid-cols-3 gap-8">
            {programs.map((program, index) => (
              <div key={index} className="bg-white p-6 rounded-lg shadow-md hover:shadow-lg transition-shadow">
                <div className="text-orange-500 mb-4">{program.icon}</div>
                <h3 className="text-xl font-semibold text-[#2C3E50] mb-3">
                  {program.title}
                </h3>
                <p className="text-gray-600 mb-4">{program.description}</p>
                <Link to={program.link} className="text-orange-500 hover:text-orange-600 font-medium inline-flex items-center">
                  Learn More
                  <svg className="w-4 h-4 ml-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                  </svg>
                </Link>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* News & Events */}
      <section className="py-16">
        <div className="container mx-auto px-4">
          <h2 className="text-3xl font-bold text-[#2C3E50] text-center mb-12">
            Upcoming Events
          </h2>
          <div className="grid md:grid-cols-2 gap-8">
            {events.map((event, index) => (
              <div key={index} className="bg-gray-50 p-6 rounded-lg">
                <div className="text-orange-500 font-medium mb-2">{event.date}</div>
                <h3 className="text-xl font-semibold text-[#2C3E50] mb-3">
                  {event.title}
                </h3>
                <div className="flex items-center text-gray-600 mb-3">
                  <Clock size={18} className="mr-2" />
                  {event.time}
                </div>
                <div className="flex items-center text-gray-600 mb-4">
                  <MapPin size={18} className="mr-2" />
                  {event.location}
                </div>
                <p className="text-gray-600 mb-4">{event.description}</p>
                <Link to="/events" className="text-orange-500 hover:text-orange-600 font-medium inline-flex items-center">
                  Learn More
                  <svg className="w-4 h-4 ml-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                  </svg>
                </Link>
              </div>
            ))}
          </div>
          <div className="text-center mt-8">
            <Link to="/events" className="inline-block bg-orange-500 hover:bg-orange-600 text-white px-8 py-3 rounded-full text-lg font-semibold transition-colors">
              View All Events
            </Link>
          </div>
        </div>
      </section>
    </>
  );
}