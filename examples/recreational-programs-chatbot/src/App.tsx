import React, { useState, useEffect } from 'react';
import FilterPanel from './components/FilterPanel';
import ActivityList from './components/ActivityList';
import ChatWidget from './components/ChatWidget/ChatWidget';
import { activities as activityData } from './data/activityData';
import { Activity, FilterState } from './types';
import { Info, Sparkles, MapPin, Calendar, Users } from 'lucide-react';
import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom';
import MobileDemo from './pages/mobile-demo';

function App() {
  const [activities, setActivities] = useState<Activity[]>([]);
  const [filteredActivities, setFilteredActivities] = useState<Activity[]>([]);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState<FilterState>({
    keyword: '',
    categories: [],
    locations: [],
    ageGroups: [],
    daysOfWeek: [],
    availability: [],
    language: []
  });

  // Simulate loading data
  useEffect(() => {
    const timer = setTimeout(() => {
      setActivities(activityData);
      setFilteredActivities(activityData);
      setLoading(false);
    }, 800);

    return () => clearTimeout(timer);
  }, []);

  // Apply filters when they change
  useEffect(() => {
    if (activities.length === 0) return;

    setLoading(true);
    
    // Simulate filtering delay
    const timer = setTimeout(() => {
      const filtered = activities.filter(activity => {
        // Keyword search
        if (filters.keyword && !matchesKeyword(activity, filters.keyword)) {
          return false;
        }
        
        // Category filter
        if (filters.categories.length > 0 && !filters.categories.includes(activity.category)) {
          return false;
        }
        
        // Location filter
        if (filters.locations.length > 0 && !filters.locations.includes(activity.location)) {
          return false;
        }
        
        // Age group filter
        if (filters.ageGroups.length > 0 && !filters.ageGroups.includes(activity.ageGroup)) {
          return false;
        }
        
        // Days of week filter
        if (filters.daysOfWeek.length > 0 && !activity.daysOfWeek.some(day => filters.daysOfWeek.includes(day))) {
          return false;
        }
        
        // Availability filter
        if (filters.availability.length > 0 && !filters.availability.includes(activity.status)) {
          return false;
        }
        
        // Language filter
        if (filters.language.length > 0 && !activity.language.some(lang => filters.language.includes(lang))) {
          return false;
        }
        
        return true;
      });
      
      setFilteredActivities(filtered);
      setLoading(false);
    }, 300);
    
    return () => clearTimeout(timer);
  }, [activities, filters]);

  const matchesKeyword = (activity: Activity, keyword: string) => {
    const searchTerm = keyword.toLowerCase();
    return (
      activity.activityName.toLowerCase().includes(searchTerm) ||
      activity.description.toLowerCase().includes(searchTerm) ||
      activity.activityCode.toLowerCase().includes(searchTerm) ||
      activity.category.toLowerCase().includes(searchTerm) ||
      activity.location.toLowerCase().includes(searchTerm)
    );
  };

  return (
    <Router>
      <Routes>
        <Route path="/" element={
          <div className="min-h-screen bg-neutral-50">
            <header className="bg-primary-700 text-white">
              <div className="container mx-auto px-4 py-8">
                <div className="flex items-center mb-2">
                  <Sparkles className="mr-2 text-accent-300" size={24} />
                  <h1 className="text-3xl font-bold font-heading">Recreation Programs</h1>
                </div>
                <p className="text-primary-100 max-w-2xl">Discover and register for exciting programs and activities for all ages and interests</p>
                
                <div className="mt-6 flex flex-wrap gap-4">
                  <div className="flex items-center text-white/80">
                    <MapPin size={18} className="mr-1 text-accent-300" />
                    <span className="text-sm">Multiple Locations</span>
                  </div>
                  <div className="flex items-center text-white/80">
                    <Calendar size={18} className="mr-1 text-accent-300" />
                    <span className="text-sm">Year-round Programs</span>
                  </div>
                  <div className="flex items-center text-white/80">
                    <Users size={18} className="mr-1 text-accent-300" />
                    <span className="text-sm">All Ages Welcome</span>
                  </div>
                  <Link to="/mobile" className="ml-auto text-white bg-primary-800 hover:bg-primary-900 px-4 py-2 rounded-lg text-sm flex items-center">
                    <span>Mobile Version</span>
                  </Link>
                </div>
              </div>
            </header>
            
            <div className="container mx-auto px-4 py-8">
              <div className="bg-accent-50 border-l-4 border-accent-400 p-4 mb-8 rounded-r-lg shadow-soft">
                <div className="flex">
                  <div className="flex-shrink-0">
                    <Info className="h-5 w-5 text-accent-500" />
                  </div>
                  <div className="ml-3">
                    <p className="text-sm text-accent-800">
                        All data has been synthetically generated for demonstration purposes only.
                    </p>
                  </div>
                </div>
              </div>
              
              <div className="flex flex-col lg:flex-row gap-8">
                <div className="lg:w-1/4">
                  <FilterPanel filters={filters} setFilters={setFilters} />
                </div>
                
                <div className="lg:w-3/4">
                  <ActivityList 
                    activities={filteredActivities} 
                    loading={loading} 
                  />
                </div>
              </div>
            </div>
            
            <footer className="bg-gradient-to-r from-neutral-900 to-neutral-800 text-white mt-16 py-12">
              <div className="container mx-auto px-4">
                <div className="flex flex-col md:flex-row justify-between">
                  <div className="mb-8 md:mb-0">
                    <div className="flex items-center mb-3">
                      <Sparkles className="mr-2 text-accent-400" size={20} />
                      <h3 className="text-xl font-semibold font-heading">Recreation Programs</h3>
                    </div>
                    <p className="text-neutral-400 text-sm max-w-md">
                      Enriching lives through quality recreation programs and facilities for all members of our community.
                    </p>
                    
                    <div className="mt-6 flex space-x-4">
                      <a href="#" className="text-neutral-400 hover:text-white transition-colors" aria-label="Facebook">
                        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="currentColor" viewBox="0 0 24 24">
                          <path d="M9 8h-3v4h3v12h5v-12h3.642l.358-4h-4v-1.667c0-.955.192-1.333 1.115-1.333h2.885v-5h-3.808c-3.596 0-5.192 1.583-5.192 4.615v3.385z" />
                        </svg>
                      </a>
                      <a href="#" className="text-neutral-400 hover:text-white transition-colors" aria-label="Twitter">
                        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="currentColor" viewBox="0 0 24 24">
                          <path d="M24 4.557c-.883.392-1.832.656-2.828.775 1.017-.609 1.798-1.574 2.165-2.724-.951.564-2.005.974-3.127 1.195-.897-.957-2.178-1.555-3.594-1.555-3.179 0-5.515 2.966-4.797 6.045-4.091-.205-7.719-2.165-10.148-5.144-1.29 2.213-.669 5.108 1.523 6.574-.806-.026-1.566-.247-2.229-.616-.054 2.281 1.581 4.415 3.949 4.89-.693.188-1.452.232-2.224.084.626 1.956 2.444 3.379 4.6 3.419-2.07 1.623-4.678 2.348-7.29 2.04 2.179 1.397 4.768 2.212 7.548 2.212 9.142 0 14.307-7.721 13.995-14.646.962-.695 1.797-1.562 2.457-2.549z" />
                        </svg>
                      </a>
                      <a href="#" className="text-neutral-400 hover:text-white transition-colors" aria-label="Instagram">
                        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="currentColor" viewBox="0 0 24 24">
                          <path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838c-3.403 0-6.162 2.759-6.162 6.162s2.759 6.163 6.162 6.163 6.162-2.759 6.162-6.163c0-3.403-2.759-6.162-6.162-6.162zm0 10.162c-2.209 0-4-1.79-4-4 0-2.209 1.791-4 4-4s4 1.791 4 4c0 2.21-1.791 4-4 4zm6.406-11.845c-.796 0-1.441.645-1.441 1.44s.645 1.44 1.441 1.44c.795 0 1.439-.645 1.439-1.44s-.644-1.44-1.439-1.44z" />
                        </svg>
                      </a>
                      <a href="#" className="text-neutral-400 hover:text-white transition-colors" aria-label="YouTube">
                        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="currentColor" viewBox="0 0 24 24">
                          <path d="M19.615 3.184c-3.604-.246-11.631-.245-15.23 0-3.897.266-4.356 2.62-4.385 8.816.029 6.185.484 8.549 4.385 8.816 3.6.245 11.626.246 15.23 0 3.897-.266 4.356-2.62 4.385-8.816-.029-6.185-.484-8.549-4.385-8.816zm-10.615 12.816v-8l8 3.993-8 4.007z" />
                        </svg>
                      </a>
                    </div>
                  </div>
                  
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-8">
                    <div>
                      <h4 className="text-base font-semibold mb-4 text-white font-heading">Programs</h4>
                      <ul className="space-y-3 text-sm text-neutral-400">
                        <li><a href="#" className="hover:text-accent-300 transition-colors">Swimming</a></li>
                        <li><a href="#" className="hover:text-accent-300 transition-colors">Fitness</a></li>
                        <li><a href="#" className="hover:text-accent-300 transition-colors">Sports</a></li>
                        <li><a href="#" className="hover:text-accent-300 transition-colors">Arts & Crafts</a></li>
                      </ul>
                    </div>
                    
                    <div>
                      <h4 className="text-base font-semibold mb-4 text-white font-heading">Locations</h4>
                      <ul className="space-y-3 text-sm text-neutral-400">
                        <li><a href="#" className="hover:text-accent-300 transition-colors">Recreation Complexes</a></li>
                        <li><a href="#" className="hover:text-accent-300 transition-colors">Community Centers</a></li>
                        <li><a href="#" className="hover:text-accent-300 transition-colors">Pools</a></li>
                        <li><a href="#" className="hover:text-accent-300 transition-colors">Arenas</a></li>
                      </ul>
                    </div>
                    
                    <div>
                      <h4 className="text-base font-semibold mb-4 text-white font-heading">Help</h4>
                      <ul className="space-y-3 text-sm text-neutral-400">
                        <li><a href="#" className="hover:text-accent-300 transition-colors">Contact Us</a></li>
                        <li><a href="#" className="hover:text-accent-300 transition-colors">FAQs</a></li>
                        <li><a href="#" className="hover:text-accent-300 transition-colors">Accessibility</a></li>
                        <li><a href="#" className="hover:text-accent-300 transition-colors">Terms of Use</a></li>
                      </ul>
                    </div>
                  </div>
                </div>
                
                <div className="mt-12 pt-8 border-t border-neutral-700 text-sm text-neutral-500">
                  <div className="flex flex-col md:flex-row justify-between items-center">
                    <p>© 2025 City of Municipal. All rights reserved. This is a demo recreation.</p>
                    <div className="mt-4 md:mt-0 flex space-x-6">
                      <a href="#" className="text-neutral-500 hover:text-neutral-300 transition-colors">Privacy Policy</a>
                      <a href="#" className="text-neutral-500 hover:text-neutral-300 transition-colors">Terms of Service</a>
                      <a href="#" className="text-neutral-500 hover:text-neutral-300 transition-colors">Cookies</a>
                    </div>
                  </div>
                </div>
              </div>
            </footer>
            
            {/* Chat Widget */}
            <ChatWidget />
          </div>
        } />
        <Route path="/mobile" element={<MobileDemo />} />
      </Routes>
    </Router>
  );
}

export default App;