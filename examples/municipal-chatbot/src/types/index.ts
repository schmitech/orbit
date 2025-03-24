export interface Alert {
  id: string;
  type: 'emergency' | 'info' | 'warning';
  message: string;
  date: Date;
}

export interface Event {
  id: string;
  title: string;
  date: Date;
  location: string;
  description: string;
}

export interface NewsItem {
  id: string;
  title: string;
  summary: string;
  date: Date;
  imageUrl?: string;
}

export interface WeatherInfo {
  temperature: number;
  condition: string;
  icon: string;
}