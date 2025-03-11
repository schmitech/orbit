import React, { useState, useEffect } from 'react';
import MobileChatWidget from '../components/ChatWidget/mobile/MobileChatWidget';
import clsx from 'clsx';
import { Link } from 'react-router-dom';
import { Home } from 'lucide-react';

type DeviceType = 'iphone-se' | 'iphone-12' | 'iphone-16' | 'pixel' | 'galaxy';

const MobileDemo: React.FC = () => {
  const [deviceType, setDeviceType] = useState<DeviceType>('iphone-16');

  // Update URL hash when device type changes
  useEffect(() => {
    window.location.hash = deviceType;
  }, [deviceType]);

  // Set device type from URL hash on initial load
  useEffect(() => {
    const hash = window.location.hash.substring(1);
    if (hash && ['iphone-se', 'iphone-12', 'iphone-16', 'pixel', 'galaxy'].includes(hash as DeviceType)) {
      setDeviceType(hash as DeviceType);
    }
  }, []);

  return (
    <div className="p-8 bg-gray-100 min-h-screen">
      <div className="max-w-7xl mx-auto">
        <div className="flex justify-between items-center mb-6">
          <h1 className="text-3xl font-bold">Mobile Chat Demo</h1>
          <Link to="/" className="flex items-center text-primary-600 hover:text-primary-800">
            <Home size={20} className="mr-1" />
            <span>Back to Home</span>
          </Link>
        </div>
        
        <div className="mb-6 flex flex-wrap gap-2">
          <button 
            onClick={() => setDeviceType('iphone-se')}
            className={clsx(
              "px-4 py-2 rounded",
              deviceType === 'iphone-se' 
                ? "bg-primary-600 text-white" 
                : "bg-white text-gray-700"
            )}
          >
            iPhone SE
          </button>
          <button 
            onClick={() => setDeviceType('iphone-12')}
            className={clsx(
              "px-4 py-2 rounded",
              deviceType === 'iphone-12' 
                ? "bg-primary-600 text-white" 
                : "bg-white text-gray-700"
            )}
          >
            iPhone 12
          </button>
          <button 
            onClick={() => setDeviceType('iphone-16')}
            className={clsx(
              "px-4 py-2 rounded",
              deviceType === 'iphone-16' 
                ? "bg-primary-600 text-white" 
                : "bg-white text-gray-700"
            )}
          >
            iPhone 16
          </button>
          <button 
            onClick={() => setDeviceType('pixel')}
            className={clsx(
              "px-4 py-2 rounded",
              deviceType === 'pixel' 
                ? "bg-primary-600 text-white" 
                : "bg-white text-gray-700"
            )}
          >
            Pixel
          </button>
          <button 
            onClick={() => setDeviceType('galaxy')}
            className={clsx(
              "px-4 py-2 rounded",
              deviceType === 'galaxy' 
                ? "bg-primary-600 text-white" 
                : "bg-white text-gray-700"
            )}
          >
            Galaxy
          </button>
        </div>
        
        <div className="flex justify-center">
          <div className={clsx(
            "mobile-device-frame",
            {
              'iphone-se-frame': deviceType === 'iphone-se',
              'iphone-12-frame': deviceType === 'iphone-12',
              'iphone-16-frame': deviceType === 'iphone-16',
              'pixel-frame': deviceType === 'pixel',
              'galaxy-frame': deviceType === 'galaxy',
            }
          )}>
            <div className="speaker"></div>
            <div className="power-button"></div>
            <div className="volume-buttons"></div>
            <div className="mobile-device-content">
              <MobileChatWidget />
            </div>
            <div className="mobile-device-home-button"></div>
          </div>
        </div>
        
        <div className="mt-8 text-center text-gray-500">
          <p>This is a demonstration of how the chat widget would appear on a mobile device.</p>
        </div>
      </div>
    </div>
  );
};

export default MobileDemo; 