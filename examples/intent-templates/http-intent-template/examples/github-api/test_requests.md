# GitHub API - Test Requests

Natural language examples for GitHub API integration.

## Repository Queries

### List User Repositories
Endpoint: /users/{username}/repos
Method: GET

1. "Show me repositories for octocat"
2. "Get all repos for user torvalds"
3. "List repositories owned by defunkt"
4. "Find projects by user mojombo"
5. "What repositories does pjhyett have?"

### Get Repository Details
Endpoint: /repos/{owner}/{repo}
Method: GET

1. "Show me details for octocat/Hello-World"
2. "Get info about torvalds/linux repository"
3. "Tell me about the facebook/react project"
4. "What is the microsoft/vscode repository?"
5. "Show repository information for google/guava"

### Search Repositories
Endpoint: /search/repositories
Method: GET

1. "Find repositories about machine learning"
2. "Search for React projects"
3. "Show me popular Python repositories"
4. "Find repositories with topic 'api'"
5. "Search for starred Rust projects"

## Issue Queries

### List Repository Issues
Endpoint: /repos/{owner}/{repo}/issues
Method: GET

1. "Show me open issues for facebook/react"
2. "List all bugs in microsoft/vscode"
3. "Get closed issues for nodejs/node"
4. "Find issues labeled 'good first issue' in rust-lang/rust"
5. "Show me recent issues in python/cpython"

### Get Issue Details
Endpoint: /repos/{owner}/{repo}/issues/{issue_number}
Method: GET

1. "Show me issue #123 in facebook/react"
2. "Get details for issue #456 in microsoft/vscode"
3. "Tell me about issue #789 in nodejs/node"
4. "What is issue #100 in rust-lang/rust about?"

## User Queries

### Get User Profile
Endpoint: /users/{username}
Method: GET

1. "Show me profile for user octocat"
2. "Get information about torvalds"
3. "Tell me about user defunkt"
4. "Who is user mojombo?"
5. "Show me details for github user pjhyett"

### List User Events
Endpoint: /users/{username}/events
Method: GET

1. "Show me recent activity for octocat"
2. "Get events for user torvalds"
3. "What has defunkt been working on?"
4. "Show me user activity for mojombo"
5. "What is pjhyett doing lately?"

## Organization Queries

### Get Organization
Endpoint: /orgs/{org}
Method: GET

1. "Show me details about github organization"
2. "Get information about google org"
3. "Tell me about the facebook organization"
4. "What is the microsoft organization?"

### List Organization Repositories
Endpoint: /orgs/{org}/repos
Method: GET

1. "Show me repositories for github organization"
2. "List all projects from google"
3. "Get repositories owned by facebook"
4. "What repositories does microsoft have?"
