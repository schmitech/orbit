# MongoDB Intent Template - Sample MFlix Database

This template provides intent-based querying for the MongoDB Atlas `sample_mflix` database, allowing natural language queries to be translated into MongoDB find operations. See schema defition here: https://www.mongodb.com/docs/atlas/sample-data/sample-mflix/

## Overview

The Sample MFlix database contains movie and user data with the following collections:

- **movies**: Movie information including title, plot, genres, directors, cast, ratings, and metadata
- **users**: User accounts with names, emails, and preferences
- **comments**: User comments and reviews for movies
- **theaters**: Theater location data
- **sessions**: User session information

## Database Schema

### Movies Collection
- `_id`: ObjectId (primary key)
- `title`: String - Movie title
- `plot`: String - Movie plot summary
- `genres`: Array - List of genres
- `directors`: Array - List of directors
- `cast`: Array - List of cast members
- `year`: Integer - Release year
- `rated`: String - MPAA rating
- `runtime`: Integer - Runtime in minutes
- `imdb.rating`: Number - IMDB rating (0-10)
- `imdb.votes`: Integer - Number of IMDB votes
- `awards.wins`: Integer - Number of award wins
- `awards.nominations`: Integer - Number of award nominations
- `countries`: Array - List of countries
- `languages`: Array - List of languages

### Users Collection
- `_id`: ObjectId (primary key)
- `name`: String - User's full name
- `email`: String - User's email address
- `password`: String - Hashed password
- `preferences`: Object - User preferences

### Comments Collection
- `_id`: ObjectId (primary key)
- `name`: String - Commenter's name
- `email`: String - Commenter's email
- `movie_id`: ObjectId - Reference to movie
- `text`: String - Comment text
- `date`: Date - Comment date

## Setup Instructions

### 1. MongoDB Atlas Connection

1. Create a MongoDB Atlas account at [mongodb.com](https://www.mongodb.com)
2. Create a new cluster or use an existing one
3. Load the sample data:
   - In Atlas, go to your cluster
   - Click "..." → "Load Sample Dataset"
   - Wait for the sample data to load (includes sample_mflix database)

### 2. Get Connection String

1. In Atlas, click "Connect" on your cluster
2. Choose "Connect your application"
3. Copy the connection string
4. Replace `<password>` with your database user password

### 3. Environment Variables

Set the following environment variables:

```bash
export DATASOURCE_MONGODB_URI="mongodb+srv://username:password@cluster.mongodb.net/sample_mflix?retryWrites=true&w=majority"
export DATASOURCE_MONGODB_DATABASE="sample_mflix"
export DATASOURCE_MONGODB_HOST="cluster.mongodb.net"
export DATASOURCE_MONGODB_USERNAME="your_username"
export DATASOURCE_MONGODB_PASSWORD="your_password"
```

### 4. Configure ORBIT

Update your `config/datasources.yaml`:

```yaml
datasources:
  mongodb:
    enabled: true
    connection_string: ${MONGODB_URI}
    database: ${MONGODB_DATABASE}
    timeout: 30
    tls: true
```

## Template Structure

### Domain Configuration (`mflix_domain.yaml`)
- Collection schemas and field definitions
- Vocabulary for natural language understanding
- Query patterns and defaults
- Response processing configuration

### Query Templates

#### Basic Templates (`mflix_templates.yaml`)
6 basic MongoDB find query templates:
  1. **search_movies_by_title**: Search movies by title with optional filters
  2. **search_movies_by_genre_year**: Find movies by genre and year range
  3. **search_users_by_name_email**: Search users by name or email
  4. **get_recent_comments**: Get recent comments with optional filters
  5. **get_movies_by_rating_threshold**: Find movies above rating threshold
  6. **search_movies_multi_filter**: Advanced search with multiple filters

#### Advanced Templates (`mflix_advanced_templates.yaml`)
9 advanced aggregation pipeline templates with multi-collection joins and BI analytics:

**Multi-Collection Queries (using $lookup):**
  1. **most_commented_movies_with_ratings**: Movies with most comments + ratings
  2. **user_engagement_analysis**: Users with most comments and activity metrics
  3. **movies_with_comment_samples**: Movies with recent comment samples

**BI Analytics Queries:**
  4. **genre_performance_analysis**: Genre analytics with ratings, counts, engagement
  5. **director_success_analysis**: Director performance with success scores
  6. **temporal_genre_trends**: Genre trends over decades
  7. **award_winning_movies_analysis**: Award-winning movies with engagement metrics
  8. **underrated_gems_analysis**: High-quality movies with low comment counts
  9. **cast_collaboration_network**: Actor collaboration patterns

## Example Queries

### Basic Queries
- "Find movies with 'batman' in the title"
- "Show me action movies from 2010 to 2020"
- "Get movies with rating above 8"
- "Find users named 'john'"
- "Show me recent comments"
- "Find drama movies from the 90s with high ratings"

### Advanced Multi-Collection Queries
- "Show me the most commented movies with high ratings"
- "Who are the most active users?"
- "Find movies with their recent comments"
- "What are people saying about highly rated movies?"

### BI Analytics Queries
- "Analyze movie genres by performance"
- "Which genres have the highest ratings?"
- "Who are the most successful directors?"
- "Show me genre trends over time"
- "Find underrated movies"
- "Show me award-winning movies with engagement metrics"

## Query Features

### Supported MongoDB Operations

#### Basic Operations
- **Find queries** with filter conditions
- **Count queries** for document counting
- **Text search** using regex (case-insensitive)
- **Range queries** for numeric fields
- **Array matching** for genres, countries, languages
- **Projection** to select specific fields
- **Sorting** by multiple fields
- **Pagination** with limit and skip

#### Advanced Aggregation Operations
- **$lookup** - Join collections (similar to SQL JOIN)
- **$group** - Group documents and compute aggregations
- **$unwind** - Deconstruct arrays
- **$match** - Filter documents in pipeline
- **$project** - Reshape documents
- **$addFields** - Add computed fields
- **$sort** - Sort pipeline results
- **$limit** - Limit pipeline results
- **$slice** - Array slicing

### Query Operators
- `$eq`, `$ne` - Equality/inequality
- `$gt`, `$gte`, `$lt`, `$lte` - Comparison
- `$in`, `$nin` - Array membership
- `$regex` - Text pattern matching
- `$and`, `$or` - Logical operators
- `$sum`, `$avg`, `$max`, `$min` - Aggregation operators
- `$size` - Array size
- `$divide`, `$multiply` - Math operators

## Configuration Files

- `mflix_domain.yaml` - Domain schema and vocabulary (all 5 collections: movies, users, comments, theaters, sessions)
- `mflix_templates.yaml` - Basic query templates (6 find queries)
- `mflix_advanced_templates.yaml` - Advanced templates (9 aggregation pipelines with multi-collection joins)
- `config/datasources.yaml` - MongoDB connection settings
- `config/adapters.yaml` - Adapter configuration

## Troubleshooting

### Common Issues

1. **Connection Failed**
   - Verify MongoDB Atlas cluster is running
   - Check connection string and credentials
   - Ensure IP whitelist includes your IP

2. **Template Not Found**
   - Verify template files are in correct location
   - Check adapter configuration paths
   - Ensure templates are loaded into vector store

3. **Query Errors**
   - Check MongoDB query syntax in templates
   - Verify collection names and field names
   - Test queries directly in MongoDB Compass

### Debug Mode

Enable verbose logging in adapter config:

```yaml
config:
  adapter_config:
    verbose: true
    confidence_threshold: 0.5
```

## Advanced Features

### Multi-Collection Joins
The advanced templates demonstrate how to combine multiple collections using MongoDB's `$lookup` aggregation stage, similar to SQL JOINs:
- Movies ← Comments (one-to-many relationship)
- Comments → Users (many-to-one relationship)
- Movies with comment counts and samples

### Business Intelligence Queries
The templates include sophisticated BI queries that provide insights:
- **Engagement Analysis**: Comment counts, user activity, popularity metrics
- **Performance Metrics**: Success scores combining ratings, votes, and awards
- **Trend Analysis**: Temporal trends over decades
- **Quality Discovery**: Finding underrated gems with high quality but low engagement
- **Network Analysis**: Actor collaboration patterns

### Computed Fields and Scoring
Templates use MongoDB's aggregation framework to compute derived metrics:
- Engagement scores (combining ratings and comments)
- Success scores (combining multiple quality signals)
- Underrated scores (quality vs. engagement ratio)
- Days active, average comments per movie, etc.

## Next Steps

- ✅ Multi-collection aggregation pipeline templates
- ✅ All 5 collections configured (movies, users, comments, theaters, sessions)
- ✅ Business intelligence analytics templates
- Add text search with MongoDB Atlas Search indexes
- Add geospatial queries for theater locations
- Add user session analysis templates
