import React, { useState } from 'react';
import { Activity } from '../types';
import { format } from 'date-fns';
import { Calendar, MapPin, Clock, DollarSign, Users, Tag, ChevronRight, Plus, Minus, Info, Link } from 'lucide-react';
import clsx from 'clsx';

interface ActivityCardProps {
  activity: Activity;
  viewMode: 'list' | 'grid';
}

const ActivityCard: React.FC<ActivityCardProps> = ({ activity, viewMode }) => {
  const [expanded, setExpanded] = useState(false);

  const statusColors = {
    Open: 'bg-green-100 text-green-800 border border-green-200',
    Waitlist: 'bg-accent-100 text-accent-800 border border-accent-200',
    Full: 'bg-red-100 text-red-800 border border-red-200'
  };

  const formatDate = (date: Date) => {
    return format(date, 'MMM d, yyyy');
  };

  const toggleExpand = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setExpanded(!expanded);
  };

  if (viewMode === 'list') {
    return (
      <div className="bg-white rounded-xl shadow-soft p-5 hover:shadow-card transition-shadow border border-neutral-100">
        <div className="flex flex-col md:flex-row">
          <div className="md:w-2/3">
            <div className="flex justify-between items-start">
              <h3 className="text-lg font-semibold text-primary-800 font-heading">{activity.activityName}</h3>
              <span className={`text-xs font-medium px-2.5 py-1 rounded-full ${statusColors[activity.status]}`}>
                {activity.status}
              </span>
            </div>
            
            <div className="mt-3 text-sm text-neutral-600 space-y-1.5">
              <p className="flex items-center">
                <MapPin size={16} className="mr-2 text-primary-500 flex-shrink-0" />
                {activity.location}
              </p>
              <p className="flex items-center">
                <Calendar size={16} className="mr-2 text-primary-500 flex-shrink-0" />
                {formatDate(activity.startDate)} - {formatDate(activity.endDate)}
              </p>
              <p className="flex items-center">
                <Clock size={16} className="mr-2 text-primary-500 flex-shrink-0" />
                {activity.time} ({activity.daysOfWeek.join(', ')})
              </p>
            </div>
            
            <div className="mt-3 flex flex-wrap gap-1.5 items-center">
              <span className="badge badge-primary">
                {activity.category}
              </span>
              <span className="badge badge-neutral">
                {activity.ageGroup}
              </span>
              <div className="flex items-center">
                {activity.language.map(lang => (
                  <span key={lang} className="badge badge-neutral mr-1">
                    {lang}
                  </span>
                ))}
                <button 
                  onClick={toggleExpand}
                  className={clsx(
                    "ml-1 p-1 rounded-full transition-colors",
                    expanded 
                      ? "bg-primary-100 text-primary-700" 
                      : "bg-neutral-100 text-neutral-500 hover:bg-neutral-200"
                  )}
                  aria-label={expanded ? "Show less" : "Show more"}
                >
                  {expanded ? <Minus size={14} /> : <Plus size={14} />}
                </button>
              </div>
            </div>
            
            {/* Expandable content */}
            <div 
              className={clsx(
                "overflow-hidden transition-all duration-300 ease-in-out",
                expanded ? "max-h-96 opacity-100 mt-4" : "max-h-0 opacity-0"
              )}
            >
              <div className="bg-neutral-50 p-4 rounded-lg border border-neutral-200">
                <h4 className="font-medium text-primary-700 mb-2 flex items-center">
                  <Info size={16} className="mr-2" />
                  Activity Details
                </h4>
                <p className="text-sm text-neutral-700 mb-3">{activity.description}</p>
                
                <div className="space-y-2">
                  <h5 className="text-xs font-medium text-neutral-500 uppercase">Related Links</h5>
                  <div className="space-y-1">
                    <a href="#" className="text-sm text-primary-600 hover:text-primary-800 flex items-center">
                      <Link size={14} className="mr-1.5" />
                      View facility information
                    </a>
                    <a href="#" className="text-sm text-primary-600 hover:text-primary-800 flex items-center">
                      <Link size={14} className="mr-1.5" />
                      Program policies
                    </a>
                    <a href="#" className="text-sm text-primary-600 hover:text-primary-800 flex items-center">
                      <Link size={14} className="mr-1.5" />
                      Cancellation policy
                    </a>
                  </div>
                </div>
              </div>
            </div>
          </div>
          
          <div className="md:w-1/3 mt-4 md:mt-0 md:border-l md:pl-5 flex flex-col justify-between">
            <div>
              <p className="flex items-center text-sm text-neutral-600 mb-1">
                <Tag size={14} className="mr-1.5 text-neutral-500" />
                Code: <span className="font-medium ml-1">{activity.activityCode}</span>
              </p>
              <p className="flex items-center text-xl font-bold text-neutral-800 mb-2">
                <DollarSign size={18} className="text-primary-600" />
                {activity.price.toFixed(2)}
              </p>
              <p className="flex items-center text-sm text-neutral-600">
                <Users size={16} className="mr-1.5 text-neutral-500" />
                {activity.spotsAvailable} spots available
              </p>
            </div>
            
            <button className="mt-4 btn btn-primary group">
              Register
              <ChevronRight size={16} className="ml-1 transition-transform group-hover:translate-x-0.5" />
            </button>
          </div>
        </div>
      </div>
    );
  }
  
  // Grid view
  return (
    <div className="bg-white rounded-xl shadow-soft overflow-hidden hover:shadow-card transition-shadow h-full flex flex-col border border-neutral-100">
      <div className="p-4 flex-grow">
        <div className="flex justify-between items-start">
          <h3 className="text-md font-semibold text-primary-800 line-clamp-2 font-heading">{activity.activityName}</h3>
          <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${statusColors[activity.status]}`}>
            {activity.status}
          </span>
        </div>
        
        <div className="mt-3 text-xs text-neutral-600 space-y-1.5">
          <p className="flex items-center">
            <MapPin size={14} className="mr-1.5 text-primary-500 flex-shrink-0" />
            <span className="truncate">{activity.location}</span>
          </p>
          <p className="flex items-center">
            <Calendar size={14} className="mr-1.5 text-primary-500 flex-shrink-0" />
            <span>{formatDate(activity.startDate)} - {formatDate(activity.endDate)}</span>
          </p>
          <p className="flex items-center">
            <Clock size={14} className="mr-1.5 text-primary-500 flex-shrink-0" />
            <span>{activity.time}</span>
          </p>
        </div>
        
        <div className="mt-3 flex flex-wrap gap-1 items-center">
          <span className="badge badge-primary text-xs px-1.5 py-0.5">
            {activity.category}
          </span>
          <span className="badge badge-neutral text-xs px-1.5 py-0.5">
            {activity.ageGroup.split(' ')[0]}
          </span>
          <div className="flex items-center ml-auto">
            {activity.language.map(lang => (
              <span key={lang} className="badge badge-neutral text-xs px-1.5 py-0.5 mr-1">
                {lang}
              </span>
            ))}
            <button 
              onClick={toggleExpand}
              className={clsx(
                "p-1 rounded-full transition-colors",
                expanded 
                  ? "bg-primary-100 text-primary-700" 
                  : "bg-neutral-100 text-neutral-500 hover:bg-neutral-200"
              )}
              aria-label={expanded ? "Show less" : "Show more"}
            >
              {expanded ? <Minus size={12} /> : <Plus size={12} />}
            </button>
          </div>
        </div>
        
        {/* Expandable content for grid view */}
        <div 
          className={clsx(
            "overflow-hidden transition-all duration-300 ease-in-out",
            expanded ? "max-h-96 opacity-100 mt-3" : "max-h-0 opacity-0"
          )}
        >
          <div className="bg-neutral-50 p-3 rounded-lg border border-neutral-200 text-xs">
            <p className="text-neutral-700 mb-2">{activity.description}</p>
            
            <div className="space-y-1.5">
              <h5 className="text-2xs font-medium text-neutral-500 uppercase">Related Links</h5>
              <div className="space-y-1">
                <a href="#" className="text-xs text-primary-600 hover:text-primary-800 flex items-center">
                  <Link size={10} className="mr-1" />
                  View facility information
                </a>
                <a href="#" className="text-xs text-primary-600 hover:text-primary-800 flex items-center">
                  <Link size={10} className="mr-1" />
                  Program policies
                </a>
              </div>
            </div>
          </div>
        </div>
      </div>
      
      <div className="bg-neutral-50 p-3 mt-auto border-t border-neutral-100">
        <div className="flex justify-between items-center">
          <p className="flex items-center text-sm font-bold text-neutral-800">
            <DollarSign size={16} className="text-primary-600" />
            {activity.price.toFixed(2)}
          </p>
          <p className="text-xs text-neutral-500">
            Code: {activity.activityCode}
          </p>
        </div>
        <button className="mt-2 w-full btn btn-primary text-sm py-1.5 group">
          Register
          <ChevronRight size={14} className="ml-1 transition-transform group-hover:translate-x-0.5" />
        </button>
      </div>
    </div>
  );
};

export default ActivityCard;