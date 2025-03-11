import * as fs from 'fs';
import * as path from 'path';
import { faker } from '@faker-js/faker';
import { Activity, ActivityStatus, DayOfWeek, Language } from '../types';

const categories = [
  'Swimming', 'Fitness', 'Arts & Crafts', 'Dance', 'Sports', 
  'Martial Arts', 'Music', 'Cooking', 'Yoga', 'Skating',
  'Hockey', 'Basketball', 'Soccer', 'Tennis', 'Gymnastics'
];

const locations = [
  'Recreation Programs Complex', 'Nepean Sportsplex', 
  'Richcraft Recreation Complex', 'Kanata Recreation Complex',
  'Minto Recreation Complex', 'Pinecrest Recreation Complex',
  'Walter Baker Sports Centre', 'Jim Durrell Recreation Centre',
  'Plant Recreation Centre', 'Carleton Heights Community Centre',
  'St. Laurent Complex', 'Hintonburg Community Centre'
];

const ageGroups = [
  'Preschool (0-5 yrs)', 'Children (6-12 yrs)', 'Youth (13-17 yrs)',
  'Adult (18-54 yrs)', 'Older Adult (55+ yrs)', 'All Ages'
];

const daysOfWeek: DayOfWeek[] = [
  'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'
];

const statuses: ActivityStatus[] = ['Open', 'Waitlist', 'Full'];
const languages: Language[] = ['English', 'French'];

const generateMockActivities = (count: number): Activity[] => {
  const activities: Activity[] = [];

  for (let i = 0; i < count; i++) {
    const startDate = faker.date.future();
    const endDate = new Date(startDate);
    endDate.setDate(endDate.getDate() + faker.number.int({ min: 28, max: 84 }));
    
    const startHour = faker.number.int({ min: 8, max: 19 });
    const endHour = startHour + faker.number.int({ min: 1, max: 3 });
    const time = `${startHour}:00 - ${endHour}:00`;
    
    // Generate 1-3 random days of the week
    const activityDays: DayOfWeek[] = [];
    const numDays = faker.number.int({ min: 1, max: 3 });
    const shuffledDays = [...daysOfWeek].sort(() => 0.5 - Math.random());
    for (let j = 0; j < numDays; j++) {
      activityDays.push(shuffledDays[j]);
    }
    
    // Determine language (English, French, or both)
    const languageOptions: Language[] = [];
    const languageChoice = faker.number.int({ min: 1, max: 10 });
    if (languageChoice <= 6) {
      languageOptions.push('English');
    } else if (languageChoice <= 9) {
      languageOptions.push('French');
    } else {
      languageOptions.push('English', 'French');
    }
    
    // Select a single category for both the activity name and category field
    const selectedCategory = faker.helpers.arrayElement(categories);
    
    activities.push({
      id: faker.string.uuid(),
      activityName: faker.helpers.arrayElement([
        `${selectedCategory} for Beginners`,
        `Advanced ${selectedCategory}`,
        `${selectedCategory} Workshop`,
        `${selectedCategory} Class`,
        `${selectedCategory} Program`,
        `Learn to ${selectedCategory}`,
        `${selectedCategory} Fundamentals`,
      ]),
      category: selectedCategory,
      location: faker.helpers.arrayElement(locations),
      ageGroup: faker.helpers.arrayElement(ageGroups),
      startDate,
      endDate,
      time,
      price: parseFloat(faker.finance.amount(20, 300, 2)),
      spotsAvailable: faker.number.int({ min: 0, max: 30 }),
      activityCode: faker.string.alphanumeric(6).toUpperCase(),
      description: faker.lorem.paragraph(),
      language: languageOptions,
      status: faker.helpers.arrayElement(statuses),
      daysOfWeek: activityDays,
    });
  }

  return activities;
};

// Get the number of records from command line arguments
const args = process.argv.slice(2);
const count = args.length > 0 ? parseInt(args[0], 10) : 120;

if (isNaN(count)) {
  console.error('Error: Please provide a valid number as an argument');
  process.exit(1);
}

console.log(`Generating ${count} mock activities...`);

// Generate the mock activities
const activities = generateMockActivities(count);

// Create the output directory if it doesn't exist
const outputDir = path.resolve(process.cwd(), 'data');
if (!fs.existsSync(outputDir)) {
  fs.mkdirSync(outputDir, { recursive: true });
}

// Write the activities to a JSON file
const outputPath = path.resolve(outputDir, 'activities.json');
fs.writeFileSync(outputPath, JSON.stringify(activities, null, 2));

console.log(`Successfully generated ${count} activities and saved to ${outputPath}`); 