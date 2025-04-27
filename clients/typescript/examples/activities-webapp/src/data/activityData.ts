import { Activity } from '../types';
import activitiesData from '../../data/activities.json';

// Convert the JSON data to Activity objects with proper date parsing
export const activities: Activity[] = activitiesData.map(item => ({
  ...item,
  startDate: new Date(item.startDate),
  endDate: new Date(item.endDate)
})) as Activity[];

// Extract unique values for filters
export const uniqueCategories = [...new Set(activities.map(a => a.category))].sort();
export const uniqueLocations = [...new Set(activities.map(a => a.location))].sort();
export const uniqueAgeGroups = [...new Set(activities.map(a => a.ageGroup))].sort(); 