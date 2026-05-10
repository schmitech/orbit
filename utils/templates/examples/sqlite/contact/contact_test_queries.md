# Contact Database Test Queries

## Category 1: List All Users
<!-- Intent: find, Entity: users -->

1. "Show me all users"
2. "List all contacts"
3. "Get all users"

## Category 2: Search by Name
<!-- Intent: find, Entity: users, Filter: name (partial match) -->

1. "Find users named John"
2. "Search for contacts with Smith in their name"
3. "Show me users whose name contains Alice"

## Category 3: Find by Email
<!-- Intent: find, Entity: users, Filter: email (exact match) -->

1. "Find the user with email john@example.com"
2. "Look up contact by email address"
3. "Get user with email alice@gmail.com"

## Category 4: Filter by Age Range
<!-- Intent: filter, Entity: users, Filter: age (range) -->

1. "Show users between 25 and 35 years old"
2. "Find contacts aged 20 to 30"
3. "List users whose age is between 30 and 40"

## Category 5: Filter by City
<!-- Intent: filter, Entity: users, Filter: city -->

1. "Show users from New York"
2. "Find contacts in Chicago"
3. "List all users in Boston"

## Category 6: Count All Users
<!-- Intent: count, Entity: users -->

1. "How many users are there?"
2. "Count all contacts"
3. "What is the total number of users?"

## Category 7: Count by City
<!-- Intent: count, Entity: users, Group: city -->

1. "How many users are in each city?"
2. "Count contacts by city"
3. "Give me a breakdown of users per city"

## Category 8: Average Age
<!-- Intent: calculate, Entity: users, Aggregation: avg age -->

1. "What is the average age of users?"
2. "Calculate the mean age of all contacts"
3. "What's the average age?"

## Category 9: Sort by Name
<!-- Intent: sort, Entity: users, Order: name ASC -->

1. "List users alphabetically"
2. "Show contacts sorted by name"
3. "Get users ordered A to Z"

## Category 10: Top N Most Recent Users
<!-- Intent: find, Entity: users, Order: created_at DESC, Limit: N -->

1. "Show me the 10 most recently added users"
2. "Get the last 5 contacts added"
3. "Who are the newest users?"

## Category 11: Multi-field Filter (City + Age Range)
<!-- Intent: filter, Entity: users, Filter: city + age range -->

1. "Show users from New York aged 25 to 35"
2. "Find contacts in Chicago between 30 and 40 years old"
3. "List users in Boston aged 20-30"

## Category 12: Email Domain Search
<!-- Intent: find, Entity: users, Filter: email (domain) -->

1. "Find users with Gmail addresses"
2. "Show contacts with @company.com emails"
3. "List users from the example.com domain"
