# Contact - Enriched Test Queries

This document provides diverse, categorized test queries for the contact database schema.
Each section targets a specific template type to ensure diverse SQL template generation.

---

## Category 1: Basic List All Users (Simple)
<!-- Intent: list, Entity: users, Filter: none -->

Show me all users
List all users
Get all users
Display users
What users do we have?

---

## Category 2: Search by Name (Text Filter)
<!-- Intent: search, Entity: users, Filter: name (partial match) -->

Find users named John
Show me users with name like Smith
Get users whose name contains "Brown"
Search for users named Alice
Find all users with "Wilson" in their name
Show me users named "Johnson"
Get users with name matching "Prince"

---

## Category 3: Search by Exact Email (Exact Match)
<!-- Intent: find, Entity: users, Filter: email (exact) -->

Find user with email john@example.com
Show me the user with email jane@example.com
Get user by email alice@example.com
Who has email bob@example.com?
Find the user with email charlie@example.com

---

## Category 4: Filter by Single Age (Exact Match)
<!-- Intent: filter, Entity: users, Filter: age (equals) -->

Show me users who are 25 years old
Find users aged exactly 30
Get all 28 year old users
List users who are 35
Find users with age 32

---

## Category 5: Filter by Age Range (Comparison)
<!-- Intent: filter, Entity: users, Filter: age (range) -->

Show me users over 30
Find users under 25
Get users between 25 and 35
List users older than 40
Find users younger than 30
Show me users aged 20 to 50
Get users over 18 but under 65

---

## Category 6: Filter by City (Exact Match)
<!-- Intent: filter, Entity: users, Filter: city (exact) -->

Find users from New York
Show me users in Los Angeles
Get users living in Chicago
List users from Miami
Find all users in Boston
Show me users from Seattle

---

## Category 7: Count All Users (Aggregation - Total)
<!-- Intent: count, Entity: users, Aggregation: COUNT(*) -->

How many users do we have?
Count all users
What's the total number of users?
How many users are there?
Get the user count
Show me total users

---

## Category 8: Count by City (Aggregation - Group By)
<!-- Intent: count, Entity: users, Filter: city, Aggregation: COUNT, GroupBy: city -->

How many users are in New York?
Count users from Los Angeles
How many users per city?
Show me user count by city
Get user distribution by city
Count users in each city

---

## Category 9: Count by Age Range (Aggregation - Conditional)
<!-- Intent: count, Entity: users, Filter: age (range), Aggregation: COUNT -->

How many users are over 30?
Count users under 25
How many users between 25 and 35?
Count users older than 40
How many users under 30?
Get count of users aged 20-50

---

## Category 10: Recent Users by Date (Time-based Filter)
<!-- Intent: find, Entity: users, Filter: created_at (recent) -->

Show me recent users
Find users created today
Get users from this week
Show me users created in the last 7 days
Find users added this month
Get newest users
List users created in the last 30 days

---

## Category 11: Order by Name (Sorting)
<!-- Intent: list, Entity: users, Sort: name -->

Show me users ordered by name
List users alphabetically
Get users sorted by name ascending
Find users in alphabetical order
Display users by name A-Z

---

## Category 12: Order by Age (Sorting - Numeric)
<!-- Intent: list, Entity: users, Sort: age -->

Show me users sorted by age
List users from youngest to oldest
Get users ordered by age descending
Find users by age oldest first
Display users sorted by age

---

## Category 13: Order by Creation Date (Sorting - Temporal)
<!-- Intent: list, Entity: users, Sort: created_at -->

Show me users by creation date
List users by newest first
Get users ordered by when they were added
Find users by oldest first
Display users sorted by creation time

---

## Category 14: Average Age (Aggregation - AVG)
<!-- Intent: calculate, Entity: users, Field: age, Aggregation: AVG -->

What's the average age of users?
Get the mean age
Calculate average user age
Show me average age
What is the mean age of all users?

---

## Category 15: Min/Max Age (Aggregation - MIN/MAX)
<!-- Intent: calculate, Entity: users, Field: age, Aggregation: MIN/MAX -->

What's the oldest user age?
Find the youngest user age
Get maximum age
Show me minimum age
What's the age range?

---

## Category 16: Oldest/Youngest User (Top 1 with Sort)
<!-- Intent: find, Entity: users, Sort: age, Limit: 1 -->

Show me the oldest user
Find the youngest user
Who is the oldest person?
Get the youngest user
Display the oldest user record

---

## Category 17: Complex Multi-Filter (AND conditions)
<!-- Intent: filter, Entity: users, Filter: multiple (AND) -->

Find users from New York who are over 30
Show me users named John from Chicago
Get users aged 25-35 living in Boston
Find users in Miami who are under 40
List users from Seattle with age over 25

---

## Category 18: Name Partial Match with City (Multi-field)
<!-- Intent: search, Entity: users, Filter: name (partial) + city (exact) -->

Find users named Smith in New York
Show me Johns from Chicago
Get users with "Brown" in name from Boston
Search for Alice in Los Angeles
Find all Wilsons from Miami

---

## Category 19: Existence Check (Boolean Result)
<!-- Intent: exists, Entity: users, Filter: varies -->

Is there a user named John?
Does john@example.com exist?
Is there a user from New York?
Does a 25 year old user exist?
Are there any users from Chicago?

---

## Category 20: Top N Users (LIMIT with ORDER)
<!-- Intent: list, Entity: users, Sort: varies, Limit: N -->

Show me top 10 oldest users
Find 5 youngest users
Get 10 most recent users
List top 20 users by name
Show me first 5 users alphabetically

---

## Category 21: Email Domain Filter (Partial Match)
<!-- Intent: filter, Entity: users, Filter: email (contains) -->

Find users with gmail.com email
Show me users with example.com domain
Get users whose email ends with @company.com
List users with yahoo.com emails
Find all users with edu email addresses

---

## Category 22: Age Groups/Buckets (Range Categories)
<!-- Intent: filter, Entity: users, Filter: age (category) -->

Show me users in their 20s
Find users in their 30s
Get users aged 18-25
List teenage users
Find senior users over 65

---

## Category 23: City Starting With (Pattern Match)
<!-- Intent: filter, Entity: users, Filter: city (pattern) -->

Find users from cities starting with "New"
Show me users in cities beginning with "San"
Get users from cities starting with "Los"
List users in cities that start with "Chicago"

---

## Category 24: Users with Email (NULL check)
<!-- Intent: filter, Entity: users, Filter: email (not null) -->

Show me users who have an email
Find users with email addresses
Get users where email is not empty
List users with valid emails

---

## Category 25: Statistics Summary (Multiple Aggregations)
<!-- Intent: analyze, Entity: users, Aggregation: COUNT, AVG, MIN, MAX -->

Show me user statistics
Get user demographics summary
What are the user stats?
Analyze user data
Give me user overview

---
