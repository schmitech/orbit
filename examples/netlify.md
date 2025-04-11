# Netlify Deployment Guide

## Initial Setup

1. Install Netlify CLI globally:
```bash
npm install -g netlify-cli
```

2. Login to your Netlify account:
```bash
netlify login
```

## Configuration

Create a `netlify.toml` file in your project root with the following content:

```toml
[build]
  command = "npm run build"
  publish = "dist"
  functions = "netlify/functions"

[dev]
  command = "npm run dev"
  port = 3000
  publish = "dist"

[[redirects]]
  from = "/*"
  to = "/index.html"
  status = 200

[build.environment]
  NODE_VERSION = "18"
  VITE_API_ENDPOINT = "http://127.0.0.1:3000"  # Replace with your API endpoint
```

### Environment Variables

You can set environment variables in three ways:
1. Directly in `netlify.toml` (as shown above)
2. Through Netlify Dashboard: Site settings > Build & deploy > Environment variables
3. Using context-specific variables in `netlify.toml`:
```toml
[context.production.environment]
VITE_API_ENDPOINT = "production-url"

[context.deploy-preview.environment]
VITE_API_ENDPOINT = "preview-url"

[context.branch-deploy.environment]
VITE_API_ENDPOINT = "branch-url"
```

## Deployment

### Standard Deployment
1. Initialize your site:
```bash
netlify init
```
Choose either:
- Connect to existing site
- Create new site

2. Deploy to production:
```bash
netlify deploy --prod
```

### Deploying a Specific Folder

If you want to deploy a specific solution or folder from your project:

1. Navigate to the specific folder:
```bash
cd path/to/your/solution
npm run build
netlify deploy --prod --dir dist
```

2. Or deploy from any location by specifying the path:
```bash
netlify deploy --prod --dir path/to/your/solution
```

Note: Make sure your `netlify.toml` is in the solution directory or adjust the paths accordingly:
```toml
[build]
  base = "path/to/your/solution"    # Directory to change to before starting build
  command = "npm run build"
  publish = "dist"                  # Directory that contains the built site
```

## Managing Deployments

### List Sites
To view all your Netlify sites:
```bash
netlify sites:list
```

### Delete a Site
1. Find your site ID from the sites list
2. Delete the site:
```bash
netlify sites:delete YOUR_SITE_ID
```

### Unlink Local Project
To remove the connection between your local project and Netlify:
```bash
netlify unlink
```

## Best Practices

1. Always review environment variables before deploying
2. Use different environment variables for different deployment contexts
3. Don't commit sensitive information in `netlify.toml`
4. Consider using Netlify's Environment Variables UI for sensitive data
5. Keep your Netlify CLI updated
6. When deploying specific folders:
   - Ensure all dependencies are available in that folder
   - Verify build scripts are correctly configured for the subfolder
   - Test the build locally before deploying
