// This script generates mock data and saves it to a JSON file
import { faker } from '@faker-js/faker';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import OpenAI from 'openai';
import dotenv from 'dotenv';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Load environment variables
dotenv.config();

// Initialize OpenAI API
const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY,
});

// Get the number of records from command line arguments
const args = process.argv.slice(2);
const count = args.length > 0 ? parseInt(args[0], 10) : 120;

if (isNaN(count)) {
  console.error('Error: Please provide a valid number as an argument');
  process.exit(1);
}

console.log(`Generating ${count} mock activities...`);

// Define constants
const categories = [
  // Sports & Physical Activities
  'Swimming', 'Fitness', 'Yoga', 'Pilates', 'Zumba',
  'Hockey', 'Basketball', 'Soccer', 'Tennis', 'Gymnastics',
  'Volleyball', 'Badminton', 'Martial Arts', 'Skating', 'Cycling',
  'Track & Field', 'Wrestling', 'Boxing', 'Archery', 'Fencing',
  'Table Tennis', 'Pickleball', 'Curling', 'Lacrosse', 'Rugby',
  
  // Aquatic Activities
  'Aquafit', 'Diving', 'Water Polo', 'Synchronized Swimming', 'Kayaking',
  'Canoeing', 'Paddle Boarding', 'Lifeguard Training', 'Swim Team',
  
  // Arts & Culture
  'Arts & Crafts', 'Painting', 'Drawing', 'Pottery', 'Sculpture',
  'Photography', 'Digital Art', 'Filmmaking', 'Animation', 'Theatre',
  'Drama', 'Dance', 'Ballet', 'Hip Hop', 'Contemporary Dance',
  'Music', 'Guitar Lessons', 'Piano Lessons', 'Choir', 'Band',
  'Creative Writing', 'Poetry', 'Book Club',
  
  // Educational & Life Skills
  'Cooking', 'Baking', 'Nutrition', 'Language Learning', 'Public Speaking',
  'Financial Literacy', 'Computer Skills', 'Coding', 'Robotics', 'Science Club',
  'Math Tutoring', 'Reading Club', 'Homework Help', 'First Aid & CPR',
  
  // Wellness & Mindfulness
  'Meditation', 'Stress Management', 'Tai Chi', 'Qigong', 'Mindfulness',
  'Senior Fitness', 'Parent & Tot', 'Family Fitness',
  
  // Outdoor & Seasonal Activities
  'Hiking', 'Nature Walks', 'Gardening', 'Bird Watching', 'Camping Skills',
  'Snowshoeing', 'Cross-Country Skiing', 'Tobogganing', 'Outdoor Survival',
  
  // Social & Community
  'Board Games', 'Chess Club', 'Youth Leadership', 'Volunteer Training',
  'Community Events', 'Seniors Social', 'Teen Night', 'Family Game Night'
];

const locations = [
  // Generic Community Centers
  'Central Community Center', 'Riverside Recreation Complex', 
  'Maple Leaf Recreation Center', 'Northern Lights Sports Complex',
  'Lakeview Community Center', 'Evergreen Recreation Facility',
  'Brookside Sports Center', 'Heritage Recreation Complex',
  'Parkview Community Center', 'Cedar Hills Recreation Center',
  'Pinecrest Community Hub', 'Mountainview Sports Complex',
  
  // Neighborhood-based Centers
  'Downtown Recreation Center', 'Westside Community Complex',
  'Eastview Sports Facility', 'Northgate Recreation Hub',
  'Southpoint Community Center', 'Hillcrest Recreation Center',
  'Valleyview Sports Complex', 'Meadowlands Community Center',
  
  // Nature-themed Centers
  'Forest Heights Recreation Center', 'Riverdale Community Complex',
  'Lakeside Sports Facility', 'Rocky Point Recreation Center',
  'Spruce Grove Community Hub', 'Aspen Woods Sports Center',
  'Willow Creek Recreation Complex', 'Birchwood Community Center',
  
  // Canadian-themed Centers
  'Maple Community Center', 'Beaver Creek Recreation Complex',
  'Moose Meadow Sports Center', 'Caribou Community Hub',
  'Glacier View Recreation Center', 'Aurora Sports Complex',
  'Taiga Community Center', 'Tundra Recreation Facility',
  
  // Seasonal-themed Centers
  'Four Seasons Recreation Center', 'Winter Haven Sports Complex',
  'Summer Heights Community Center', 'Spring Valley Recreation Hub',
  'Autumn Ridge Sports Facility', 'Snowfield Community Center'
];

const ageGroups = [
  'Preschool (0-5 yrs)', 'Children (6-12 yrs)', 'Youth (13-17 yrs)',
  'Adult (18-54 yrs)', 'Older Adult (55+ yrs)', 'All Ages'
];

const daysOfWeek = [
  'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'
];

const statuses = ['Open', 'Waitlist', 'Full'];
const languages = ['English', 'French'];

// Function to generate a realistic description using OpenAI
const generateDescription = async (activityName, category, ageGroup) => {
  try {
    const prompt = `Write a brief, concise description (30-50 words) for a ${ageGroup} activity called "${activityName}" in the category of ${category}. Keep it short but informative.`;
    
    const response = await openai.chat.completions.create({
      model: 'chatgpt-4o-latest',
      messages: [
        { role: 'system', content: 'You are a helpful assistant that writes concise activity descriptions.' },
        { role: 'user', content: prompt }
      ],
      max_tokens: 75,
      temperature: 0.7,
    });
    
    return response.choices[0].message.content.trim();
  } catch (error) {
    console.error('Error generating description:', error);
    return faker.lorem.paragraph(1); // Fallback to faker with just 1 paragraph if API call fails
  }
};

// Helper function to get a random element but track usage to ensure diversity
const getRandomElementWithDiversity = (array, usageMap) => {
  // If all elements have been used at least once, reset or use less strict criteria
  const unusedElements = array.filter(item => !usageMap[item] || usageMap[item] < 2);
  
  let selected;
  if (unusedElements.length > 0) {
    // Prioritize unused or less used elements
    selected = faker.helpers.arrayElement(unusedElements);
  } else {
    // If all have been used multiple times, pick randomly but favor less used ones
    const lessUsedElements = array.filter(item => usageMap[item] < Math.max(...Object.values(usageMap)));
    selected = faker.helpers.arrayElement(lessUsedElements.length > 0 ? lessUsedElements : array);
  }
  
  // Update usage count
  usageMap[selected] = (usageMap[selected] || 0) + 1;
  return selected;
};

// Helper function to generate a URL-friendly slug from activity name
const generateSlug = (text) => {
  return text
    .toLowerCase()
    .replace(/[^\w\s-]/g, '') // Remove special characters
    .replace(/\s+/g, '-') // Replace spaces with hyphens
    .replace(/-+/g, '-') // Replace multiple hyphens with single hyphen
    .trim(); // Trim leading/trailing spaces
};

// Modify the generateMockActivities function to use OpenAI for descriptions
const generateMockActivities = async (count) => {
  const activities = [];
  
  // Track usage to ensure diversity
  const categoryUsage = {};
  const locationUsage = {};
  const ageGroupUsage = {};
  const statusUsage = {};
  
  // More diverse activity name templates
  const activityNameTemplates = [
    // Basic templates
    `{category} for Beginners`,
    `Advanced {category}`,
    `{category} Workshop`,
    `{category} Class`,
    `{category} Program`,
    `{category} Fundamentals`,
    
    // More specific templates
    `Introduction to {category}`,
    `{category} for {ageGroup}`,
    `{category} Skills Development`,
    `{category} Intensive`,
    `{category} Drop-in`,
    `{category} Club`,
    `{category} Exploration`,
    `{category} Adventure`,
    `{category} Mastery`,
    `{category} Techniques`,
    `Competitive {category}`,
    `{category} Social`,
    `{category} Bootcamp`,
    `{category} Clinic`,
    `{category} Series`,
    `{category} Tournament`,
    `{category} League`,
  ];

  for (let i = 0; i < count; i++) {
    // Ensure diverse selection of categories, locations, and age groups
    const selectedCategory = getRandomElementWithDiversity(categories, categoryUsage);
    const selectedLocation = getRandomElementWithDiversity(locations, locationUsage);
    const selectedAgeGroup = getRandomElementWithDiversity(ageGroups, ageGroupUsage);
    const selectedStatus = getRandomElementWithDiversity(statuses, statusUsage);
    
    // Generate more diverse start dates (from 2 weeks to 6 months in the future)
    const startDate = new Date();
    startDate.setDate(startDate.getDate() + faker.number.int({ min: 14, max: 180 }));
    
    // Generate more realistic end dates based on activity type
    const endDate = new Date(startDate);
    // Different activities have different durations
    const durationMap = {
      'Workshop': { min: 1, max: 3 }, // 1-3 days for workshops
      'Class': { min: 28, max: 84 }, // 4-12 weeks for classes
      'Program': { min: 56, max: 112 }, // 8-16 weeks for programs
      'Camp': { min: 5, max: 14 }, // 1-2 weeks for camps
      'Retreat': { min: 2, max: 7 }, // 2-7 days for retreats
      'default': { min: 28, max: 84 } // default 4-12 weeks
    };
    
    // Determine activity type from name for duration calculation
    const activityType = Object.keys(durationMap).find(type => 
      activityNameTemplates.some(template => template.includes(type))
    ) || 'default';
    
    const duration = durationMap[activityType];
    endDate.setDate(endDate.getDate() + faker.number.int(duration));
    
    // Generate more realistic time slots
    const timeSlots = [
      '9:00 - 10:00', '10:00 - 11:00', '11:00 - 12:00', // Morning
      '13:00 - 14:00', '14:00 - 15:00', '15:00 - 16:00', // Afternoon
      '16:30 - 17:30', '17:30 - 18:30', '18:30 - 19:30', '19:30 - 20:30', // Evening
      '9:00 - 11:00', '13:00 - 15:00', '18:00 - 20:00', // 2-hour blocks
      '9:00 - 12:00', '13:00 - 16:00', // 3-hour blocks
    ];
    const time = faker.helpers.arrayElement(timeSlots);
    
    // Generate 1-3 random days of the week with more realistic patterns
    const activityDays = [];
    const dayPatterns = [
      ['Monday', 'Wednesday', 'Friday'], // MWF pattern
      ['Tuesday', 'Thursday'], // TTh pattern
      ['Saturday'], // Weekend only
      ['Sunday'], // Weekend only
      ['Saturday', 'Sunday'], // Weekend both days
      ['Monday'], ['Tuesday'], ['Wednesday'], ['Thursday'], ['Friday'] // Single weekday options
    ];
    
    // Either pick a pattern or generate random days
    if (faker.number.int({ min: 1, max: 10 }) <= 7) {
      // Use a common pattern 70% of the time
      const pattern = faker.helpers.arrayElement(dayPatterns);
      activityDays.push(...pattern);
    } else {
      // Random days 30% of the time
      const numDays = faker.number.int({ min: 1, max: 3 });
      const shuffledDays = [...daysOfWeek].sort(() => 0.5 - Math.random());
      for (let j = 0; j < numDays; j++) {
        activityDays.push(shuffledDays[j]);
      }
    }
    
    // Determine language with more realistic distribution for Canada
    const languageOptions = [];
    const languageChoice = faker.number.int({ min: 1, max: 100 });
    if (languageChoice <= 45) {
      languageOptions.push('English');
    } else if (languageChoice <= 70) {
      languageOptions.push('French');
    } else if (languageChoice <= 95) {
      // Increased probability of bilingual activities (25% chance)
      languageOptions.push('English', 'French');
    } else {
      // Small chance for other language combinations
      const otherOptions = [
        ['English', 'French'], 
        ['English', 'French'], // Duplicate to increase probability
        ['English', 'French', 'Spanish'],
        ['English', 'French', 'Mandarin'],
        ['English', 'French', 'Indigenous Languages']
      ];
      languageOptions.push(...faker.helpers.arrayElement(otherOptions));
    }
    
    // Generate more diverse activity names
    let template = faker.helpers.arrayElement(activityNameTemplates);
    let activityName = template
      .replace('{category}', selectedCategory)
      .replace('{ageGroup}', selectedAgeGroup.split(' ')[0]); // Just use the first word of age group
    
    // Add seasonal prefix occasionally
    const seasons = ['Winter', 'Spring', 'Summer', 'Fall'];
    if (faker.number.int({ min: 1, max: 10 }) <= 3) {
      const season = faker.helpers.arrayElement(seasons);
      activityName = `${season} ${activityName}`;
    }
    
    // Generate price based on activity type and duration
    let basePrice;
    if (activityName.includes('Workshop') || activityName.includes('Clinic')) {
      basePrice = faker.number.int({ min: 30, max: 150 });
    } else if (activityName.includes('Advanced') || activityName.includes('Intensive')) {
      basePrice = faker.number.int({ min: 100, max: 300 });
    } else if (activityName.includes('Certification') || activityName.includes('Training')) {
      basePrice = faker.number.int({ min: 150, max: 500 });
    } else {
      basePrice = faker.number.int({ min: 50, max: 200 });
    }
    
    // Adjust price based on duration
    const durationFactor = (endDate - startDate) / (1000 * 60 * 60 * 24 * 7); // in weeks
    const price = parseFloat((basePrice * (0.5 + durationFactor / 10)).toFixed(2));
    
    // Generate description using OpenAI with more context
    const description = await generateDescription(activityName, selectedCategory, selectedAgeGroup);
    
    // Generate registration URL using activity name and code
    const activityCode = faker.string.alphanumeric(6).toUpperCase();
    const activitySlug = generateSlug(activityName);
    const registrationUrl = `https://recreation.example.ca/register/${activitySlug}/${activityCode}`;
    
    // Generate waitlist URL for waitlisted activities
    const waitlistUrl = selectedStatus === 'Waitlist' 
      ? `${registrationUrl}/add-to-waitlist` 
      : null;
    
    activities.push({
      id: faker.string.uuid(),
      activityName,
      category: selectedCategory,
      location: selectedLocation,
      ageGroup: selectedAgeGroup,
      startDate,
      endDate,
      time,
      price,
      spotsAvailable: faker.number.int({ min: 0, max: 30 }),
      activityCode,
      description,
      language: languageOptions,
      status: selectedStatus,
      daysOfWeek: activityDays,
      registrationUrl,
      ...(selectedStatus === 'Waitlist' && { waitlistUrl: `${registrationUrl}/add-to-waitlist` })
    });
    
    // Log progress for long-running generations
    if (count > 20 && i % 10 === 0) {
      console.log(`Generated ${i + 1} of ${count} activities...`);
    }
  }

  return activities;
};

// Wrap the main execution in an async function to use await
(async () => {
  try {
    // Generate the mock activities
    const newActivities = await generateMockActivities(count);
    
    // Create the output directory if it doesn't exist
    const outputDir = path.resolve(process.cwd(), 'data');
    if (!fs.existsSync(outputDir)) {
      fs.mkdirSync(outputDir, { recursive: true });
    }
    
    // Define the output path
    const activitiesOutputPath = path.resolve(outputDir, 'activities.json');
    
    // Check if the file already exists
    let existingActivities = [];
    if (fs.existsSync(activitiesOutputPath)) {
      try {
        // Read existing activities
        const fileContent = fs.readFileSync(activitiesOutputPath, 'utf8');
        existingActivities = JSON.parse(fileContent);
        console.log(`Found ${existingActivities.length} existing activities.`);
      } catch (readError) {
        console.error('Error reading existing activities:', readError);
        console.log('Creating a new file instead.');
      }
    }
    
    // Create a set of existing activity identifiers to check for duplicates
    // We'll use a combination of name, location, and time as a unique identifier
    const existingActivityKeys = new Set();
    existingActivities.forEach(activity => {
      const key = `${activity.activityName}|${activity.location}|${activity.time}|${activity.daysOfWeek.join(',')}`;
      existingActivityKeys.add(key);
    });
    
    // Filter out any duplicates from the new activities
    const uniqueNewActivities = newActivities.filter(activity => {
      const key = `${activity.activityName}|${activity.location}|${activity.time}|${activity.daysOfWeek.join(',')}`;
      if (existingActivityKeys.has(key)) {
        return false; // Skip this activity as it's a duplicate
      }
      existingActivityKeys.add(key); // Add to set to prevent duplicates within new batch
      return true;
    });
    
    console.log(`Filtered out ${newActivities.length - uniqueNewActivities.length} duplicate activities.`);
    
    // Combine existing and unique new activities
    const allActivities = [...existingActivities, ...uniqueNewActivities];
    
    // Write the activities to a JSON file
    fs.writeFileSync(activitiesOutputPath, JSON.stringify(allActivities, null, 2));
    
    console.log(`Successfully added ${uniqueNewActivities.length} new activities to the file.`);
    console.log(`Total activities: ${allActivities.length}`);
    console.log(`Activities saved to: ${activitiesOutputPath}`);
  } catch (error) {
    console.error('Error generating mock data:', error);
  }
})();