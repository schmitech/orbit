import React from 'react';
import type { NewsItem } from '../types';
import { format } from 'date-fns';

const NewsSection: React.FC = () => {
  const [news] = React.useState<NewsItem[]>([
    {
      id: '1',
      title: 'New Community Center Opening Soon',
      summary: 'The state-of-the-art facility will open its doors next month, featuring recreational spaces, meeting rooms, and more.',
      date: new Date('2024-03-15'),
      imageUrl: 'https://images.unsplash.com/photo-1497366216548-37526070297c?auto=format&fit=crop&q=80&w=1200',
    },
    {
      id: '2',
      title: 'Road Improvement Project Updates',
      summary: 'Major progress on downtown street renovations. Expected completion ahead of schedule.',
      date: new Date('2024-03-14'),
      imageUrl: 'https://images.unsplash.com/photo-1516216628859-9c66c0152f0f?auto=format&fit=crop&q=80&w=1200',
    },
  ]);

  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-bold">Latest News</h2>
        <button className="text-blue-600 hover:text-blue-800">View All News</button>
      </div>
      <div className="space-y-6">
        {news.map(item => (
          <div key={item.id} className="border-b pb-6 last:border-b-0 last:pb-0">
            <div className="flex flex-col md:flex-row md:space-x-6">
              {item.imageUrl && (
                <div className="flex-shrink-0 mb-4 md:mb-0">
                  <img
                    src={item.imageUrl}
                    alt={item.title}
                    className="w-full md:w-48 h-32 object-cover rounded-lg"
                  />
                </div>
              )}
              <div>
                <h3 className="text-lg font-semibold mb-2">{item.title}</h3>
                <p className="text-gray-600 mb-2">{item.summary}</p>
                <p className="text-sm text-gray-500">
                  {format(item.date, 'MMMM d, yyyy')}
                </p>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default NewsSection;