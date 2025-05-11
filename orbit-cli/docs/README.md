# API Key Manager

A utility for managing API keys and system prompts using a relational database with support for multiple database engines.

## Features

- Create, list, test, and deactivate API keys
- Create and manage system prompts (templates that guide LLM responses)
- Associate prompts with API keys
- Support for multiple database engines through a single configuration file
- Command-line interface for all operations

## Supported Database Engines

- SQLite (default, no additional installation required)
- PostgreSQL
- MySQL
- Oracle
- MS SQL Server

## Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/schmtech/orbit.git
   cd db-api-manager
   ```

2. Create a virtual environment and install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Copy the example configuration file:
   ```bash
   cp config.example.yaml config.yaml
   ```

4. Edit the configuration file to match your database preferences:
   ```yaml
   database:
     engine: "sqlite"  # or "postgres", "mysql", "oracle", "mssql"
     connection:
       sqlite:
         database: "data/api_keys.db"
       # Add details for other engines as needed
   ```

## Requirements

The following packages are required and will be installed from requirements.txt:

```
PyYAML>=6.0
SQLAlchemy>=2.0.0
```

Depending on your database engine, you'll also need the appropriate driver:
- SQLite: Built into Python, no additional packages needed
- PostgreSQL: `pip install psycopg2-binary`
- MySQL: `pip install pymysql`
- Oracle: `pip install cx_Oracle`
- MS SQL Server: `pip install pyodbc`

## Usage Examples

### API Key Management

#### Create a new API key with a system prompt
```bash
python orbit.py --config config.yaml create \
  --collection city \
  --name "City Assistant" \
  --prompt-file ../prompts/examples/city/city-assistant-normal-prompt.txt \
  --prompt-name "Municipal Assistant Prompt"
```

#### Create a basic API key
```bash
python orbit.py --config config.yaml create \
  --collection customer_data \
  --name "Customer Support" \
  --notes "For support portal"
```

#### List all API keys
```bash
python orbit.py --config config.yaml list
```

#### Test an API key
```bash
python orbit.py --config config.yaml test --key YOUR_API_KEY
```

#### Deactivate an API key
```bash
python orbit.py --config config.yaml deactivate --key YOUR_API_KEY
```

#### Delete an API key
```bash
python orbit.py --config config.yaml delete --key YOUR_API_KEY
```

#### Get API key status
```bash
python orbit.py --config config.yaml status --key YOUR_API_KEY
```

### System Prompt Management

#### Create a new system prompt
```bash
python orbit.py --config config.yaml prompt create \
  --name "Support Assistant" \
  --file prompts/support.txt \
  --version "1.0"
```

#### List all prompts
```bash
python orbit.py --config config.yaml prompt list
```

#### Get a specific prompt
```bash
python orbit.py --config config.yaml prompt get --id 1
```

#### Update a prompt
```bash
python orbit.py --config config.yaml prompt update \
  --id 1 \
  --file prompts/updated.txt \
  --version "1.1"
```

#### Delete a prompt
```bash
python orbit.py --config config.yaml prompt delete --id 1
```

### Associating Prompts with API Keys

#### Associate a prompt with an API key
```bash
python orbit.py --config config.yaml prompt associate \
  --key YOUR_API_KEY \
  --prompt-id 1
```

#### Create API key with a new prompt
```bash
python orbit.py --config config.yaml create \
  --collection support_docs \
  --name "Support Team" \
  --prompt-file prompts/support.txt \
  --prompt-name "Support Assistant"
```

#### Create API key with an existing prompt
```bash
python orbit.py --config config.yaml create \
  --collection legal_docs \
  --name "Legal Team" \
  --prompt-id 1
```

## Switching Database Engines

To switch from one database engine to another, simply update the `engine` field in your `config.yaml` file and ensure the connection parameters for the selected engine are correctly configured:

```yaml
database:
  engine: "postgres"  # Changed from "sqlite" to "postgres"
  connection:
    postgres:
      host: "localhost"
      port: 5432
      database: "api_keys"
      user: "postgres"
      password: "your_password"
```

No code changes are required to switch between supported database engines.

## Database Configuration

The configuration file supports detailed settings for each database engine:

### SQLite
```yaml
sqlite:
  database: "data/api_keys.db"
```

### PostgreSQL
```yaml
postgres:
  host: "localhost"
  port: 5432
  database: "api_keys"
  user: "postgres"
  password: "password"
  sslmode: "prefer"
```

### MySQL
```yaml
mysql:
  host: "localhost"
  port: 3306
  database: "api_keys"
  user: "root"
  password: "password"
  charset: "utf8mb4"
```

### Oracle
```yaml
oracle:
  host: "localhost"
  port: 1521
  service_name: "XEPDB1"  # or use SID: "XE"
  user: "system"
  password: "password"
```

### Microsoft SQL Server
```yaml
mssql:
  host: "localhost"
  port: 1433
  database: "api_keys"
  user: "sa"
  password: "password"
  driver: "ODBC Driver 17 for SQL Server"
```

## License

MIT