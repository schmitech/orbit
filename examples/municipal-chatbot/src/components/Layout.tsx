import React from 'react';
import { Link, Outlet } from 'react-router-dom';
import { Menu, X, Search, Bell, Globe, Sun } from 'lucide-react';
import AlertBanner from './AlertBanner';

const Layout: React.FC = () => {
  const [isMenuOpen, setIsMenuOpen] = React.useState(false);

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-blue-900 text-white">
        <div className="container mx-auto px-4">
          <div className="flex items-center justify-between h-16">
            <Link to="/" className="font-bold text-xl">City of Maple</Link>
            
            {/* Desktop Navigation */}
            <nav className="hidden md:flex space-x-8">
              <Link to="/services" className="hover:text-blue-200">City Services</Link>
              <Link to="/government" className="hover:text-blue-200">Government</Link>
              <Link to="/residents" className="hover:text-blue-200">Residents</Link>
              <Link to="/business" className="hover:text-blue-200">Business</Link>
            </nav>

            {/* Utility Icons */}
            <div className="hidden md:flex items-center space-x-4">
              <button aria-label="Search" className="p-2 hover:bg-blue-800 rounded-full">
                <Search size={20} />
              </button>
              <button aria-label="Notifications" className="p-2 hover:bg-blue-800 rounded-full">
                <Bell size={20} />
              </button>
              <button aria-label="Language" className="p-2 hover:bg-blue-800 rounded-full">
                <Globe size={20} />
              </button>
            </div>

            {/* Mobile Menu Button */}
            <button 
              className="md:hidden p-2"
              onClick={() => setIsMenuOpen(!isMenuOpen)}
              aria-label="Toggle menu"
            >
              {isMenuOpen ? <X size={24} /> : <Menu size={24} />}
            </button>
          </div>
        </div>

        {/* Mobile Menu */}
        {isMenuOpen && (
          <div className="md:hidden">
            <div className="px-2 pt-2 pb-3 space-y-1">
              <Link to="/services" className="block px-3 py-2 hover:bg-blue-800">City Services</Link>
              <Link to="/government" className="block px-3 py-2 hover:bg-blue-800">Government</Link>
              <Link to="/residents" className="block px-3 py-2 hover:bg-blue-800">Residents</Link>
              <Link to="/business" className="block px-3 py-2 hover:bg-blue-800">Business</Link>
            </div>
          </div>
        )}
      </header>

      {/* Alert Banner */}
      <AlertBanner />

      {/* Main Content */}
      <main>
        <Outlet />
      </main>

      {/* Footer */}
      <footer className="bg-gray-900 text-white mt-20">
        <div className="container mx-auto px-4 py-12">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-8">
            <div>
              <h3 className="text-lg font-semibold mb-4">Contact Us</h3>
              <p>City Hall</p>
              <p>123 Main Street</p>
              <p>Maple, ST 12345</p>
              <p>Phone: (555) 123-4567</p>
            </div>
            <div>
              <h3 className="text-lg font-semibold mb-4">Quick Links</h3>
              <ul className="space-y-2">
                <li><Link to="/services" className="hover:text-blue-300">City Services</Link></li>
                <li><Link to="/pay" className="hover:text-blue-300">Online Payments</Link></li>
                <li><Link to="/report" className="hover:text-blue-300">Report an Issue</Link></li>
                <li><Link to="/jobs" className="hover:text-blue-300">Employment</Link></li>
              </ul>
            </div>
            <div>
              <h3 className="text-lg font-semibold mb-4">Connect With Us</h3>
              <div className="flex space-x-4">
                <a href="#" className="hover:text-blue-300">Facebook</a>
                <a href="#" className="hover:text-blue-300">Twitter</a>
                <a href="#" className="hover:text-blue-300">Instagram</a>
              </div>
            </div>
            <div>
              <h3 className="text-lg font-semibold mb-4">Newsletter</h3>
              <form className="space-y-4">
                <input
                  type="email"
                  placeholder="Enter your email"
                  className="w-full px-4 py-2 rounded bg-gray-800 text-white"
                />
                <button
                  type="submit"
                  className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700"
                >
                  Subscribe
                </button>
              </form>
            </div>
          </div>
          <div className="mt-8 pt-8 border-t border-gray-800 text-center">
            <p>&copy; 2024 City of Maple. All rights reserved.</p>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default Layout;