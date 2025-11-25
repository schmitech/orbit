"""
NATO Classification Conversion GraphQL API Test Script

This example demonstrates how to interact with the NATO Classification Conversion
GraphQL API to test authentication, queries, and mutations.

Requirements:
    pip install requests

Basic Usage:
    # Test with default credentials (will prompt for email/password)
    python test_nato_graphql.py

    # Test with credentials from command line
    python test_nato_graphql.py --email user@nato.int --password your_password

    # Test specific operations
    python test_nato_graphql.py --test auth
    python test_nato_graphql.py --test queries
    python test_nato_graphql.py --test mutations
    
    # Introspect schema to see all available queries and mutations
    python test_nato_graphql.py --test introspect
    
    # Test which queries work without authentication
    python test_nato_graphql.py --test public
    
    # Run sample queries/mutations from documentation examples
    python test_nato_graphql.py --test sample

Command-Line Arguments:
    --endpoint       GraphQL endpoint URL (default: https://security-converter.obrienlabs.dev/graphql)
    --email          User email for authentication
    --password       User password for authentication
    --test           Specific test to run: auth, queries, mutations, all, connection, introspect, public, or sample (default: all)

Features:
    - JWT token authentication
    - Query nations, authorities, and classification schemas
    - Submit conversion requests
    - View conversion history
    - Comprehensive error handling

Notes:
    - The API requires authentication for most operations
    - All requests use the production endpoint by default
    - JWT tokens are automatically included in authenticated requests
"""

import requests
import json
import argparse
import sys
import uuid
from typing import Optional, Dict, Any


class NATOGraphQLClient:
    """Client for interacting with the NATO Classification Conversion GraphQL API."""

    def __init__(self, endpoint: str = "https://security-converter.obrienlabs.dev/graphql"):
        """
        Initialize the GraphQL client.

        Args:
            endpoint: GraphQL API endpoint URL
        """
        self.endpoint = endpoint
        self.token: Optional[str] = None
        self.email: Optional[str] = None

    def _execute_query(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute a GraphQL query or mutation.

        Args:
            query: GraphQL query/mutation string
            variables: Optional variables dictionary

        Returns:
            Response JSON as dictionary
        """
        headers = {
            "Content-Type": "application/json",
        }

        # Add authorization header if token is available
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        try:
            response = requests.post(self.endpoint, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"❌ Request failed: {e}")
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_data = e.response.json()
                    print(f"   Error details: {json.dumps(error_data, indent=2)}")
                except:
                    print(f"   Response: {e.response.text}")
            raise

    def sign_in(self, email: str, password: str) -> bool:
        """
        Authenticate and obtain JWT token.

        Args:
            email: User email
            password: User password

        Returns:
            True if authentication successful, False otherwise
        """
        mutation = """
        mutation SignIn($input: SignInInput!) {
            signIn(input: $input) {
                bearer
                email
                role
            }
        }
        """

        variables = {
            "input": {
                "email": email,
                "password": password
            }
        }

        try:
            result = self._execute_query(mutation, variables)
            
            if "errors" in result:
                print(f"❌ Authentication failed: {result['errors']}")
                return False

            sign_in_data = result.get("data", {}).get("signIn")
            if sign_in_data and sign_in_data.get("bearer"):
                self.token = sign_in_data["bearer"]
                self.email = sign_in_data.get("email", email)
                print(f"✅ Authentication successful!")
                print(f"   Email: {self.email}")
                print(f"   Role: {sign_in_data.get('role', 'N/A')}")
                return True
            else:
                print("❌ Authentication failed: No token received")
                return False

        except Exception as e:
            print(f"❌ Authentication error: {e}")
            return False

    def query_nations(self) -> bool:
        """Query all available nations."""
        query = """
        query {
            nations {
                id
                nationCode
                nationName
            }
        }
        """

        try:
            result = self._execute_query(query)
            
            if "errors" in result:
                print(f"❌ Query failed: {result['errors']}")
                return False

            nations = result.get("data", {}).get("nations", [])
            print(f"✅ Found {len(nations)} nations:")
            for nation in nations:
                print(f"   - {nation.get('nationCode')}: {nation.get('nationName')}")
            return True

        except Exception as e:
            print(f"❌ Query error: {e}")
            return False

    def query_authorities(self) -> bool:
        """
        Query all authorities.
        
        Note: This query may not exist or may require authentication.
        Run --test introspect to see all available queries.
        """
        query = """
        query {
            authorities {
                id
                name
                email
                nation {
                    nationCode
                    nationName
                }
            }
        }
        """

        try:
            result = self._execute_query(query)
            
            if "errors" in result:
                error_msg = str(result["errors"][0].get("message", "Unknown error"))
                if "unknown field" in error_msg.lower():
                    print(f"⚠️  'authorities' query doesn't exist in the schema")
                    print(f"   Error: {error_msg}")
                    print(f"   💡 Run '--test introspect' to see available queries")
                    return False
                else:
                    print(f"❌ Query failed: {error_msg}")
                    return False

            authorities = result.get("data", {}).get("authorities", [])
            print(f"✅ Found {len(authorities)} authorities:")
            for auth in authorities[:5]:  # Show first 5
                nation = auth.get("nation", {})
                print(f"   - {auth.get('name')} ({auth.get('email')}) - {nation.get('nationCode', 'N/A')}")
            if len(authorities) > 5:
                print(f"   ... and {len(authorities) - 5} more")
            return True

        except Exception as e:
            print(f"❌ Query error: {e}")
            return False

    def query_classification_schema(self, nation_code: str = "USA") -> bool:
        """Query classification schema for a specific nation."""
        query = """
        query ClassificationSchema($nationCode: String!) {
            classificationSchemasByNationCode(nationCode: $nationCode) {
                id
                nationCode
                toNatoUnclassified
                toNatoRestricted
                toNatoConfidential
                toNatoSecret
                toNatoTopSecret
                version
            }
        }
        """

        variables = {"nationCode": nation_code}

        try:
            result = self._execute_query(query, variables)
            
            if "errors" in result:
                print(f"❌ Query failed: {result['errors']}")
                return False

            schemas = result.get("data", {}).get("classificationSchemasByNationCode", [])
            if schemas:
                schema = schemas[0]
                print(f"✅ Classification schema for {nation_code}:")
                print(f"   Version: {schema.get('version', 'N/A')}")
                print(f"   UNCLASSIFIED → {schema.get('toNatoUnclassified', 'N/A')}")
                print(f"   RESTRICTED → {schema.get('toNatoRestricted', 'N/A')}")
                print(f"   CONFIDENTIAL → {schema.get('toNatoConfidential', 'N/A')}")
                print(f"   SECRET → {schema.get('toNatoSecret', 'N/A')}")
                print(f"   TOP SECRET → {schema.get('toNatoTopSecret', 'N/A')}")
            else:
                print(f"⚠️  No classification schema found for {nation_code}")
            return True

        except Exception as e:
            print(f"❌ Query error: {e}")
            return False

    def query_conversion_requests(self) -> bool:
        """Query all conversion requests."""
        query = """
        query {
            conversionRequests {
                id
                sourceNationCode
                sourceNationClassification
                targetNationCodes
                createdAt
                completedAt
                creator {
                    name
                    email
                }
            }
        }
        """

        try:
            result = self._execute_query(query)
            
            if "errors" in result:
                print(f"❌ Query failed: {result['errors']}")
                return False

            requests = result.get("data", {}).get("conversionRequests", [])
            print(f"✅ Found {len(requests)} conversion requests:")
            for req in requests[:5]:  # Show first 5
                creator = req.get("creator", {})
                status = "✅ Completed" if req.get("completedAt") else "⏳ Pending"
                print(f"   - {req.get('id')[:8]}... {status}")
                print(f"     {req.get('sourceNationCode')} {req.get('sourceNationClassification')} → {req.get('targetNationCodes')}")
                print(f"     Created: {req.get('createdAt')}")
            if len(requests) > 5:
                print(f"   ... and {len(requests) - 5} more")
            return True

        except Exception as e:
            print(f"❌ Query error: {e}")
            return False

    def query_conversion_requests_by_creator(self, creator_id: Optional[str] = None) -> bool:
        """
        Query conversion requests by creator ID (Example 2 from documentation).
        
        Args:
            creator_id: Optional creator ID. If not provided, will try to get from first request.
        """
        # First, try to get a creator ID from existing requests if not provided
        if not creator_id:
            try:
                all_requests = self.query_conversion_requests()
                if all_requests:
                    # Get creator ID from first request (this is a simplified approach)
                    print("   ℹ️  Note: This query requires a valid creatorId")
                    print("   Run query_conversion_requests first to get a creator ID")
                    return False
            except:
                pass
        
        query = """
        query ConversionRequestsByCreator($creatorId: UUID!) {
            conversionRequestsByCreatorId(creatorId: $creatorId) {
                id
                sourceNationCode
                sourceNationClassification
                targetNationCodes
                createdAt
                isCompleted
                dataObject {
                    title
                }
            }
        }
        """
        
        if not creator_id:
            print("⚠️  creatorId is required for this query")
            print("   Get a creatorId from conversionRequests query first")
            return False
        
        variables = {"creatorId": creator_id}
        
        try:
            result = self._execute_query(query, variables)
            
            if "errors" in result:
                print(f"❌ Query failed: {result['errors']}")
                return False

            requests = result.get("data", {}).get("conversionRequestsByCreatorId", [])
            print(f"✅ Found {len(requests)} conversion requests for creator {creator_id[:8]}...")
            for req in requests[:3]:  # Show first 3
                status = "✅ Completed" if req.get("isCompleted") else "⏳ Pending"
                print(f"   - {req.get('id')[:8]}... {status}")
                print(f"     Title: {req.get('dataObject', {}).get('title', 'N/A')}")
                print(f"     {req.get('sourceNationCode')} {req.get('sourceNationClassification')} → {req.get('targetNationCodes')}")
            if len(requests) > 3:
                print(f"   ... and {len(requests) - 3} more")
            return True

        except Exception as e:
            print(f"❌ Query error: {e}")
            return False

    def submit_sample_conversion_request(
        self, 
        user_id: Optional[str] = None,
        authority_id: Optional[str] = None
    ) -> bool:
        """
        Submit a sample conversion request based on Example 1 from documentation.
        
        This demonstrates the complete conversion workflow with realistic sample data.
        
        Args:
            user_id: User UUID (required for actual submission)
            authority_id: Authority UUID (required for actual submission)
        """
        print("\n📝 Sample Conversion Request (Example 1 from documentation)")
        print("   Scenario: US agency converting SECRET document for UK and France")
        
        if not user_id or not authority_id:
            print("\n⚠️  This mutation requires valid userId and authorityId")
            print("   These should be obtained from authenticated queries")
            print("   Showing the mutation structure instead...")
            
            mutation_example = """
mutation SubmitConversion($input: ConversionRequestInput!) {
  submitConversionRequest(conversionData: $input) {
    request {
      id
      sourceNationCode
      targetNationCodes
    }
    response {
      natoEquivalent
      targetNationClassifications
    }
    success
    message
  }
}
"""
            print("\n📋 Mutation Structure:")
            print(mutation_example)
            
            print("\n📋 Sample Variables (from documentation):")
            sample_vars = {
                "input": {
                    "userId": "123e4567-e89b-12d3-a456-426614174000",
                    "authorityId": "987e6543-e21b-12d3-a456-426614174000",
                    "dataObject": {
                        "title": "Intelligence Assessment: Eastern Europe",
                        "description": "Comprehensive intelligence report on regional threats"
                    },
                    "metadata": {
                        "identifier": "urn:uuid:770e8400-e29b-41d4-a716-446655440002",
                        "authorizationReference": "FRAGO 2024-027",
                        "authorizationReferenceDate": "2024-03-20T10:30:00",
                        "originatorOrganizationId": "987e6543-e21b-12d3-a456-426614174000",
                        "custodianOrganizationId": "987e6543-e21b-12d3-a456-426614174000",
                        "format": "application/pdf",
                        "formatSize": 5242880,
                        "securityClassification": "SECRET",
                        "releasableToCountries": ["USA", "GBR", "FRA"],
                        "releasableToOrganizations": ["NATO"],
                        "disclosureCategory": "Category B",
                        "handlingRestrictions": ["CUI", "NOFORN"],
                        "handlingAuthority": "EO 13526",
                        "domain": "INTEL",
                        "tags": ["regional", "threat-assessment", "strategic"]
                    },
                    "sourceNationClassification": "SECRET",
                    "sourceNationCode": "USA",
                    "targetNationCodes": ["GBR", "FRA"]
                }
            }
            print(json.dumps(sample_vars, indent=2))
            return False
        
        mutation = """
        mutation SubmitConversion($input: ConversionRequestInput!) {
            submitConversionRequest(conversionData: $input) {
                request {
                    id
                    sourceNationCode
                    targetNationCodes
                    createdAt
                }
                response {
                    id
                    natoEquivalent
                    targetNationClassifications
                }
                success
                message
            }
        }
        """
        
        variables = {
            "input": {
                "userId": user_id,
                "authorityId": authority_id,
                "dataObject": {
                    "title": "Intelligence Assessment: Eastern Europe",
                    "description": "Comprehensive intelligence report on regional threats"
                },
                "metadata": {
                    "identifier": f"urn:uuid:{uuid.uuid4()}",
                    "authorizationReference": "FRAGO 2024-027",
                    "authorizationReferenceDate": "2024-03-20T10:30:00",
                    "originatorOrganizationId": authority_id,
                    "custodianOrganizationId": authority_id,
                    "format": "application/pdf",
                    "formatSize": 5242880,
                    "securityClassification": "SECRET",
                    "releasableToCountries": ["USA", "GBR", "FRA"],
                    "releasableToOrganizations": ["NATO"],
                    "disclosureCategory": "Category B",
                    "handlingRestrictions": ["CUI", "NOFORN"],
                    "handlingAuthority": "EO 13526",
                    "domain": "INTEL",
                    "tags": ["regional", "threat-assessment", "strategic"]
                },
                "sourceNationClassification": "SECRET",
                "sourceNationCode": "USA",
                "targetNationCodes": ["GBR", "FRA"]
            }
        }
        
        try:
            result = self._execute_query(mutation, variables)
            
            if "errors" in result:
                print(f"❌ Mutation failed: {result['errors']}")
                return False

            response_data = result.get("data", {}).get("submitConversionRequest", {})
            if response_data:
                request_data = response_data.get("request", {})
                response_result = response_data.get("response", {})
                
                print(f"✅ Conversion request submitted successfully!")
                print(f"   Request ID: {request_data.get('id', 'N/A')}")
                print(f"   Source: {request_data.get('sourceNationCode')} → {request_data.get('targetNationCodes')}")
                print(f"   NATO Equivalent: {response_result.get('natoEquivalent', 'N/A')}")
                print(f"   Target Classifications: {response_result.get('targetNationClassifications', {})}")
                print(f"   Success: {response_data.get('success', False)}")
                print(f"   Message: {response_data.get('message', 'N/A')}")
                return True
            else:
                print("⚠️  Unexpected response format")
                return False

        except Exception as e:
            print(f"❌ Mutation error: {e}")
            import traceback
            traceback.print_exc()
            return False

    def introspect_schema(self, detailed: bool = True) -> bool:
        """
        Introspect the GraphQL schema to show all available queries and mutations.
        
        Args:
            detailed: If True, show detailed information including arguments and types
        """
        if detailed:
            query = """
            query IntrospectionQuery {
                __schema {
                    description
                    queryType {
                        name
                        description
                        fields {
                            name
                            description
                            args {
                                name
                                type {
                                    name
                                    kind
                                    ofType {
                                        name
                                        kind
                                    }
                                }
                                description
                            }
                            type {
                                name
                                kind
                                ofType {
                                    name
                                    kind
                                }
                            }
                        }
                    }
                    mutationType {
                        name
                        description
                        fields {
                            name
                            description
                            args {
                                name
                                type {
                                    name
                                    kind
                                    ofType {
                                        name
                                        kind
                                    }
                                }
                                description
                            }
                            type {
                                name
                                kind
                                ofType {
                                    name
                                    kind
                                }
                            }
                        }
                    }
                }
            }
            """
        else:
            query = """
            query IntrospectionQuery {
                __schema {
                    description
                    queryType {
                        name
                        description
                        fields {
                            name
                            description
                        }
                    }
                    mutationType {
                        name
                        description
                        fields {
                            name
                            description
                        }
                    }
                }
            }
            """

        try:
            result = self._execute_query(query)
            
            if "errors" in result:
                print(f"❌ Introspection failed: {result['errors']}")
                return False

            schema = result.get("data", {}).get("__schema", {})
            schema_desc = schema.get("description")
            if schema_desc:
                print("\n" + "="*60)
                print("📘 SCHEMA INFO")
                print("="*60)
                print(schema_desc)
            
            # Show Queries
            query_type = schema.get("queryType")
            if query_type:
                query_root_desc = query_type.get("description")
                queries = query_type.get("fields", [])
                print("\n" + "="*60)
                root_name = query_type.get("name", "Query")
                print(f"📊 {root_name.upper()} FIELDS")
                print("="*60)
                if query_root_desc:
                    print(query_root_desc)
                if queries:
                    for q in queries:
                        name = q.get("name", "N/A")
                        desc = q.get("description", "No description")
                        print(f"\n✅ {name}")
                        if desc and desc != "No description":
                            print(f"   Description: {desc}")
                        
                        if detailed:
                            # Show arguments
                            args = q.get("args", [])
                            if args:
                                print(f"   Arguments:")
                                for arg in args:
                                    arg_name = arg.get("name", "N/A")
                                    arg_type = self._format_type(arg.get("type", {}))
                                    arg_desc = arg.get("description", "")
                                    print(f"     - {arg_name}: {arg_type}")
                                    if arg_desc:
                                        print(f"       {arg_desc}")
                            
                            # Show return type
                            return_type = q.get("type", {})
                            if return_type:
                                type_str = self._format_type(return_type)
                                print(f"   Returns: {type_str}")
                else:
                    print("   No queries found")
            
            # Show Mutations
            mutation_type = schema.get("mutationType")
            if mutation_type:
                mutation_root_desc = mutation_type.get("description")
                mutations = mutation_type.get("fields", [])
                print("\n" + "="*60)
                root_name = mutation_type.get("name", "Mutation")
                print(f"✏️  {root_name.upper()} FIELDS")
                print("="*60)
                if mutation_root_desc:
                    print(mutation_root_desc)
                if mutations:
                    for m in mutations:
                        name = m.get("name", "N/A")
                        desc = m.get("description", "No description")
                        print(f"\n✅ {name}")
                        if desc and desc != "No description":
                            print(f"   Description: {desc}")
                        
                        if detailed:
                            # Show arguments
                            args = m.get("args", [])
                            if args:
                                print(f"   Arguments:")
                                for arg in args:
                                    arg_name = arg.get("name", "N/A")
                                    arg_type = self._format_type(arg.get("type", {}))
                                    arg_desc = arg.get("description", "")
                                    print(f"     - {arg_name}: {arg_type}")
                                    if arg_desc:
                                        print(f"       {arg_desc}")
                            
                            # Show return type
                            return_type = m.get("type", {})
                            if return_type:
                                type_str = self._format_type(return_type)
                                print(f"   Returns: {type_str}")
                else:
                    print("   No mutations found")
            
            print("\n" + "="*60)
            print("💡 TIP: Use these queries/mutations in your script or GraphQL Playground")
            print("="*60)
            
            return True

        except Exception as e:
            print(f"❌ Introspection error: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _format_type(self, type_info: Dict[str, Any]) -> str:
        """
        Format a GraphQL type for display.
        
        Args:
            type_info: Type information from introspection
            
        Returns:
            Formatted type string
        """
        kind = type_info.get("kind", "")
        name = type_info.get("name")
        of_type = type_info.get("ofType")
        
        if kind == "NON_NULL":
            if of_type:
                return f"{self._format_type(of_type)}!"
            return "!"
        elif kind == "LIST":
            if of_type:
                return f"[{self._format_type(of_type)}]"
            return "[]"
        elif name:
            return name
        else:
            return kind or "Unknown"

    def test_public_queries(self) -> bool:
        """
        Test which queries work without authentication.
        This helps identify public endpoints.
        """
        print("\n" + "="*60)
        print("🔓 TESTING PUBLIC QUERIES (No Authentication)")
        print("="*60)
        
        # Common queries that might be public
        # Note: Run --test introspect to see all available queries
        test_queries = [
            ("nations", """
                query {
                    nations {
                        id
                        nationCode
                        nationName
                    }
                }
            """),
            ("classificationSchemasByNationCode (USA)", """
                query {
                    classificationSchemasByNationCode(nationCode: "USA") {
                        nationCode
                        toNatoUnclassified
                        toNatoRestricted
                        toNatoConfidential
                        toNatoSecret
                        toNatoTopSecret
                    }
                }
            """),
            ("classificationSchemasByNationCode (GBR)", """
                query {
                    classificationSchemasByNationCode(nationCode: "GBR") {
                        nationCode
                        toNatoUnclassified
                        toNatoRestricted
                        toNatoConfidential
                        toNatoSecret
                        toNatoTopSecret
                    }
                }
            """),
        ]
        
        results = []
        for query_name, query in test_queries:
            print(f"\n🧪 Testing: {query_name}")
            try:
                # Temporarily remove token to test without auth
                original_token = self.token
                self.token = None
                
                result = self._execute_query(query)
                
                # Restore token
                self.token = original_token
                
                if "errors" in result:
                    error_msg = str(result["errors"][0].get("message", "Unknown error"))
                    if "authentication" in error_msg.lower() or "unauthorized" in error_msg.lower():
                        print(f"   ❌ Requires authentication")
                    elif "unknown field" in error_msg.lower():
                        print(f"   ❌ Query doesn't exist: {error_msg[:100]}")
                    else:
                        print(f"   ⚠️  Error: {error_msg[:100]}")
                    results.append((query_name, False))
                else:
                    print(f"   ✅ Works without authentication!")
                    data = result.get("data", {})
                    # Show a sample of the data
                    if data:
                        first_key = list(data.keys())[0] if data else None
                        if first_key:
                            items = data[first_key]
                            if isinstance(items, list) and len(items) > 0:
                                print(f"   📊 Found {len(items)} items")
                            elif items:
                                print(f"   📊 Data available")
                    results.append((query_name, True))
            except Exception as e:
                # Restore token on error
                self.token = original_token
                print(f"   ❌ Failed: {e}")
                results.append((query_name, False))
        
        print("\n" + "="*60)
        public_count = sum(1 for _, success in results if success)
        print(f"📊 Results: {public_count}/{len(results)} queries work without authentication")
        print("="*60)
        print("\n💡 Tip: Run '--test introspect' to see all available queries")
        print("   Some queries may require authentication or have different names")
        print("="*60)
        
        return public_count > 0

    def test_connection(self) -> bool:
        """Test basic connection to the GraphQL endpoint."""
        query = """
        query {
            __typename
        }
        """

        try:
            result = self._execute_query(query)
            if "errors" not in result:
                print("✅ GraphQL endpoint is reachable")
                return True
            else:
                print(f"❌ Endpoint returned errors: {result['errors']}")
                return False
        except Exception as e:
            print(f"❌ Connection test failed: {e}")
            return False


def run_auth_test(client: NATOGraphQLClient, email: str, password: str) -> bool:
    """Run authentication tests."""
    print("\n" + "="*60)
    print("🔐 AUTHENTICATION TESTS")
    print("="*60)
    
    success = client.sign_in(email, password)
    return success


def run_query_tests(client: NATOGraphQLClient) -> bool:
    """Run query tests."""
    print("\n" + "="*60)
    print("📊 QUERY TESTS")
    print("="*60)
    
    if not client.token:
        print("❌ Not authenticated. Please authenticate first.")
        return False

    results = []
    results.append(("Nations", client.query_nations()))
    results.append(("Authorities", client.query_authorities()))
    results.append(("USA Classification Schema", client.query_classification_schema("USA")))
    results.append(("GBR Classification Schema", client.query_classification_schema("GBR")))
    results.append(("Conversion Requests", client.query_conversion_requests()))

    success_count = sum(1 for _, result in results if result)
    print(f"\n✅ Query tests: {success_count}/{len(results)} passed")
    return success_count == len(results)


def run_mutation_tests(client: NATOGraphQLClient) -> bool:
    """Run mutation tests."""
    print("\n" + "="*60)
    print("✏️  MUTATION TESTS")
    print("="*60)
    
    if not client.token:
        print("❌ Not authenticated. Please authenticate first.")
        return False

    # For now, just show that mutations would work
    print("ℹ️  Mutation tests require valid userId and authorityId")
    print("   These can be obtained from the authorities query")
    client.submit_test_conversion_request()
    return True


def run_sample_tests(client: NATOGraphQLClient) -> bool:
    """
    Run sample queries and mutations based on complete examples from documentation.
    
    These demonstrate real-world usage patterns from:
    https://security-converter.obrienlabs.dev/
    """
    print("\n" + "="*60)
    print("📚 SAMPLE QUERIES & MUTATIONS (From Documentation Examples)")
    print("="*60)
    print("Based on: https://security-converter.obrienlabs.dev/")
    print("="*60)
    
    results = []
    
    # Example 3: Check Classification Schema (works without auth)
    print("\n📋 Example 3: Check Classification Schema (Poland)")
    print("   From documentation - verifying correct classification terms")
    results.append(("Classification Schema (POL)", client.query_classification_schema("POL")))
    
    # Example 2: Query Request History (requires auth)
    if client.token:
        print("\n📋 Example 2: Query Request History by Creator")
        print("   From documentation - querying conversion requests by creator ID")
        print("   ℹ️  Note: This requires a valid creatorId from existing requests")
        # Try to get a creator ID from existing requests
        try:
            # First get all requests to find a creator ID
            all_requests_result = client._execute_query("""
                query {
                    conversionRequests {
                        id
                        creator {
                            id
                        }
                    }
                }
            """)
            if "errors" not in all_requests_result:
                requests_data = all_requests_result.get("data", {}).get("conversionRequests", [])
                if requests_data and requests_data[0].get("creator", {}).get("id"):
                    creator_id = requests_data[0]["creator"]["id"]
                    results.append(("Request History by Creator", 
                                   client.query_conversion_requests_by_creator(creator_id)))
                else:
                    print("   ⚠️  No conversion requests found to get creator ID")
                    results.append(("Request History by Creator", False))
            else:
                print("   ⚠️  Could not fetch conversion requests")
                results.append(("Request History by Creator", False))
        except Exception as e:
            print(f"   ⚠️  Error: {e}")
            results.append(("Request History by Creator", False))
    else:
        print("\n📋 Example 2: Query Request History by Creator")
        print("   ⚠️  Requires authentication - skipping")
        results.append(("Request History by Creator", False))
    
    # Example 1: Submit Conversion Request (requires auth and IDs)
    if client.token:
        print("\n📋 Example 1: Submit Conversion Request")
        print("   From documentation - complete conversion workflow")
        print("   ℹ️  This demonstrates the full mutation with sample data")
        results.append(("Submit Conversion Request", 
                       client.submit_sample_conversion_request()))
    else:
        print("\n📋 Example 1: Submit Conversion Request")
        print("   ⚠️  Requires authentication - showing structure only")
        results.append(("Submit Conversion Request", 
                       client.submit_sample_conversion_request()))
    
    print("\n" + "="*60)
    success_count = sum(1 for _, result in results if result)
    print(f"📊 Sample Tests: {success_count}/{len(results)} completed")
    print("="*60)
    print("\n💡 Note: Some examples require valid IDs (userId, authorityId, creatorId)")
    print("   These can be obtained from authenticated queries")
    print("="*60)
    
    return success_count > 0


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Test NATO Classification Conversion GraphQL API",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--endpoint",
        default="https://security-converter.obrienlabs.dev/graphql",
        help="GraphQL endpoint URL"
    )
    parser.add_argument(
        "--email",
        help="User email for authentication"
    )
    parser.add_argument(
        "--password",
        help="User password for authentication"
    )
    parser.add_argument(
        "--test",
        choices=["auth", "queries", "mutations", "all", "connection", "introspect", "public", "sample"],
        default="all",
        help="Specific test to run (default: all)"
    )

    args = parser.parse_args()

    # Create client
    client = NATOGraphQLClient(args.endpoint)

    # Test connection first
    if args.test == "connection":
        print("🔍 Testing GraphQL endpoint connection...")
        success = client.test_connection()
        sys.exit(0 if success else 1)

    # Introspect schema to find registration options
    if args.test == "introspect":
        print("🔍 Introspecting GraphQL schema...")
        print("   Fetching all available queries and mutations...\n")
        success = client.introspect_schema(detailed=True)
        print("\n" + "="*60)
        print("💡 Next Steps:")
        print("="*60)
        print("1. Review the queries above - some may work without authentication")
        print("2. Run: python test_nato_graphql.py --test public")
        print("   to test which queries work without authentication")
        print("3. Use the 'signIn' mutation with credentials from the administrator")
        print("4. Once authenticated, you can use all queries and mutations")
        print("="*60)
        sys.exit(0 if success else 1)

    # Test public queries
    if args.test == "public":
        success = client.test_public_queries()
        sys.exit(0 if success else 1)

    # Get credentials
    email = args.email
    password = args.password

    if not email:
        print("\n" + "="*60)
        print("🔐 AUTHENTICATION REQUIRED")
        print("="*60)
        print("⚠️  Account registration is NOT available via the API.")
        print("   Only 'signIn' mutation exists - credentials must be created")
        print("   by an administrator.")
        print("")
        print("To obtain credentials:")
        print("1. Contact the API administrator to request account creation")
        print("2. Check the documentation at:")
        print("   https://security-converter.obrienlabs.dev")
        print("   for contact information or registration instructions")
        print("3. The API is for 'official use by authorized NATO personnel only'")
        print("   - You may need to be part of an authorized organization")
        print("="*60 + "\n")
        email = input("Enter email (or press Enter to exit): ").strip()
        if not email:
            print("👋 Exiting. Run with --test introspect to explore the API schema.")
            sys.exit(0)
    
    if not password:
        import getpass
        password = getpass.getpass("Enter password: ").strip()

    if not email or not password:
        print("❌ Email and password are required")
        sys.exit(1)

    # Run tests
    all_success = True

    if args.test in ["auth", "all"]:
        all_success = run_auth_test(client, email, password) and all_success

    if args.test in ["queries", "all"] and client.token:
        all_success = run_query_tests(client) and all_success

    if args.test in ["mutations", "all"] and client.token:
        all_success = run_mutation_tests(client) and all_success

    if args.test in ["sample", "all"]:
        all_success = run_sample_tests(client) and all_success

    print("\n" + "="*60)
    if all_success:
        print("✅ All tests completed successfully!")
    else:
        print("⚠️  Some tests failed or were skipped")
    print("="*60)

    sys.exit(0 if all_success else 1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
