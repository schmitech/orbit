export type ActivityStatus = 'Open' | 'Waitlist' | 'Full';
export type Language = 'English' | 'French';
export type DayOfWeek = 'Monday' | 'Tuesday' | 'Wednesday' | 'Thursday' | 'Friday' | 'Saturday' | 'Sunday';

export interface Activity {
  id: string;
  activityName: string;
  category: string;
  location: string;
  ageGroup: string;
  startDate: Date;
  endDate: Date;
  time: string;
  price: number;
  spotsAvailable: number;
  activityCode: string;
  description: string;
  language: Language[];
  status: ActivityStatus;
  daysOfWeek: DayOfWeek[];
}

export interface FilterState {
  keyword: string;
  categories: string[];
  locations: string[];
  ageGroups: string[];
  daysOfWeek: DayOfWeek[];
  availability: ActivityStatus[];
  language: Language[];
}