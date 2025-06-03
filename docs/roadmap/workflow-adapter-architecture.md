# Workflow Adapter Architecture: Enterprise API & Webhook Orchestration

## Overview

The **Workflow Adapter System** transforms ORBIT from a retrieval-focused platform into a comprehensive **enterprise AI orchestration engine**. Built on LangChain's agent framework, it enables complex multi-step workflows that combine data retrieval, API calls, webhook notifications, and business process automation.

## Strategic Vision

```
ORBIT Evolution: From RAG to Enterprise AI Platform

Phase 1: Data Retrieval (Current)
├── SQL Adapters
├── Vector Adapters  
└── File Adapters

Phase 2: Workflow Orchestration (Proposed)
├── API Workflow Adapters
├── Webhook Integration Adapters
├── Business Process Adapters
└── Multi-Modal Workflow Adapters

Phase 3: Enterprise AI Platform
├── Complete workflow automation
├── Cross-system integration
├── Compliance and audit trails
└── Enterprise-grade reliability
```

## Architecture Overview

```
BaseAdapter (abstract base for all adapter types)
├── RetrieverAdapter (data retrieval)
│   ├── SQLRetriever
│   ├── VectorRetriever
│   └── FileRetriever
├── WorkflowAdapter (process orchestration) 🆕
│   ├── APIWorkflowAdapter
│   ├── WebhookWorkflowAdapter
│   ├── BusinessProcessAdapter
│   └── MultiModalWorkflowAdapter
└── IntegrationAdapter (external systems) 🆕
    ├── CRMIntegrationAdapter
    ├── ERPIntegrationAdapter
    └── NotificationAdapter
```

## Core Workflow Adapter Types

### 1. API Workflow Adapter

```python
# server/adapters/workflow/api_workflow_adapter.py

from typing import Dict, Any, List, Optional
import asyncio
import aiohttp
from langchain.agents import AgentExecutor
from langchain.tools import BaseTool
from langchain.schema import AgentAction, AgentFinish
from adapters.base.base_adapter import BaseAdapter

class APIWorkflowAdapter(BaseAdapter):
    """
    Orchestrates complex workflows involving multiple API calls,
    data transformation, and decision logic using LangChain agents.
    """
    
    def __init__(self, config: Dict[str, Any], **kwargs):
        super().__init__(config=config, **kwargs)
        self.workflow_config = config.get('workflow', {})
        self.api_endpoints = config.get('api_endpoints', {})
        self.tools = []
        self.agent_executor = None
        
    async def initialize(self) -> None:
        """Initialize LangChain agent with configured tools"""
        await super().initialize()
        
        # Create tools from configuration
        self.tools = await self._create_workflow_tools()
        
        # Initialize LangChain agent
        self.agent_executor = await self._create_agent_executor()
        
    async def execute_workflow(self, 
                             workflow_name: str, 
                             inputs: Dict[str, Any],
                             context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute a named workflow with given inputs"""
        
        workflow_def = self.workflow_config.get('workflows', {}).get(workflow_name)
        if not workflow_def:
            raise ValueError(f"Workflow '{workflow_name}' not found")
        
        # Prepare execution context
        execution_context = {
            'inputs': inputs,
            'context': context or {},
            'workflow_name': workflow_name,
            'steps': []
        }
        
        # Execute workflow steps
        result = await self._execute_workflow_steps(workflow_def, execution_context)
        
        return {
            'workflow_name': workflow_name,
            'result': result,
            'execution_trace': execution_context['steps'],
            'status': 'completed'
        }
    
    async def _create_workflow_tools(self) -> List[BaseTool]:
        """Create LangChain tools from configuration"""
        tools = []
        
        # API call tools
        for api_name, api_config in self.api_endpoints.items():
            tool = APICallTool(api_name, api_config)
            tools.append(tool)
        
        # Data transformation tools
        tools.append(DataTransformTool())
        tools.append(ConditionalLogicTool())
        tools.append(DataValidationTool())
        
        # Integration tools
        if self.workflow_config.get('enable_retrieval_integration'):
            tools.append(RetrievalIntegrationTool(self.config))
        
        return tools

class APICallTool(BaseTool):
    """LangChain tool for making API calls"""
    
    name: str = "api_call"
    description: str = "Make HTTP API calls to external services"
    
    def __init__(self, api_name: str, api_config: Dict[str, Any]):
        super().__init__()
        self.api_name = api_name
        self.api_config = api_config
        self.name = f"api_call_{api_name}"
        self.description = f"Call {api_name} API: {api_config.get('description', '')}"
    
    async def _arun(self, 
                   endpoint: str, 
                   method: str = "GET", 
                   data: Optional[Dict] = None,
                   headers: Optional[Dict] = None) -> str:
        """Execute API call asynchronously"""
        
        base_url = self.api_config.get('base_url', '')
        auth_config = self.api_config.get('auth', {})
        
        # Prepare request
        url = f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        request_headers = {**self.api_config.get('default_headers', {}), **(headers or {})}
        
        # Add authentication
        if auth_config.get('type') == 'bearer':
            request_headers['Authorization'] = f"Bearer {auth_config['token']}"
        elif auth_config.get('type') == 'api_key':
            request_headers[auth_config['header']] = auth_config['key']
        
        # Make request
        async with aiohttp.ClientSession() as session:
            async with session.request(
                method=method.upper(),
                url=url,
                json=data,
                headers=request_headers,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                response_data = await response.json()
                
                if response.status >= 400:
                    raise Exception(f"API call failed: {response.status} - {response_data}")
                
                return response_data
```

### 2. Webhook Workflow Adapter

```python
# server/adapters/workflow/webhook_workflow_adapter.py

class WebhookWorkflowAdapter(BaseAdapter):
    """
    Handles incoming webhooks and triggers appropriate workflows.
    Supports webhook validation, transformation, and routing.
    """
    
    def __init__(self, config: Dict[str, Any], **kwargs):
        super().__init__(config=config, **kwargs)
        self.webhook_endpoints = config.get('webhook_endpoints', {})
        self.routing_rules = config.get('routing_rules', [])
        
    async def process_webhook(self, 
                            webhook_id: str, 
                            payload: Dict[str, Any],
                            headers: Dict[str, str],
                            source_ip: str) -> Dict[str, Any]:
        """Process incoming webhook and trigger appropriate workflow"""
        
        # Validate webhook
        webhook_config = self.webhook_endpoints.get(webhook_id)
        if not webhook_config:
            raise ValueError(f"Unknown webhook: {webhook_id}")
        
        # Security validation
        if not await self._validate_webhook_security(webhook_config, payload, headers, source_ip):
            raise SecurityError("Webhook security validation failed")
        
        # Transform payload
        transformed_payload = await self._transform_webhook_payload(webhook_config, payload)
        
        # Route to appropriate workflow
        workflow_result = await self._route_webhook_to_workflow(webhook_config, transformed_payload)
        
        return {
            'webhook_id': webhook_id,
            'processed_at': datetime.now(UTC).isoformat(),
            'workflow_result': workflow_result,
            'status': 'processed'
        }
    
    async def _validate_webhook_security(self, 
                                       webhook_config: Dict[str, Any],
                                       payload: Dict[str, Any],
                                       headers: Dict[str, str],
                                       source_ip: str) -> bool:
        """Validate webhook security (signatures, IP whitelist, etc.)"""
        
        security_config = webhook_config.get('security', {})
        
        # IP whitelist validation
        if 'allowed_ips' in security_config:
            if source_ip not in security_config['allowed_ips']:
                return False
        
        # Signature validation
        if 'signature' in security_config:
            expected_signature = self._calculate_webhook_signature(
                payload, security_config['secret']
            )
            received_signature = headers.get(security_config['signature_header'])
            if expected_signature != received_signature:
                return False
        
        return True
    
    async def register_webhook_endpoint(self, 
                                      webhook_id: str, 
                                      config: Dict[str, Any]) -> str:
        """Register a new webhook endpoint"""
        
        webhook_url = f"{self.base_url}/webhooks/{webhook_id}"
        
        # Store webhook configuration
        self.webhook_endpoints[webhook_id] = {
            **config,
            'created_at': datetime.now(UTC).isoformat(),
            'url': webhook_url
        }
        
        # Update routing rules
        await self._update_webhook_routing()
        
        return webhook_url
```

### 3. Business Process Adapter

```python
# server/adapters/workflow/business_process_adapter.py

class BusinessProcessAdapter(WorkflowAdapter):
    """
    Orchestrates complex business processes that span multiple systems,
    with approval workflows, audit trails, and compliance checks.
    """
    
    def __init__(self, config: Dict[str, Any], **kwargs):
        super().__init__(config=config, **kwargs)
        self.process_definitions = config.get('business_processes', {})
        self.approval_workflows = config.get('approval_workflows', {})
        
    async def execute_business_process(self, 
                                     process_name: str,
                                     initiator: str,
                                     business_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a business process with full audit trail"""
        
        process_def = self.process_definitions.get(process_name)
        if not process_def:
            raise ValueError(f"Business process '{process_name}' not found")
        
        # Create process instance
        process_instance = await self._create_process_instance(
            process_name, initiator, business_data
        )
        
        # Execute process steps
        for step in process_def['steps']:
            step_result = await self._execute_process_step(
                process_instance, step, business_data
            )
            
            # Check if approval required
            if step.get('requires_approval'):
                approval_result = await self._handle_approval_workflow(
                    process_instance, step, step_result
                )
                if not approval_result['approved']:
                    return await self._handle_process_rejection(
                        process_instance, approval_result
                    )
        
        # Complete process
        return await self._complete_business_process(process_instance)
    
    async def _execute_process_step(self, 
                                  process_instance: Dict[str, Any],
                                  step: Dict[str, Any],
                                  business_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute individual business process step"""
        
        step_type = step.get('type')
        
        if step_type == 'api_call':
            return await self._execute_api_step(step, business_data)
        elif step_type == 'data_retrieval':
            return await self._execute_retrieval_step(step, business_data)
        elif step_type == 'notification':
            return await self._execute_notification_step(step, business_data)
        elif step_type == 'conditional':
            return await self._execute_conditional_step(step, business_data)
        else:
            raise ValueError(f"Unknown step type: {step_type}")
```

## Configuration Examples

### 1. Customer Onboarding Workflow

```yaml
# config.yaml - Customer onboarding process
adapters:
  - name: "customer-onboarding-workflow"
    type: "workflow"
    adapter: "business_process"
    implementation: "adapters.workflow.BusinessProcessAdapter"
    config:
      business_processes:
        customer_onboarding:
          description: "Complete customer onboarding process"
          steps:
            - name: "validate_customer_data"
              type: "data_validation"
              config:
                required_fields: ["name", "email", "company"]
                validation_rules:
                  email: "^[\\w\\.-]+@[\\w\\.-]+\\.[a-zA-Z]{2,}$"
                  
            - name: "check_existing_customer"
              type: "data_retrieval"
              config:
                adapter: "customer-database-sql"
                query: "SELECT * FROM customers WHERE email = {email}"
                
            - name: "create_crm_record"
              type: "api_call"
              config:
                api: "salesforce"
                endpoint: "/services/data/v54.0/sobjects/Account"
                method: "POST"
                data_mapping:
                  Name: "{company}"
                  Primary_Contact_Email__c: "{email}"
                  
            - name: "setup_user_accounts"
              type: "api_call"
              config:
                api: "auth0"
                endpoint: "/api/v2/users"
                method: "POST"
                
            - name: "send_welcome_email"
              type: "notification"
              config:
                type: "email"
                template: "customer_welcome"
                recipients: ["{email}"]
                
            - name: "notify_sales_team"
              type: "webhook"
              config:
                url: "https://hooks.slack.com/services/..."
                method: "POST"
                
      api_endpoints:
        salesforce:
          base_url: "https://company.salesforce.com"
          auth:
            type: "oauth2"
            client_id: "${SALESFORCE_CLIENT_ID}"
            client_secret: "${SALESFORCE_CLIENT_SECRET}"
            
        auth0:
          base_url: "https://company.auth0.com"
          auth:
            type: "bearer"
            token: "${AUTH0_MANAGEMENT_TOKEN}"
```

### 2. Document Processing Workflow

```yaml
adapters:
  - name: "document-processing-workflow"
    type: "workflow"
    adapter: "api_workflow"
    implementation: "adapters.workflow.APIWorkflowAdapter"
    config:
      workflows:
        legal_document_review:
          description: "Automated legal document review process"
          steps:
            - name: "extract_document_content"
              type: "file_processing"
              config:
                adapter: "file-vector"
                extract_metadata: true
                
            - name: "legal_compliance_check"
              type: "api_call"
              config:
                api: "legal_ai_service"
                endpoint: "/compliance/analyze"
                timeout: 60
                
            - name: "risk_assessment"
              type: "api_call"
              config:
                api: "risk_engine"
                endpoint: "/assess"
                
            - name: "route_for_approval"
              type: "conditional"
              config:
                condition: "risk_score > 0.7"
                if_true:
                  action: "send_for_legal_review"
                  assignee: "legal_team"
                if_false:
                  action: "auto_approve"
                  
            - name: "update_document_status"
              type: "api_call"
              config:
                api: "document_management"
                endpoint: "/documents/{document_id}/status"
                method: "PATCH"
```

### 3. Multi-Modal AI Workflow

```yaml
adapters:
  - name: "multimodal-content-workflow"
    type: "workflow"
    adapter: "multimodal_workflow"
    implementation: "adapters.workflow.MultiModalWorkflowAdapter"
    config:
      workflows:
        content_analysis_pipeline:
          description: "Analyze images, text, and audio content"
          steps:
            - name: "content_type_detection"
              type: "classification"
              config:
                models:
                  - "image_classifier"
                  - "text_analyzer"
                  - "audio_detector"
                  
            - name: "extract_text_from_image"
              type: "ocr"
              condition: "content_type == 'image'"
              config:
                api: "google_vision"
                
            - name: "transcribe_audio"
              type: "speech_to_text"
              condition: "content_type == 'audio'"
              config:
                api: "whisper_api"
                
            - name: "sentiment_analysis"
              type: "nlp"
              config:
                api: "azure_cognitive"
                
            - name: "content_moderation"
              type: "moderation"
              config:
                api: "openai_moderation"
                
            - name: "generate_summary"
              type: "llm"
              config:
                model: "gpt-4"
                prompt: "Summarize the analyzed content..."
```

## Enterprise Integration Patterns

### 1. CRM Integration Workflow

```python
# server/adapters/workflow/crm_integration_adapter.py

class CRMIntegrationAdapter(WorkflowAdapter):
    """Specialized workflow adapter for CRM systems"""
    
    async def sync_customer_data(self, customer_id: str) -> Dict[str, Any]:
        """Sync customer data across systems"""
        
        # 1. Retrieve customer from internal DB
        customer_data = await self._get_customer_data(customer_id)
        
        # 2. Enrich with external data
        enriched_data = await self._enrich_customer_data(customer_data)
        
        # 3. Update CRM system
        crm_result = await self._update_crm_record(customer_id, enriched_data)
        
        # 4. Update data warehouse
        dw_result = await self._update_data_warehouse(customer_id, enriched_data)
        
        # 5. Trigger dependent workflows
        await self._trigger_customer_workflows(customer_id, enriched_data)
        
        return {
            'customer_id': customer_id,
            'sync_timestamp': datetime.now(UTC).isoformat(),
            'systems_updated': ['crm', 'data_warehouse'],
            'workflows_triggered': ['lead_scoring', 'marketing_automation']
        }
```

### 2. ERP Integration Workflow

```python
class ERPIntegrationAdapter(WorkflowAdapter):
    """Enterprise Resource Planning integration workflows"""
    
    async def process_purchase_order(self, po_data: Dict[str, Any]) -> Dict[str, Any]:
        """Complete purchase order processing workflow"""
        
        # 1. Validate PO data
        validation_result = await self._validate_purchase_order(po_data)
        
        # 2. Check inventory levels
        inventory_check = await self._check_inventory_availability(po_data['items'])
        
        # 3. Calculate pricing and discounts
        pricing_result = await self._calculate_order_pricing(po_data)
        
        # 4. Route for approval if needed
        if pricing_result['total'] > 10000:
            approval_result = await self._route_for_approval(po_data, pricing_result)
            if not approval_result['approved']:
                return await self._handle_po_rejection(po_data, approval_result)
        
        # 5. Create ERP order
        erp_order = await self._create_erp_order(po_data, pricing_result)
        
        # 6. Update inventory reservations
        await self._update_inventory_reservations(erp_order)
        
        # 7. Send notifications
        await self._send_po_notifications(erp_order)
        
        return {
            'po_number': erp_order['po_number'],
            'status': 'processed',
            'erp_order_id': erp_order['id'],
            'estimated_delivery': erp_order['estimated_delivery']
        }
```

## Advanced Workflow Features

### 1. Conditional Logic and Branching

```python
class ConditionalWorkflowEngine:
    """Advanced conditional logic for workflows"""
    
    async def evaluate_condition(self, 
                                condition: str, 
                                context: Dict[str, Any]) -> bool:
        """Evaluate complex conditions safely"""
        
        # Support for complex expressions
        # Examples:
        # - "customer.tier == 'enterprise' and order.value > 50000"
        # - "sentiment_score < 0.3 or contains_sensitive_data"
        # - "time_since_last_order > 90 and customer.status == 'active'"
        
        safe_evaluator = SafeExpressionEvaluator()
        return safe_evaluator.evaluate(condition, context)
    
    async def execute_parallel_branches(self, 
                                       branches: List[Dict[str, Any]],
                                       context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Execute multiple workflow branches in parallel"""
        
        tasks = []
        for branch in branches:
            if await self.evaluate_condition(branch.get('condition', 'true'), context):
                task = self._execute_workflow_branch(branch, context)
                tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [r for r in results if not isinstance(r, Exception)]
```

### 2. Error Handling and Retry Logic

```python
class WorkflowErrorHandler:
    """Robust error handling for workflow execution"""
    
    async def execute_with_retry(self, 
                                step_func: Callable,
                                retry_config: Dict[str, Any],
                                context: Dict[str, Any]) -> Any:
        """Execute workflow step with configurable retry logic"""
        
        max_retries = retry_config.get('max_retries', 3)
        backoff_strategy = retry_config.get('backoff', 'exponential')
        retry_exceptions = retry_config.get('retry_on', [])
        
        for attempt in range(max_retries + 1):
            try:
                return await step_func(context)
            except Exception as e:
                if attempt == max_retries:
                    raise
                
                if retry_exceptions and type(e).__name__ not in retry_exceptions:
                    raise
                
                wait_time = self._calculate_backoff_time(attempt, backoff_strategy)
                await asyncio.sleep(wait_time)
                
                logger.warning(f"Workflow step failed, retrying in {wait_time}s: {str(e)}")
        
    def _calculate_backoff_time(self, attempt: int, strategy: str) -> float:
        """Calculate wait time based on backoff strategy"""
        if strategy == 'exponential':
            return min(2 ** attempt, 60)  # Max 60 seconds
        elif strategy == 'linear':
            return min(attempt * 2, 30)   # Max 30 seconds
        else:
            return 1.0  # Fixed 1 second
```

### 3. Workflow Monitoring and Analytics

```python
class WorkflowMonitor:
    """Monitor and analyze workflow execution"""
    
    async def track_workflow_execution(self, 
                                     workflow_id: str,
                                     execution_data: Dict[str, Any]) -> None:
        """Track workflow execution for analytics"""
        
        await self.mongodb.insert_one('workflow_executions', {
            'workflow_id': workflow_id,
            'execution_id': execution_data['execution_id'],
            'start_time': execution_data['start_time'],
            'end_time': execution_data.get('end_time'),
            'status': execution_data['status'],
            'steps_executed': execution_data['steps'],
            'total_duration': execution_data.get('duration'),
            'error_details': execution_data.get('error'),
            'resource_usage': execution_data.get('resources')
        })
    
    async def get_workflow_analytics(self, 
                                   workflow_id: str,
                                   time_range: Dict[str, Any]) -> Dict[str, Any]:
        """Get analytics for workflow performance"""
        
        pipeline = [
            {'$match': {
                'workflow_id': workflow_id,
                'start_time': {
                    '$gte': time_range['start'],
                    '$lte': time_range['end']
                }
            }},
            {'$group': {
                '_id': '$status',
                'count': {'$sum': 1},
                'avg_duration': {'$avg': '$total_duration'},
                'max_duration': {'$max': '$total_duration'},
                'min_duration': {'$min': '$total_duration'}
            }}
        ]
        
        results = await self.mongodb.aggregate('workflow_executions', pipeline)
        
        return {
            'workflow_id': workflow_id,
            'time_range': time_range,
            'execution_stats': list(results),
            'success_rate': self._calculate_success_rate(results),
            'performance_trends': await self._get_performance_trends(workflow_id, time_range)
        }
```

## CLI Integration

### Workflow Management Commands

```python
# bin/orbit.py - Enhanced with workflow commands

class OrbitCLI:
    def _add_workflow_commands(self, subparsers):
        """Add workflow management commands"""
        workflow_parser = subparsers.add_parser('workflow', help='Workflow management')
        workflow_subparsers = workflow_parser.add_subparsers(dest='workflow_command')
        
        # List workflows
        list_parser = workflow_subparsers.add_parser('list', help='List all workflows')
        
        # Execute workflow
        execute_parser = workflow_subparsers.add_parser('execute', help='Execute workflow')
        execute_parser.add_argument('--name', required=True, help='Workflow name')
        execute_parser.add_argument('--input-file', help='JSON file with input data')
        execute_parser.add_argument('--async', action='store_true', help='Execute asynchronously')
        
        # Create workflow
        create_parser = workflow_subparsers.add_parser('create', help='Create new workflow')
        create_parser.add_argument('--name', required=True, help='Workflow name')
        create_parser.add_argument('--definition-file', required=True, help='YAML workflow definition')
        
        # Monitor workflows
        monitor_parser = workflow_subparsers.add_parser('monitor', help='Monitor workflow execution')
        monitor_parser.add_argument('--workflow-id', help='Specific workflow to monitor')
        monitor_parser.add_argument('--live', action='store_true', help='Live monitoring')
        
        # Analytics
        analytics_parser = workflow_subparsers.add_parser('analytics', help='Workflow analytics')
        analytics_parser.add_argument('--workflow-id', required=True, help='Workflow to analyze')
        analytics_parser.add_argument('--days', type=int, default=30, help='Days to analyze')
```

### Usage Examples

```bash
# List available workflows
orbit workflow list

# Execute customer onboarding workflow
orbit workflow execute --name customer-onboarding \
  --input-file customer_data.json

# Create new workflow
orbit workflow create --name order-processing \
  --definition-file workflows/order_processing.yaml

# Monitor workflow execution
orbit workflow monitor --workflow-id customer-onboarding --live

# Get workflow analytics
orbit workflow analytics --workflow-id document-processing --days 7
```

## Enterprise Benefits

### 1. **Complete Business Process Automation**
- End-to-end process orchestration
- Cross-system integration
- Approval workflows with audit trails
- Compliance monitoring

### 2. **Scalable Integration Platform**
- Connect any API or webhook
- Transform and route data between systems
- Handle complex business logic
- Real-time and batch processing

### 3. **Enterprise-Grade Reliability**
- Retry mechanisms and error handling
- Monitoring and alerting
- Performance analytics
- Disaster recovery

### 4. **Developer-Friendly**
- LangChain integration for AI-powered workflows
- YAML-based workflow definitions
- Extensive CLI tooling
- Comprehensive API

## Migration Strategy

### Phase 1: Core Workflow Infrastructure
```bash
# Add workflow adapter support
orbit adapter create --type workflow --name api-workflow \
  --implementation "adapters.workflow.APIWorkflowAdapter"

# Configure basic API endpoints
orbit workflow create --name simple-api-test \
  --definition-file workflows/api_test.yaml
```

### Phase 2: Business Process Integration
```bash
# Customer onboarding workflow
orbit workflow create --name customer-onboarding \
  --definition-file workflows/customer_onboarding.yaml

# Document processing workflow  
orbit workflow create --name document-processing \
  --definition-file workflows/document_processing.yaml
```

### Phase 3: Advanced Enterprise Features
```bash
# Multi-modal workflows
orbit workflow create --name content-analysis \
  --definition-file workflows/multimodal_analysis.yaml

# ERP integration workflows
orbit workflow create --name erp-sync \
  --definition-file workflows/erp_integration.yaml
```
