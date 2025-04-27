import React from 'react';
import { Cloud, Sun, CloudRain } from 'lucide-react';
import type { WeatherInfo } from '../types';

const WeatherWidget: React.FC = () => {
  const [weather] = React.useState<WeatherInfo>({
    temperature: 22,
    condition: 'Partly Cloudy',
    icon: 'cloud',
  });

  const getWeatherIcon = () => {
    switch (weather.icon) {
      case 'sun':
        return <Sun className="w-8 h-8" />;
      case 'rain':
        return <CloudRain className="w-8 h-8" />;
      default:
        return <Cloud className="w-8 h-8" />;
    }
  };

  return (
    <div className="bg-white rounded-lg shadow-md p-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-3">
          {getWeatherIcon()}
          <div>
            <p className="text-2xl font-bold">{weather.temperature}°C</p>
            <p className="text-gray-600">{weather.condition}</p>
          </div>
        </div>
        <button className="text-blue-600 hover:text-blue-800">
          Full Forecast
        </button>
      </div>
    </div>
  );
};

export default WeatherWidget;