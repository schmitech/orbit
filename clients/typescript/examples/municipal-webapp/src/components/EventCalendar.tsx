import React from 'react';
import { Calendar } from 'lucide-react';
import { format } from 'date-fns';
import type { Event } from '../types';

const EventCalendar: React.FC = () => {
  const [events] = React.useState<Event[]>([
    {
      id: '1',
      title: 'City Council Meeting',
      date: new Date('2024-03-20T18:00:00'),
      location: 'City Hall - Council Chambers',
      description: 'Regular city council meeting open to the public',
    },
    {
      id: '2',
      title: 'Community Clean-up Day',
      date: new Date('2024-03-23T09:00:00'),
      location: 'Central Park',
      description: 'Join us for our annual spring cleaning event',
    },
  ]);

  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-bold">Upcoming Events</h2>
        <button className="text-blue-600 hover:text-blue-800">View All</button>
      </div>
      <div className="space-y-4">
        {events.map(event => (
          <div key={event.id} className="border-b pb-4 last:border-b-0 last:pb-0">
            <div className="flex items-start space-x-4">
              <div className="flex-shrink-0">
                <Calendar className="w-5 h-5 text-blue-600" />
              </div>
              <div>
                <h3 className="font-semibold">{event.title}</h3>
                <p className="text-sm text-gray-600">
                  {format(event.date, 'MMMM d, yyyy h:mm a')}
                </p>
                <p className="text-sm text-gray-600">{event.location}</p>
                <p className="text-sm mt-1">{event.description}</p>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default EventCalendar;