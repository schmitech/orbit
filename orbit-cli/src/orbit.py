#!/usr/bin/env python3
"""
ORBIT Manager Utility
=========================================

A command-line utility for managing ORBIT admin tasks.
Supports multiple database engines through a YAML configuration file.

Features:
- Create, list, test, and deactivate API keys
- Create and manage system prompts (templates that guide LLM responses)
- Associate prompts with API keys

Supported Database Engines:
- SQLite (default)
- PostgreSQL
- MySQL
- Oracle
- Microsoft SQL Server

Requirements:
- PyYAML: For parsing the configuration file
- SQLAlchemy: For database engine abstraction
- Database-specific drivers based on your configuration

Configuration:
  Uses a YAML configuration file (default: config.yaml) for database connection details
  and other settings.

Examples:
  # Create a new API key
  python db_api_manager.py --config config.yaml create --collection customer_data --name "Customer Support" --notes "For support portal"

  # List all API keys
  python db_api_manager.py --config config.yaml list

  # Check status of an API key
  python db_api_manager.py --config config.yaml status --key api_abcd1234

  # Change database engine in config.yaml and run the same commands without code changes
"""

import argparse
import json
import os
import sys
import secrets
import string
import logging
import datetime
from datetime import UTC
from typing import Dict, Any, List, Optional, Tuple, Union
from pathlib import Path

import yaml
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from sqlalchemy.sql import text, func
from sqlalchemy.pool import QueuePool
from sqlalchemy.exc import SQLAlchemyError

# Default configuration path
DEFAULT_CONFIG_PATH = Path('config.yaml')

# Create default config if it doesn't exist
if not DEFAULT_CONFIG_PATH.exists():
    default_config = {
        'database': {
            'engine': 'sqlite',
            'connection': {
                'sqlite': {
                    'database': 'api_keys.db'
                }
            }
        },
        'application': {
            'log_level': 'INFO',
            'log_file': 'orbit.log'
        },
        'api_keys': {
            'prefix': 'api_',
            'length': 16,
            'characters': string.ascii_letters + string.digits
        },
        'prompts': {
            'default_version': '1.0'
        }
    }
    
    DEFAULT_CONFIG_PATH.parent.mkdir(exist_ok=True)
    with open(DEFAULT_CONFIG_PATH, 'w') as f:
        yaml.dump(default_config, f, default_flow_style=False)
    
    print(f"Created default configuration at {DEFAULT_CONFIG_PATH}")

# Set up logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Create SQLAlchemy base class
Base = declarative_base()

# Define SQLAlchemy models
class ApiKey(Base):
    __tablename__ = 'api_keys'
    
    id = Column(Integer, primary_key=True)
    api_key = Column(String(50), unique=True, nullable=False)
    collection_name = Column(String(100), nullable=False)
    client_name = Column(String(100), nullable=False)
    notes = Column(Text)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(UTC), nullable=False)
    last_used_at = Column(DateTime)
    
    # Relationship to prompt through association table
    prompt = relationship("ApiKeyPrompt", back_populates="api_key", uselist=False, cascade="all, delete-orphan")
    
    def to_dict(self):
        result = {
            "id": self.id,
            "api_key": self.api_key,
            "collection_name": self.collection_name,
            "client_name": self.client_name,
            "notes": self.notes,
            "active": self.active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None
        }
        
        # Add prompt information if available
        if self.prompt and self.prompt.system_prompt:
            result["prompt_id"] = self.prompt.system_prompt.id
            result["prompt_name"] = self.prompt.system_prompt.name
            
        return result

class SystemPrompt(Base):
    __tablename__ = 'system_prompts'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    prompt_text = Column(Text, nullable=False)
    version = Column(String(20), default='1.0', nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(UTC), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.datetime.now(UTC), onupdate=lambda: datetime.datetime.now(UTC), nullable=False)
    
    # Relationship to api keys through association table
    api_keys = relationship("ApiKeyPrompt", back_populates="system_prompt", cascade="all, delete-orphan")
    
    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "prompt_text": self.prompt_text,
            "version": self.version,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }

class ApiKeyPrompt(Base):
    __tablename__ = 'api_key_prompts'
    
    api_key_id = Column(Integer, ForeignKey('api_keys.id', ondelete='CASCADE'), primary_key=True)
    prompt_id = Column(Integer, ForeignKey('system_prompts.id', ondelete='CASCADE'), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(UTC), nullable=False)
    
    # Relationships
    api_key = relationship(
        "ApiKey",
        back_populates="prompt",
    )
    system_prompt = relationship(
        "SystemPrompt",
        back_populates="api_keys",
    )


class DbApiKeyManager:
    """Database-agnostic utility class for managing API keys and system prompts"""
    
    _engines = {}  # Class variable to store database engines
    
    def __init__(self, config_file: str = 'config.yaml'):
        """
        Initialize the API Key Manager with configuration from a YAML file
        
        Args:
            config_file: Path to the YAML configuration file
        """
        self.config = self._load_config(config_file)
        self.engine = self._create_engine()
        self.Session = sessionmaker(bind=self.engine)
        
        # Create tables if they don't exist
        self._initialize_database()
        
        # Configure logging
        self._configure_logging()
    
    @classmethod
    def cleanup_engines(cls):
        """
        Clean up all database engines
        """
        for engine in cls._engines.values():
            try:
                engine.dispose()
            except Exception as e:
                logger.error(f"Error disposing engine: {e}")
        cls._engines.clear()
    
    def __del__(self):
        """
        Clean up resources when the object is garbage collected
        """
        try:
            # Dispose engine to close any open connections
            if hasattr(self, 'engine') and self.engine:
                self.engine.dispose()
        except Exception as e:
            # Can't use logger here as it might already be gone
            print(f"Error during cleanup: {str(e)}", file=sys.stderr)
    
    def _load_config(self, config_file: str) -> Dict[str, Any]:
        """
        Load configuration from a YAML file
        
        Args:
            config_file: Path to the YAML configuration file
            
        Returns:
            Dictionary containing the configuration
        """
        try:
            with open(config_file, 'r') as file:
                config = yaml.safe_load(file)
            return config
        except Exception as e:
            raise RuntimeError(f"Error loading configuration from {config_file}: {str(e)}") from e
    
    def _configure_logging(self):
        """Configure logging based on the configuration"""
        if 'application' in self.config and 'log_level' in self.config['application']:
            log_level_str = self.config['application']['log_level'].upper()
            log_level = getattr(logging, log_level_str, logging.INFO)
            logger.setLevel(log_level)
            
            if 'log_file' in self.config['application']:
                log_file = self.config['application']['log_file']
                # Create log directory if it doesn't exist
                log_dir = os.path.dirname(log_file)
                if log_dir and not os.path.exists(log_dir):
                    os.makedirs(log_dir)
                
                file_handler = logging.FileHandler(log_file)
                file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
                logger.addHandler(file_handler)
    
    def _create_engine(self):
        """
        Create a SQLAlchemy engine based on the configuration
        
        Returns:
            SQLAlchemy engine
        """
        db_config = self.config.get('database', {})
        engine_type = db_config.get('engine', 'sqlite')
        
        # Get connection parameters for the selected engine
        conn_params = db_config.get('connection', {}).get(engine_type, {})
        
        # Build connection URL based on engine type
        if engine_type == 'sqlite':
            db_path = conn_params.get('database', 'api_keys.db')
            # Create directory if it doesn't exist
            db_dir = os.path.dirname(db_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir)
            url = f"sqlite:///{db_path}"
        
        elif engine_type == 'postgres':
            host = conn_params.get('host', 'localhost')
            port = conn_params.get('port', 5432)
            database = conn_params.get('database', 'api_keys')
            user = conn_params.get('user', 'postgres')
            password = conn_params.get('password', '')
            sslmode = conn_params.get('sslmode', 'prefer')
            url = f"postgresql://{user}:{password}@{host}:{port}/{database}?sslmode={sslmode}"
        
        elif engine_type == 'mysql':
            host = conn_params.get('host', 'localhost')
            port = conn_params.get('port', 3306)
            database = conn_params.get('database', 'api_keys')
            user = conn_params.get('user', 'root')
            password = conn_params.get('password', '')
            charset = conn_params.get('charset', 'utf8mb4')
            url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset={charset}"
        
        elif engine_type == 'oracle':
            host = conn_params.get('host', 'localhost')
            port = conn_params.get('port', 1521)
            user = conn_params.get('user', 'system')
            password = conn_params.get('password', '')
            
            # Oracle can use either service_name or SID
            if 'service_name' in conn_params:
                service_name = conn_params['service_name']
                url = f"oracle+cx_oracle://{user}:{password}@{host}:{port}/?service_name={service_name}"
            else:
                sid = conn_params.get('sid', 'XE')
                url = f"oracle+cx_oracle://{user}:{password}@{host}:{port}/{sid}"
        
        elif engine_type == 'mssql':
            host = conn_params.get('host', 'localhost')
            port = conn_params.get('port', 1433)
            database = conn_params.get('database', 'api_keys')
            user = conn_params.get('user', 'sa')
            password = conn_params.get('password', '')
            driver = conn_params.get('driver', 'ODBC Driver 17 for SQL Server')
            url = f"mssql+pyodbc://{user}:{password}@{host}:{port}/{database}?driver={driver}"
        
        else:
            raise ValueError(f"Unsupported database engine: {engine_type}")
        
        # Create engine with pool settings if configured
        pool_config = db_config.get('pool', {})
        pool_size = pool_config.get('max_size', 5)
        pool_timeout = pool_config.get('timeout', 30)
        
        engine = create_engine(url, pool_size=pool_size, pool_timeout=pool_timeout)
        # Add to class list for cleanup
        DbApiKeyManager._engines[url] = engine
        return engine
    
    def _initialize_database(self):
        """Create database tables if they don't exist"""
        Base.metadata.create_all(self.engine)
        logger.info("Database initialized successfully")
    
    def _generate_api_key(self) -> str:
        """
        Generate a random API key based on configuration
        
        Returns:
            A random API key string
        """
        api_key_config = self.config.get('api_keys', {})
        prefix = api_key_config.get('prefix', 'api_')
        length = api_key_config.get('length', 16)
        characters = api_key_config.get('characters', string.ascii_letters + string.digits)
        
        # Generate a random string of characters
        random_part = ''.join(secrets.choice(characters) for _ in range(length))
        return f"{prefix}{random_part}"
    
    def create_api_key(
        self, 
        collection_name: str, 
        client_name: str, 
        notes: Optional[str] = None,
        prompt_id: Optional[int] = None,
        prompt_name: Optional[str] = None,
        prompt_file: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new API key for a client, optionally with an associated system prompt
        
        Args:
            collection_name: The name of the collection to associate with this key
            client_name: The name of the client
            notes: Optional notes about this API key
            prompt_id: Optional existing system prompt ID to associate
            prompt_name: Optional name for a new system prompt
            prompt_file: Optional path to a file containing a system prompt
            
        Returns:
            Dictionary containing the created API key details
        """
        session = self.Session()
        
        try:
            # First handle prompt if needed
            if prompt_file and (prompt_name or prompt_id):
                # If we have a prompt file, we need to either create a new prompt or update an existing one
                prompt_text = self._read_file_content(prompt_file)
                
                if prompt_id:
                    # Update an existing prompt
                    prompt_result = self.update_prompt(prompt_id, prompt_text)
                    prompt_id = prompt_result.get("id") or prompt_id
                elif prompt_name:
                    # Create a new prompt
                    prompt_result = self.create_prompt(prompt_name, prompt_text)
                    prompt_id = prompt_result.get("id")
                    if not prompt_id:
                        raise RuntimeError("Failed to get prompt ID from created prompt")
            
            # Generate a unique API key
            api_key_value = self._generate_api_key()
            
            # Create a new API key
            api_key = ApiKey(
                api_key=api_key_value,
                collection_name=collection_name,
                client_name=client_name,
                notes=notes
            )
            
            session.add(api_key)
            session.flush()  # Flush to get the ID
            
            # If we have a prompt ID, associate it with the API key
            if prompt_id:
                # First check if the prompt exists
                prompt = session.query(SystemPrompt).filter(SystemPrompt.id == prompt_id).first()
                if not prompt:
                    raise RuntimeError(f"Prompt with ID {prompt_id} not found")
                
                # Create the association
                api_key_prompt = ApiKeyPrompt(
                    api_key_id=api_key.id,
                    prompt_id=prompt_id
                )
                
                session.add(api_key_prompt)
            
            session.commit()
            
            # Refresh to ensure relationships are loaded
            session.refresh(api_key)
            
            # Convert to dictionary
            result = api_key.to_dict()
            
            return result
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error creating API key: {str(e)}")
            raise RuntimeError(f"Error creating API key: {str(e)}") from e
        finally:
            session.close()
    
    def _read_file_content(self, file_path: str) -> str:
        """
        Read content from a file
        
        Args:
            file_path: Path to the file
            
        Returns:
            Content of the file as a string
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                return file.read()
        except Exception as e:
            raise RuntimeError(f"Error reading file {file_path}: {str(e)}") from e
    
    def list_api_keys(self) -> List[Dict[str, Any]]:
        """
        List all API keys
        
        Returns:
            List of dictionaries containing API key details
        """
        session = self.Session()
        
        try:
            api_keys = session.query(ApiKey).all()
            return [api_key.to_dict() for api_key in api_keys]
        except Exception as e:
            logger.error(f"Error listing API keys: {str(e)}")
            raise RuntimeError(f"Error listing API keys: {str(e)}") from e
        finally:
            session.close()
    
    def deactivate_api_key(self, api_key: str) -> Dict[str, Any]:
        """
        Deactivate an API key
        
        Args:
            api_key: The API key to deactivate
            
        Returns:
            Dictionary containing the result of the operation
        """
        session = self.Session()
        
        try:
            # Find the API key
            api_key_obj = session.query(ApiKey).filter(ApiKey.api_key == api_key).first()
            
            if not api_key_obj:
                raise RuntimeError(f"API key {api_key} not found")
            
            # Deactivate the API key
            api_key_obj.active = False
            
            session.commit()
            
            return {"status": "success", "message": f"API key {api_key} deactivated successfully"}
        except Exception as e:
            session.rollback()
            logger.error(f"Error deactivating API key: {str(e)}")
            raise RuntimeError(f"Error deactivating API key: {str(e)}") from e
        finally:
            session.close()
    
    def delete_api_key(self, api_key: str) -> Dict[str, Any]:
        """
        Delete an API key
        
        Args:
            api_key: The API key to delete
            
        Returns:
            Dictionary containing the result of the operation
        """
        session = self.Session()
        
        try:
            # Find the API key
            api_key_obj = session.query(ApiKey).filter(ApiKey.api_key == api_key).first()
            
            if not api_key_obj:
                raise RuntimeError(f"API key {api_key} not found")
            
            # Delete the API key (cascade will handle associations)
            session.delete(api_key_obj)
            
            session.commit()
            
            return {"status": "success", "message": f"API key {api_key} deleted successfully"}
        except Exception as e:
            session.rollback()
            logger.error(f"Error deleting API key: {str(e)}")
            raise RuntimeError(f"Error deleting API key: {str(e)}") from e
        finally:
            session.close()
    
    def get_api_key_status(self, api_key: str) -> Dict[str, Any]:
        """
        Get the status of an API key
        
        Args:
            api_key: The API key to check
            
        Returns:
            Dictionary containing the API key status
        """
        session = self.Session()
        
        try:
            # Find the API key
            api_key_obj = session.query(ApiKey).filter(ApiKey.api_key == api_key).first()
            
            if not api_key_obj:
                raise RuntimeError(f"API key {api_key} not found")
            
            return api_key_obj.to_dict()
        except Exception as e:
            logger.error(f"Error checking API key status: {str(e)}")
            raise RuntimeError(f"Error checking API key status: {str(e)}") from e
        finally:
            session.close()
    
    def test_api_key(self, api_key: str) -> Dict[str, Any]:
        """
        Test an API key by checking if it exists and is active
        
        Args:
            api_key: The API key to test
            
        Returns:
            Dictionary containing the test result
        """
        session = self.Session()
        
        try:
            # Find the API key
            api_key_obj = session.query(ApiKey).filter(ApiKey.api_key == api_key).first()
            
            if not api_key_obj:
                return {
                    "status": "error",
                    "error": "API key not found"
                }
            
            if not api_key_obj.active:
                return {
                    "status": "error",
                    "error": "API key is deactivated"
                }
            
            # Update the last_used_at timestamp
            api_key_obj.last_used_at = datetime.datetime.now(UTC)
            
            session.commit()
            
            return {
                "status": "success",
                "message": "API key is valid and active"
            }
        except Exception as e:
            session.rollback()
            logger.error(f"Error testing API key: {str(e)}")
            raise RuntimeError(f"Error testing API key: {str(e)}") from e
        finally:
            session.close()
    
    # System Prompt Management
    
    def create_prompt(self, name: str, prompt_text: str, version: str = None) -> Dict[str, Any]:
        """
        Create a new system prompt
        
        Args:
            name: A unique name for the prompt
            prompt_text: The prompt text
            version: Version string for the prompt (default from config)
            
        Returns:
            Dictionary containing the created prompt details
        """
        session = self.Session()
        
        try:
            # Use default version from config if not provided
            if version is None:
                version = self.config.get('prompts', {}).get('default_version', '1.0')
            
            # Create a new prompt
            prompt = SystemPrompt(
                name=name,
                prompt_text=prompt_text,
                version=version
            )
            
            session.add(prompt)
            session.commit()
            
            # Refresh to ensure all fields are loaded
            session.refresh(prompt)
            
            # Convert to dictionary
            result = prompt.to_dict()
            
            return result
        except Exception as e:
            session.rollback()
            logger.error(f"Error creating prompt: {str(e)}")
            raise RuntimeError(f"Error creating prompt: {str(e)}") from e
        finally:
            session.close()
    
    def list_prompts(self) -> List[Dict[str, Any]]:
        """
        List all system prompts
        
        Returns:
            List of dictionaries containing prompt details
        """
        session = self.Session()
        
        try:
            prompts = session.query(SystemPrompt).all()
            return [prompt.to_dict() for prompt in prompts]
        except Exception as e:
            logger.error(f"Error listing prompts: {str(e)}")
            raise RuntimeError(f"Error listing prompts: {str(e)}") from e
        finally:
            session.close()
    
    def get_prompt(self, prompt_id: int) -> Dict[str, Any]:
        """
        Get a system prompt by its ID
        
        Args:
            prompt_id: The ID of the prompt
            
        Returns:
            Dictionary containing the prompt details
        """
        session = self.Session()
        
        try:
            # Find the prompt
            prompt = session.query(SystemPrompt).filter(SystemPrompt.id == prompt_id).first()
            
            if not prompt:
                raise RuntimeError(f"Prompt with ID {prompt_id} not found")
            
            return prompt.to_dict()
        except Exception as e:
            logger.error(f"Error getting prompt: {str(e)}")
            raise RuntimeError(f"Error getting prompt: {str(e)}") from e
        finally:
            session.close()
    
    def update_prompt(self, prompt_id: int, prompt_text: str, version: Optional[str] = None) -> Dict[str, Any]:
        """
        Update an existing system prompt
        
        Args:
            prompt_id: The ID of the prompt to update
            prompt_text: The new prompt text
            version: Optional new version string
            
        Returns:
            Dictionary containing the updated prompt details
        """
        session = self.Session()
        
        try:
            # Find the prompt
            prompt = session.query(SystemPrompt).filter(SystemPrompt.id == prompt_id).first()
            
            if not prompt:
                raise RuntimeError(f"Prompt with ID {prompt_id} not found")
            
            # Update the prompt
            prompt.prompt_text = prompt_text
            
            if version:
                prompt.version = version
            
            # update_at will be updated automatically via the onupdate trigger
            
            session.commit()
            
            # Refresh to ensure all fields are updated
            session.refresh(prompt)
            
            return prompt.to_dict()
        except Exception as e:
            session.rollback()
            logger.error(f"Error updating prompt: {str(e)}")
            raise RuntimeError(f"Error updating prompt: {str(e)}") from e
        finally:
            session.close()
    
    def delete_prompt(self, prompt_id: int) -> Dict[str, Any]:
        """
        Delete a system prompt
        
        Args:
            prompt_id: The ID of the prompt to delete
            
        Returns:
            Dictionary containing the result of the operation
        """
        session = self.Session()
        
        try:
            # Find the prompt
            prompt = session.query(SystemPrompt).filter(SystemPrompt.id == prompt_id).first()
            
            if not prompt:
                raise RuntimeError(f"Prompt with ID {prompt_id} not found")
            
            # Delete the prompt (cascade will handle associations)
            session.delete(prompt)
            
            session.commit()
            
            return {"status": "success", "message": f"Prompt with ID {prompt_id} deleted successfully"}
        except Exception as e:
            session.rollback()
            logger.error(f"Error deleting prompt: {str(e)}")
            raise RuntimeError(f"Error deleting prompt: {str(e)}") from e
        finally:
            session.close()
    
    def associate_prompt_with_api_key(self, api_key: str, prompt_id: int) -> Dict[str, Any]:
        """
        Associate a system prompt with an API key
        
        Args:
            api_key: The API key
            prompt_id: The ID of the prompt to associate
            
        Returns:
            Dictionary containing the result of the operation
        """
        session = self.Session()
        
        try:
            # Find the API key
            api_key_obj = session.query(ApiKey).filter(ApiKey.api_key == api_key).first()
            
            if not api_key_obj:
                raise RuntimeError(f"API key {api_key} not found")
            
            # Find the prompt
            prompt = session.query(SystemPrompt).filter(SystemPrompt.id == prompt_id).first()
            
            if not prompt:
                raise RuntimeError(f"Prompt with ID {prompt_id} not found")
            
            # Check if there's an existing association
            existing = session.query(ApiKeyPrompt).filter(ApiKeyPrompt.api_key_id == api_key_obj.id).first()
            
            if existing:
                # Update the existing association
                existing.prompt_id = prompt_id
            else:
                # Create a new association
                api_key_prompt = ApiKeyPrompt(
                    api_key_id=api_key_obj.id,
                    prompt_id=prompt_id
                )
                session.add(api_key_prompt)
            
            session.commit()
            
            return {
                "status": "success",
                "message": f"Prompt with ID {prompt_id} associated with API key {api_key} successfully"
            }
        except Exception as e:
            session.rollback()
            logger.error(f"Error associating prompt with API key: {str(e)}")
            raise RuntimeError(f"Error associating prompt with API key: {str(e)}") from e
        finally:
            session.close()
    
    def get_prompt_for_api_key(self, api_key: str) -> Optional[Dict[str, Any]]:
        """
        Get the prompt associated with an API key
        
        Args:
            api_key: The API key
            
        Returns:
            Dictionary containing the prompt details or None if no prompt is associated
        """
        session = self.Session()
        
        try:
            # Find the API key
            api_key_obj = session.query(ApiKey).filter(ApiKey.api_key == api_key).first()
            
            if not api_key_obj:
                raise RuntimeError(f"API key {api_key} not found")
            
            # Get the associated prompt
            if api_key_obj.prompt and api_key_obj.prompt.system_prompt:
                return api_key_obj.prompt.system_prompt.to_dict()
            
            return None
        except Exception as e:
            logger.error(f"Error getting prompt for API key: {str(e)}")
            raise RuntimeError(f"Error getting prompt for API key: {str(e)}") from e
        finally:
            session.close()


def main():
    """Command-line interface for the Database API Key Manager"""
    parser = argparse.ArgumentParser(description="API Key and Prompt Manager using a database")
    
    parser.add_argument("--config", default="config.yaml", help="Path to the YAML configuration file")
    
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # API Key management commands
    # Create command
    create_parser = subparsers.add_parser("create", help="Create a new API key")
    create_parser.add_argument("--collection", required=True, help="Collection name to associate with the key")
    create_parser.add_argument("--name", required=True, help="Client name")
    create_parser.add_argument("--notes", help="Optional notes about this API key")
    create_parser.add_argument("--prompt-id", type=int, help="Existing system prompt ID to associate with the key")
    create_parser.add_argument("--prompt-name", help="Name for a new system prompt")
    create_parser.add_argument("--prompt-file", help="Path to a file containing a system prompt")
    
    # List command
    list_parser = subparsers.add_parser("list", help="List all API keys")
    
    # Deactivate command
    deactivate_parser = subparsers.add_parser("deactivate", help="Deactivate an API key")
    deactivate_parser.add_argument("--key", required=True, help="API key to deactivate")
    
    # Delete command
    delete_parser = subparsers.add_parser("delete", help="Delete an API key")
    delete_parser.add_argument("--key", required=True, help="API key to delete")
    
    # Test command
    test_parser = subparsers.add_parser("test", help="Test an API key")
    test_parser.add_argument("--key", required=True, help="API key to test")
    
    # Status command
    status_parser = subparsers.add_parser("status", help="Get the status of an API key")
    status_parser.add_argument("--key", required=True, help="API key to check")
    
    # System Prompt management commands
    prompt_parser = subparsers.add_parser("prompt", help="System prompt management")
    prompt_subparsers = prompt_parser.add_subparsers(dest="prompt_command", help="Prompt command to execute")
    
    # Create prompt command
    prompt_create_parser = prompt_subparsers.add_parser("create", help="Create a new system prompt")
    prompt_create_parser.add_argument("--name", required=True, help="Unique name for the prompt")
    prompt_create_parser.add_argument("--file", required=True, help="Path to a file containing the prompt text")
    prompt_create_parser.add_argument("--version", help="Version string (default from config)")
    
    # List prompts command
    prompt_list_parser = prompt_subparsers.add_parser("list", help="List all system prompts")
    
    # Get prompt command
    prompt_get_parser = prompt_subparsers.add_parser("get", help="Get a system prompt by ID")
    prompt_get_parser.add_argument("--id", required=True, type=int, help="Prompt ID")
    
    # Update prompt command
    prompt_update_parser = prompt_subparsers.add_parser("update", help="Update an existing system prompt")
    prompt_update_parser.add_argument("--id", required=True, type=int, help="Prompt ID to update")
    prompt_update_parser.add_argument("--file", required=True, help="Path to a file containing the updated prompt text")
    prompt_update_parser.add_argument("--version", help="New version string")
    
    # Delete prompt command
    prompt_delete_parser = prompt_subparsers.add_parser("delete", help="Delete a system prompt")
    prompt_delete_parser.add_argument("--id", required=True, type=int, help="Prompt ID to delete")
    
    # Associate prompt with API key command
    prompt_associate_parser = prompt_subparsers.add_parser("associate", help="Associate a system prompt with an API key")
    prompt_associate_parser.add_argument("--key", required=True, help="API key")
    prompt_associate_parser.add_argument("--prompt-id", required=True, type=int, help="Prompt ID to associate")

    args = parser.parse_args()
    
    try:
        manager = DbApiKeyManager(config_file=args.config)
        
        # Handle API Key commands
        if args.command == "create":
            result = manager.create_api_key(
                args.collection, 
                args.name, 
                args.notes,
                args.prompt_id,
                args.prompt_name,
                args.prompt_file
            )
            print(json.dumps(result, indent=2))
            print("\nAPI key created successfully.")
            
        elif args.command == "list":
            result = manager.list_api_keys()
            print(json.dumps(result, indent=2))
            print(f"\nFound {len(result)} API keys.")
            
        elif args.command == "deactivate":
            result = manager.deactivate_api_key(args.key)
            print(json.dumps(result, indent=2))
            print(f"\nAPI key deactivated successfully.")
            
        elif args.command == "delete":
            result = manager.delete_api_key(args.key)
            print(json.dumps(result, indent=2))
            print(f"\nAPI key deleted successfully.")
            
        elif args.command == "test":
            result = manager.test_api_key(args.key)
            print(json.dumps(result, indent=2))
            print(f"\nAPI key test completed successfully.")
            
        elif args.command == "status":
            result = manager.get_api_key_status(args.key)
            print(json.dumps(result, indent=2))
            if result.get("active"):
                print("\nAPI key is active.")
            else:
                print("\nAPI key is inactive.")
                
        # Handle System Prompt commands
        elif args.command == "prompt":
            if args.prompt_command == "create":
                prompt_text = manager._read_file_content(args.file)
                result = manager.create_prompt(args.name, prompt_text, args.version)
                print(json.dumps(result, indent=2))
                print("\nSystem prompt created successfully.")
                
            elif args.prompt_command == "list":
                result = manager.list_prompts()
                print(json.dumps(result, indent=2))
                print(f"\nFound {len(result)} system prompts.")
                
            elif args.prompt_command == "get":
                result = manager.get_prompt(args.id)
                print(json.dumps(result, indent=2))
                
            elif args.prompt_command == "update":
                prompt_text = manager._read_file_content(args.file)
                result = manager.update_prompt(args.id, prompt_text, args.version)
                print(json.dumps(result, indent=2))
                print("\nSystem prompt updated successfully.")
                
            elif args.prompt_command == "delete":
                result = manager.delete_prompt(args.id)
                print(json.dumps(result, indent=2))
                print("\nSystem prompt deleted successfully.")
                
            elif args.prompt_command == "associate":
                result = manager.associate_prompt_with_api_key(args.key, args.prompt_id)
                print(json.dumps(result, indent=2))
                print("\nSystem prompt associated with API key successfully.")
                
            else:
                prompt_parser.print_help()
                sys.exit(1)
            
        else:
            parser.print_help()
            sys.exit(1)
            
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    finally:
        # Ensure engines are cleaned up
        DbApiKeyManager.cleanup_engines()