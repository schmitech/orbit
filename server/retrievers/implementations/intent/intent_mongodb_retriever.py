"""
MongoDB-specific intent retriever implementation.

This retriever extends IntentHTTPRetriever to provide MongoDB Query Language (MQL) support,
allowing natural language queries to be translated into MongoDB find operations.
Uses the MongoDB datasource from the datasource registry for connection pooling.
"""

import logging
import traceback
import json
from typing import Dict, Any, List, Optional, Tuple
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

from retrievers.base.intent_http_base import IntentHTTPRetriever
from retrievers.base.base_retriever import RetrieverFactory
from datasources.registry import get_registry

logger = logging.getLogger(__name__)


class IntentMongoDBRetriever(IntentHTTPRetriever):
    """
    MongoDB-specific intent retriever.

    Translates natural language queries to MongoDB find operations.
    Uses MongoDB datasource from registry for connection pooling.
    Features:
    - MongoDB Query Language (MQL) generation
    - Collection management
    - Basic query operators ($eq, $gt, $lt, $in, $regex, etc.)
    - Projection and sorting support
    - MongoDB-specific response processing
    """

    def __init__(self, config: Dict[str, Any], domain_adapter=None, datasource=None, **kwargs):
        """
        Initialize MongoDB retriever.

        Args:
            config: Configuration dictionary with datasource settings
            domain_adapter: Optional domain adapter
            datasource: Optional pre-initialized datasource
            **kwargs: Additional arguments
        """
        # MongoDB uses its own client from datasource, not the generic HTTP client
        # Provide a placeholder base_url to satisfy parent class if not already set
        if 'adapter_config' in config and 'base_url' not in config['adapter_config']:
            config['adapter_config']['base_url'] = 'http://localhost:27017'  # Placeholder, not used

        super().__init__(config=config, domain_adapter=domain_adapter, datasource=datasource, **kwargs)

        # MongoDB-specific settings from adapter config
        self.database_name = self.intent_config.get('database', 'sample_mflix')
        self.default_collection = self.intent_config.get('default_collection', 'movies')
        self.default_limit = self.intent_config.get('default_limit', 100)
        self.max_limit = self.intent_config.get('max_limit', 1000)
        self.enable_text_search = self.intent_config.get('enable_text_search', True)
        self.case_insensitive_regex = self.intent_config.get('case_insensitive_regex', True)

        # Store datasource reference (will be initialized in initialize())
        self.mongo_datasource = datasource
        self.mongo_client: Optional[AsyncIOMotorClient] = None

        logger.debug(f"MongoDBRetriever initialized with database: {self.database_name}, default_collection: {self.default_collection}")

    def _get_datasource_name(self) -> str:
        """Return the datasource name."""
        return "mongodb"

    async def initialize(self) -> None:
        """Initialize the retriever and get MongoDB datasource from registry."""
        # Call parent initialization
        await super().initialize()

        # Get or create MongoDB datasource from registry
        if not self.mongo_datasource:
            registry = get_registry()
            self.mongo_datasource = registry.get_or_create_datasource(
                datasource_name="mongodb",
                config=self.config,
                logger_instance=logger
            )

        if not self.mongo_datasource:
            raise RuntimeError("Failed to initialize MongoDB datasource")

        # Initialize the datasource if not already initialized
        if not self.mongo_datasource.is_initialized:
            await self.mongo_datasource.initialize()

        # Get the MongoDB client
        self.mongo_client = self.mongo_datasource.client

        logger.debug("MongoDB retriever initialized with datasource from registry")

    async def _execute_template(self, template: Dict[str, Any],
                                parameters: Dict[str, Any]) -> Tuple[Any, Optional[str]]:
        """
        Execute MongoDB find template with parameters.

        Args:
            template: The template dictionary containing MongoDB query
            parameters: Extracted parameters for the query

        Returns:
            Tuple of (results, error_message)
        """
        try:
            # Ensure we have a MongoDB client
            if not self.mongo_client:
                return [], "MongoDB client not initialized"

            # Get MongoDB query from template
            mongo_query_template = template.get('mongodb_query', template.get('query'))
            if not mongo_query_template:
                return [], "Template has no MongoDB query"

            # Normalize parameters based on template parameter definitions
            template_params = template.get('parameters', [])
            if template_params:
                parameters = self._normalize_parameters(parameters, template_params)
                logger.debug(f"Normalized parameters: {parameters}")

            # Process the MongoDB query template with parameters
            mongo_query = self._process_mongodb_query_template(mongo_query_template, parameters)

            # Determine collection and query type
            collection_name = template.get('collection', self.default_collection)
            query_type = template.get('query_type', 'find')

            logger.debug(f"Executing MongoDB {query_type} on collection: {collection_name}")
            logger.debug(f"MongoDB Query: {json.dumps(mongo_query, indent=2)}")

            # Get collection reference
            database = self.mongo_client[template.get('database', self.database_name)]
            collection = database[collection_name]

            # Execute based on query type
            if query_type == 'find':
                results = await self._execute_find_query(collection, mongo_query, template)
            elif query_type == 'count':
                results = await self._execute_count_query(collection, mongo_query, template)
            elif query_type == 'aggregate':
                results = await self._execute_aggregate_query(collection, mongo_query, template)
            else:
                return [], f"Unsupported query type: {query_type}"

            return results, None

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error executing MongoDB template: {error_msg}")
            logger.error(traceback.format_exc())
            return [], error_msg

    def _normalize_parameters(self, parameters: Dict[str, Any], template_params: List[Dict]) -> Dict[str, Any]:
        """
        Normalize parameters based on their type definitions in the template.

        Args:
            parameters: Raw parameters extracted from query
            template_params: Template parameter definitions

        Returns:
            Normalized parameters with correct types
        """
        normalized = {}

        # Create a map of parameter names to their type definitions
        param_types = {p['name']: p.get('type', 'string') for p in template_params}

        for key, value in parameters.items():
            param_type = param_types.get(key, 'string')

            # Normalize based on type
            if param_type == 'array':
                # Convert single values to arrays
                if not isinstance(value, list):
                    normalized[key] = [value]
                else:
                    normalized[key] = value
            elif param_type == 'integer':
                # Ensure integer type
                if isinstance(value, str):
                    try:
                        normalized[key] = int(value)
                    except ValueError:
                        normalized[key] = value
                else:
                    normalized[key] = int(value) if value is not None else value
            elif param_type == 'number':
                # Ensure numeric type
                if isinstance(value, str):
                    try:
                        normalized[key] = float(value)
                    except ValueError:
                        normalized[key] = value
                else:
                    normalized[key] = float(value) if value is not None else value
            else:
                # Keep as-is for strings and other types
                normalized[key] = value

        return normalized

    def _process_mongodb_query_template(self, template: str, parameters: Dict[str, Any]) -> Dict:
        """
        Process MongoDB query template with variable substitution.

        Args:
            template: MongoDB query template string (may contain Jinja2 syntax)
            parameters: Parameters for substitution

        Returns:
            Processed MongoDB query as dictionary with proper BSON types
        """
        rendered = None
        try:
            if self.template_processor:
                # Use the template processor to render the MongoDB query
                rendered = self.template_processor.render_sql(
                    template,
                    parameters=parameters,
                    preserve_unknown=False
                )
                logger.debug(f"Rendered MongoDB query template:\n{rendered}")
                parsed = json.loads(rendered)
            else:
                # Fallback: simple parameter substitution
                rendered = template
                for key, value in parameters.items():
                    placeholder = f"{{{{{key}}}}}"
                    if isinstance(value, str):
                        # Escape quotes in string values
                        escaped_value = value.replace('"', '\\"')
                        rendered = rendered.replace(placeholder, f'"{escaped_value}"')
                    elif isinstance(value, (list, dict)):
                        rendered = rendered.replace(placeholder, json.dumps(value))
                    else:
                        rendered = rendered.replace(placeholder, str(value))
                logger.debug(f"Rendered MongoDB query template (fallback):\n{rendered}")
                parsed = json.loads(rendered)

            # Convert Extended JSON types (e.g., {"$oid": "..."}) to BSON types
            return self._convert_extended_json(parsed)

        except Exception as e:
            logger.error(f"Error processing MongoDB query template: {e}")
            if rendered:
                logger.error(f"Rendered template that failed to parse:\n{rendered}")
            logger.error(f"Template parameters: {parameters}")
            # Return an empty query as fallback
            return {"filter": {}}

    def _convert_extended_json(self, obj: Any) -> Any:
        """
        Recursively convert MongoDB Extended JSON types to BSON types.

        Handles:
        - {"$oid": "..."} -> ObjectId(...)
        - {"$date": "..."} -> datetime (if needed in future)

        Args:
            obj: The object to convert (dict, list, or primitive)

        Returns:
            Converted object with proper BSON types
        """
        if isinstance(obj, dict):
            # Check for Extended JSON ObjectId format
            if len(obj) == 1 and "$oid" in obj:
                try:
                    return ObjectId(obj["$oid"])
                except Exception as e:
                    logger.warning(f"Invalid ObjectId value: {obj['$oid']}, error: {e}")
                    return obj

            # Recursively process all values
            return {key: self._convert_extended_json(value) for key, value in obj.items()}

        elif isinstance(obj, list):
            return [self._convert_extended_json(item) for item in obj]

        return obj

    def _normalize_sort_spec(self, sort_spec):
        """
        Normalize sort specification to Motor-compatible format.

        Converts from list of dicts [{"field": -1}] to list of tuples [("field", -1)]

        Args:
            sort_spec: Sort specification (list of dicts or list of tuples)

        Returns:
            List of tuples suitable for Motor's sort() method
        """
        if not sort_spec:
            return []

        normalized = []
        for item in sort_spec:
            if isinstance(item, dict):
                # Convert dict to tuple: {"field": -1} -> ("field", -1)
                for field, direction in item.items():
                    normalized.append((field, direction))
            elif isinstance(item, tuple):
                # Already in correct format
                normalized.append(item)
            else:
                logger.warning(f"Unexpected sort specification format: {item}")

        return normalized

    async def _execute_find_query(self, collection, mongo_query: Dict, template: Dict) -> List[Dict]:
        """
        Execute MongoDB find query.

        Args:
            collection: MongoDB collection reference
            mongo_query: Processed MongoDB query
            template: The template being executed

        Returns:
            List of result dictionaries
        """
        try:
            # Extract query components
            filter_query = mongo_query.get('filter', {})
            projection = mongo_query.get('projection', {})
            sort_spec = mongo_query.get('sort', [])
            limit_val = mongo_query.get('limit', self.default_limit)
            skip_val = mongo_query.get('skip', 0)

            # Apply limit constraints
            limit_val = min(limit_val, self.max_limit)

            # Normalize sort specification for Motor
            if sort_spec:
                sort_spec = self._normalize_sort_spec(sort_spec)

            # Build cursor
            cursor = collection.find(filter_query, projection)

            if sort_spec:
                cursor = cursor.sort(sort_spec)

            if skip_val > 0:
                cursor = cursor.skip(skip_val)

            cursor = cursor.limit(limit_val)

            # Execute query and convert to list
            results = []
            async for document in cursor:
                # Convert ObjectId to string for JSON serialization
                if '_id' in document:
                    document['_id'] = str(document['_id'])
                results.append(document)

            return results

        except Exception as e:
            logger.error(f"Error executing MongoDB find query: {e}")
            logger.error(f"Filter: {filter_query}")
            logger.error(f"Projection: {projection}")
            logger.error(f"Sort: {sort_spec}")
            logger.error(traceback.format_exc())
            return []

    async def _execute_count_query(self, collection, mongo_query: Dict, template: Dict) -> List[Dict]:
        """
        Execute MongoDB count query.

        Args:
            collection: MongoDB collection reference
            mongo_query: Processed MongoDB query
            template: The template being executed

        Returns:
            List with count result
        """
        try:
            filter_query = mongo_query.get('filter', {})
            count = await collection.count_documents(filter_query)
            return [{'count': count}]

        except Exception as e:
            logger.error(f"Error executing MongoDB count query: {e}")
            return [{'count': 0}]

    async def _execute_aggregate_query(self, collection, mongo_query: Dict, template: Dict) -> List[Dict]:
        """
        Execute MongoDB aggregation pipeline query.

        Args:
            collection: MongoDB collection reference
            mongo_query: Processed MongoDB query with pipeline
            template: The template being executed

        Returns:
            List of aggregation result dictionaries
        """
        try:
            # Extract pipeline from query
            pipeline = mongo_query.get('pipeline', [])

            if not pipeline:
                logger.warning("Aggregation query has no pipeline")
                return []

            # Execute aggregation pipeline
            cursor = collection.aggregate(pipeline)

            # Convert cursor to list
            results = []
            async for document in cursor:
                # Convert ObjectId to string for JSON serialization
                if '_id' in document:
                    # Check if _id is ObjectId, otherwise keep as is (for grouped results)
                    if hasattr(document['_id'], '__class__') and document['_id'].__class__.__name__ == 'ObjectId':
                        document['_id'] = str(document['_id'])
                results.append(document)

            return results

        except Exception as e:
            logger.error(f"Error executing MongoDB aggregation query: {e}")
            logger.error(traceback.format_exc())
            return []

    def _format_http_results(self, results: Any, template: Dict,
                            parameters: Dict, similarity: float) -> List[Dict[str, Any]]:
        """
        Format MongoDB results into context documents.

        Args:
            results: MongoDB query results
            template: The template that was executed
            parameters: Parameters used in the query
            similarity: Template matching similarity score

        Returns:
            List of formatted context items
        """
        if not results:
            return [{
                "content": "No results found for your query.",
                "metadata": {
                    "source": "mongodb",
                    "template_id": template.get('id'),
                    "parameters_used": parameters,
                    "similarity": similarity,
                    "result_count": 0
                },
                "confidence": similarity
            }]

        # Format the response
        content = self._format_mongodb_results(results, template)

        # Build metadata
        metadata = {
            "source": "mongodb",
            "template_id": template.get('id'),
            "query_intent": template.get('description', ''),
            "parameters_used": parameters,
            "similarity": similarity,
            "result_count": len(results),
            "results": results
        }

        return [{
            "content": content,
            "metadata": metadata,
            "confidence": similarity
        }]

    def _format_mongodb_results(self, documents: List[Dict], template: Dict) -> str:
        """
        Format MongoDB results as human-readable text.

        All documents are included in the formatted output to ensure the LLM
        has access to complete query results for accurate responses.

        Args:
            documents: List of MongoDB documents
            template: The template being executed

        Returns:
            Formatted string representation
        """
        lines = []

        # Check if this is a count result
        if documents and 'count' in documents[0]:
            count = documents[0]['count']
            lines.append(f"Found {count} documents matching your query.")
            return '\n'.join(lines)

        # Format regular document results
        total = len(documents)
        lines.append(f"Found {total} documents:")

        display_fields = template.get('display_fields', None)

        # Format ALL documents (not just first 10) so LLM has complete data
        for i, doc in enumerate(documents, 1):
            lines.append(f"\n{i}.")

            if display_fields:
                for field in display_fields:
                    # Handle nested field access (e.g., "imdb.rating")
                    value = self._get_nested_value(doc, field)
                    if value is not None:
                        if isinstance(value, dict):
                            value = json.dumps(value, indent=2)
                        lines.append(f"   {field}: {value}")
            else:
                # Show all fields except _id if it's just the ObjectId string
                for key, value in doc.items():
                    if key == '_id' and isinstance(value, str) and len(value) == 24:
                        continue  # Skip ObjectId strings
                    if isinstance(value, dict):
                        value = json.dumps(value, indent=2)
                    lines.append(f"   {key}: {value}")

        return '\n'.join(lines)

    def _get_nested_value(self, doc: Dict, field_path: str) -> Any:
        """
        Get a value from a nested document using dot notation.

        Args:
            doc: The document to extract from
            field_path: Dot-separated path (e.g., "imdb.rating")

        Returns:
            The value at the path, or None if not found
        """
        parts = field_path.split('.')
        value = doc
        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return None
        return value

    async def get_collection_info(self, collection_name: str) -> Dict:
        """
        Get collection information for template generation.

        Args:
            collection_name: Collection name

        Returns:
            Collection info dictionary
        """
        try:
            if not self.mongo_client:
                return {}

            database = self.mongo_client[self.database_name]
            collection = database[collection_name]

            # Get collection stats
            stats = await database.command("collStats", collection_name)
            
            # Get sample document to understand schema
            sample_doc = await collection.find_one()
            
            return {
                'count': stats.get('count', 0),
                'size': stats.get('size', 0),
                'avgObjSize': stats.get('avgObjSize', 0),
                'sample_document': sample_doc
            }
        except Exception as e:
            logger.error(f"Failed to get collection info: {e}")
            return {}

    async def execute_aggregation(self, collection_name: str, pipeline: List[Dict]) -> List[Dict]:
        """
        Execute MongoDB aggregation pipeline.

        Args:
            collection_name: Collection name
            pipeline: Aggregation pipeline

        Returns:
            Aggregation results
        """
        try:
            if not self.mongo_client:
                return []

            database = self.mongo_client[self.database_name]
            collection = database[collection_name]

            results = []
            async for doc in collection.aggregate(pipeline):
                if '_id' in doc:
                    doc['_id'] = str(doc['_id'])
                results.append(doc)

            return results

        except Exception as e:
            logger.error(f"Failed to execute aggregation: {e}")
            return []


# Register the MongoDB retriever
RetrieverFactory.register_retriever('intent_mongodb', IntentMongoDBRetriever)
logger.info("Registered IntentMongoDBRetriever as 'intent_mongodb'")
