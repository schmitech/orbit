import React from 'react';
import { AlertTriangle, X } from 'lucide-react';

const AlertBanner: React.FC = () => {
  const [alerts] = React.useState([
    {
      id: '1',
      type: 'emergency',
      message: 'Severe weather warning in effect. Please stay informed and follow safety guidelines.',
    }
  ]);
  const [dismissedAlerts, setDismissedAlerts] = React.useState<string[]>([]);

  const handleDismiss = (id: string) => {
    setDismissedAlerts([...dismissedAlerts, id]);
  };

  const visibleAlerts = alerts.filter(alert => !dismissedAlerts.includes(alert.id));

  if (visibleAlerts.length === 0) return null;

  return (
    <div className="bg-red-600 text-white">
      {visibleAlerts.map(alert => (
        <div key={alert.id} className="container mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <AlertTriangle size={20} />
            <span>{alert.message}</span>
          </div>
          <button
            onClick={() => handleDismiss(alert.id)}
            className="p-1 hover:bg-red-700 rounded-full"
            aria-label="Dismiss alert"
          >
            <X size={16} />
          </button>
        </div>
      ))}
    </div>
  );
};

export default AlertBanner;