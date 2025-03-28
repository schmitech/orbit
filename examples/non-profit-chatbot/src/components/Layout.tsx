import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { Menu, X, Facebook, Twitter, Instagram, Mail, Phone, MapPin } from 'lucide-react';

const programs = [
  {
    title: "Youth Programs",
    link: "/programs/youth"
  },
  {
    title: "Senior Services",
    link: "/programs/seniors"
  },
  {
    title: "Adult Education",
    link: "/programs/adult-education"
  },
  {
    title: "Family Services",
    link: "/programs/family"
  },
  {
    title: "Financial Literacy",
    link: "/programs/financial"
  },
  {
    title: "Community Outreach",
    link: "/programs/outreach"
  }
];

const quickLinks = [
  { title: "Programs", link: "/programs" },
  { title: "Events Calendar", link: "/events" },
  { title: "Volunteer", link: "/volunteer" },
  { title: "Donate", link: "/donate" },
  { title: "Resources", link: "/resources" },
  { title: "Newsletter", link: "/newsletter" }
];

const hours = [
  { day: "Monday - Friday", hours: "8:00 AM - 8:00 PM" },
  { day: "Saturday", hours: "9:00 AM - 5:00 PM" },
  { day: "Sunday", hours: "Closed" }
];

export default function Layout({ children }: { children: React.ReactNode }) {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  return (
    <div className="min-h-screen bg-white">
      {/* Header */}
      <div className="bg-[#2C3E50] text-white">
        <div className="container mx-auto px-4 py-2">
          <div className="flex justify-between items-center text-sm">
            <div className="flex items-center space-x-4">
              <span className="flex items-center">
                <Phone size={16} className="mr-1" />
                (555) 123-4567
              </span>
              <span className="flex items-center">
                <Mail size={16} className="mr-1" />
                info@democenter.org
              </span>
            </div>
            <div className="flex items-center space-x-4">
              <Link to="/donate" className="hover:text-orange-400">Donate</Link>
              <Link to="/volunteer" className="hover:text-orange-400">Volunteer</Link>
            </div>
          </div>
        </div>
      </div>
      
      <header className="bg-white shadow-md">
        <div className="container mx-auto px-4">
          <div className="flex justify-between items-center h-20">
            <Link to="/" className="text-2xl font-bold text-[#2C3E50]">Demo Community Center</Link>
            <nav className="hidden md:flex space-x-6">
              <Link to="/" className="text-gray-700 hover:text-orange-500">Home</Link>
              <div className="relative group">
                <Link to="/programs" className="text-gray-700 hover:text-orange-500">Programs</Link>
                <div className="absolute hidden group-hover:block w-48 bg-white shadow-lg py-2 z-10">
                  {programs.map((program, index) => (
                    <Link
                      key={index}
                      to={program.link}
                      className="block px-4 py-2 text-sm text-gray-700 hover:bg-orange-50 hover:text-orange-500"
                    >
                      {program.title}
                    </Link>
                  ))}
                </div>
              </div>
              <Link to="/events" className="text-gray-700 hover:text-orange-500">Events</Link>
              <Link to="/about" className="text-gray-700 hover:text-orange-500">About Us</Link>
              <Link to="/contact" className="text-gray-700 hover:text-orange-500">Contact</Link>
            </nav>
            <button 
              className="md:hidden"
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            >
              {mobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
            </button>
          </div>
        </div>
        
        {/* Mobile Menu */}
        {mobileMenuOpen && (
          <div className="md:hidden bg-white border-t pb-4">
            <nav className="flex flex-col space-y-4 px-4">
              <Link to="/" className="text-gray-700 hover:text-orange-500">Home</Link>
              <Link to="/programs" className="text-gray-700 hover:text-orange-500">Programs</Link>
              <Link to="/events" className="text-gray-700 hover:text-orange-500">Events</Link>
              <Link to="/about" className="text-gray-700 hover:text-orange-500">About Us</Link>
              <Link to="/contact" className="text-gray-700 hover:text-orange-500">Contact</Link>
            </nav>
          </div>
        )}
      </header>

      {/* Main Content */}
      <main>
        {children}
      </main>

      {/* Footer */}
      <footer className="bg-[#2C3E50] text-white py-12">
        <div className="container mx-auto px-4">
          <div className="grid md:grid-cols-4 gap-8">
            <div>
              <h3 className="text-xl font-bold mb-4">Demo Community Center</h3>
              <p className="text-gray-300 mb-4">
                Serving our community with educational programs, social services, and enrichment activities.
              </p>
              <div className="flex space-x-4">
                <a href="#" className="text-gray-300 hover:text-orange-400">
                  <Facebook size={24} />
                </a>
                <a href="#" className="text-gray-300 hover:text-orange-400">
                  <Twitter size={24} />
                </a>
                <a href="#" className="text-gray-300 hover:text-orange-400">
                  <Instagram size={24} />
                </a>
              </div>
            </div>
            <div>
              <h4 className="text-lg font-semibold mb-4">Quick Links</h4>
              <ul className="space-y-2">
                {quickLinks.map((link, index) => (
                  <li key={index}>
                    <Link to={link.link} className="text-gray-300 hover:text-orange-400">
                      {link.title}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h4 className="text-lg font-semibold mb-4">Hours of Operation</h4>
              <ul className="space-y-2">
                {hours.map((schedule, index) => (
                  <li key={index} className="text-gray-300">
                    <span className="font-medium">{schedule.day}:</span>
                    <br />
                    {schedule.hours}
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h4 className="text-lg font-semibold mb-4">Contact Us</h4>
              <ul className="space-y-2">
                <li className="flex items-center gap-2">
                  <MapPin size={18} />
                  <span className="text-gray-300">123 Community Ave<br />Demo City, ST 12345</span>
                </li>
                <li className="flex items-center gap-2">
                  <Phone size={18} />
                  <span className="text-gray-300">(555) 123-4567</span>
                </li>
                <li className="flex items-center gap-2">
                  <Mail size={18} />
                  <span className="text-gray-300">info@democenter.org</span>
                </li>
              </ul>
            </div>
          </div>
          <div className="border-t border-gray-600 mt-8 pt-8 text-center text-gray-300">
            <p>© 2024 City Community Center. This is a demonstration website.</p>
          </div>
        </div>
      </footer>
    </div>
  );
}