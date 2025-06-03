# Prompt Service Enhancement: LangChain Integration & RAG Context Management

## Overview

The **Enhanced Prompt Service** transforms ORBIT's prompt management from a simple storage system into a comprehensive **prompt orchestration platform**. Built on LangChain's templating system, it enables dynamic prompt generation, RAG context injection, and enterprise-grade prompt management.

## Strategic Vision

```
ORBIT Prompt Evolution: From Storage to Orchestration

Phase 1: Basic Storage (Current)
├── Simple Text Storage
├── Version Control
└── API Key Association

Phase 2: Enhanced Templating (Proposed)
├── LangChain Integration
├── Variable Management
├── Context Injection
└── Permission System

Phase 3: Enterprise Prompt Platform
├── Prompt Analytics
├── A/B Testing
├── Compliance Tracking
└── Multi-Modal Support
```

## Architecture Overview

```
BasePromptService (abstract base)
├── EnhancedPromptService
│   ├── Template Management
│   ├── Variable Validation
│   └── Version Control
├── RAGPromptManager
│   ├── Context Injection
│   ├── Retriever Integration
│   └── Context Formatting
└── PromptPermissionService
    ├── Access Control
    ├── Usage Tracking
    └── Compliance Monitoring
```

## Core Components

### 1. Enhanced Prompt Template Structure

```python
prompt_doc = {
    "name": str,                    # Unique identifier
    "version": str,                 # Version tracking
    "description": str,             # Purpose/description
    "template": str,                # The actual prompt template
    "variables": {                  # Variable definitions
        "required": List[str],      # Required variables
        "optional": List[str],      # Optional variables
        "defaults": Dict[str, Any]  # Default values
    },
    "context_sources": {            # RAG context integration
        "retrievers": List[str],    # Which retrievers to use
        "context_format": str,      # How to format context
        "max_tokens": int          # Context length limit
    },
    "metadata": {                   # Additional metadata
        "tags": List[str],         # Categorization
        "model_compatibility": List[str],  # Compatible models
        "created_at": datetime,
        "updated_at": datetime
    }
}
```

### 2. LangChain Integration

```python
class PromptService:
    """Enhanced prompt service with LangChain integration"""
    
    async def get_langchain_template(self, 
                                   prompt_id: Union[str, ObjectId],
                                   template_type: str = "chat") -> Union[PromptTemplate, ChatPromptTemplate]:
        """Get a LangChain prompt template instance"""
        prompt_doc = await self.get_prompt_by_id(prompt_id)
        if not prompt_doc:
            raise ValueError(f"Prompt template not found: {prompt_id}")
            
        if template_type == "chat":
            return ChatPromptTemplate.from_template(prompt_doc["template"])
        return PromptTemplate.from_template(prompt_doc["template"])
```

### 3. RAG Context Management

```python
class RAGPromptManager:
    """Manages RAG context injection into prompts"""
    
    async def prepare_prompt_with_context(self,
                                        prompt_id: Union[str, ObjectId],
                                        query: str,
                                        retrievers: List[Any]) -> str:
        """Prepare a prompt with injected RAG context"""
        # Get prompt template
        prompt_doc = await self.prompt_service.get_prompt_by_id(prompt_id)
        
        # Retrieve context from each configured retriever
        context_data = {}
        for retriever in retrievers:
            if retriever.name in prompt_doc["context_sources"]["retrievers"]:
                results = await retriever.get_relevant_documents(query)
                context_data[retriever.name] = self._format_retriever_results(results)
        
        # Inject context into prompt
        return await self.prompt_service.inject_context(prompt_id, context_data)
```

## Configuration Examples

### 1. Basic Prompt Template

```yaml
# config.yaml - Basic prompt template
prompts:
  - name: "qa_template"
    template: |
      Answer the following question based on the provided context:

      Context: {context}

      Question: {question}

      Answer:
    variables:
      required: ["question"]
      optional: ["additional_context"]
      defaults:
        additional_context: ""
    context_sources:
      retrievers: ["vector_store", "sql_store"]
      context_format: "concatenated"
      max_tokens: 1000
```

### 2. Multi-Modal Prompt Template

```yaml
prompts:
  - name: "image_analysis_template"
    template: |
      Analyze the following image and answer the question:

      Image: {image_data}
      Context: {context}
      Question: {question}

      Analysis:
    variables:
      required: ["image_data", "question"]
      optional: ["context"]
    context_sources:
      retrievers: ["image_retriever", "text_retriever"]
      context_format: "structured"
      max_tokens: 2000
```

### 3. Complex Workflow Template

```yaml
prompts:
  - name: "workflow_analysis_template"
    template: |
      Analyze the following workflow and provide recommendations:

      Workflow Data: {workflow_data}
      Historical Context: {context}
      Business Rules: {rules}

      Analysis:
    variables:
      required: ["workflow_data"]
      optional: ["context", "rules"]
    context_sources:
      retrievers: ["workflow_retriever", "history_retriever"]
      context_format: "structured"
      max_tokens: 3000
```

## Enterprise Features

### 1. Prompt Analytics

```python
class PromptAnalytics:
    """Track and analyze prompt usage and performance"""
    
    async def track_prompt_usage(self,
                               prompt_id: Union[str, ObjectId],
                               usage_data: Dict[str, Any]) -> None:
        """Track prompt usage metrics"""
        await self.mongodb.insert_one("prompt_analytics", {
            "prompt_id": prompt_id,
            "timestamp": datetime.now(UTC),
            "usage_data": usage_data,
            "performance_metrics": {
                "response_time": usage_data.get("response_time"),
                "token_usage": usage_data.get("token_usage"),
                "success_rate": usage_data.get("success_rate")
            }
        })
```

### 2. A/B Testing Support

```python
class PromptABTesting:
    """Manage A/B testing of prompt variations"""
    
    async def create_test_variants(self,
                                 base_prompt_id: Union[str, ObjectId],
                                 variants: List[Dict[str, Any]]) -> List[ObjectId]:
        """Create A/B test variants of a prompt"""
        variant_ids = []
        for variant in variants:
            variant_id = await self.prompt_service.create_prompt_template(
                name=f"{base_prompt_id}_variant_{len(variant_ids)}",
                template=variant["template"],
                variables=variant["variables"]
            )
            variant_ids.append(variant_id)
        return variant_ids
```

### 3. Compliance Tracking

```python
class PromptCompliance:
    """Track prompt compliance and audit trails"""
    
    async def track_prompt_changes(self,
                                 prompt_id: Union[str, ObjectId],
                                 change_data: Dict[str, Any]) -> None:
        """Track changes to prompts for compliance"""
        await self.mongodb.insert_one("prompt_audit_log", {
            "prompt_id": prompt_id,
            "timestamp": datetime.now(UTC),
            "change_type": change_data["type"],
            "changed_by": change_data["user"],
            "changes": change_data["changes"],
            "compliance_checks": change_data["compliance_checks"]
        })
```

## Migration Strategy

### Phase 1: Core Enhancement

```bash
# Add enhanced prompt service
orbit prompt create --name enhanced-prompt-service \
  --implementation "services.prompt.EnhancedPromptService"

# Migrate existing prompts
orbit prompt migrate --source old-prompts --target enhanced-prompts
```

### Phase 2: RAG Integration

```bash
# Add RAG prompt manager
orbit prompt create --name rag-prompt-manager \
  --implementation "services.prompt.RAGPromptManager"

# Configure retriever integration
orbit prompt configure --name rag-integration \
  --retrievers vector-store sql-store
```

### Phase 3: Enterprise Features

```bash
# Add analytics support
orbit prompt create --name prompt-analytics \
  --implementation "services.prompt.PromptAnalytics"

# Enable A/B testing
orbit prompt create --name prompt-ab-testing \
  --implementation "services.prompt.PromptABTesting"
```

## Benefits

### 1. **Enhanced Prompt Management**
- Full LangChain integration
- Dynamic context injection
- Variable validation
- Version control

### 2. **Improved RAG Integration**
- Structured context formatting
- Multiple retriever support
- Context length management
- Performance optimization

### 3. **Enterprise-Grade Features**
- Usage analytics
- A/B testing
- Compliance tracking
- Audit trails

### 4. **Developer Experience**
- Clear template structure
- Flexible configuration
- Comprehensive API
- Easy integration

## Future Enhancements

1. **Multi-Modal Support**
   - Image prompt templates
   - Audio prompt templates
   - Video prompt templates

2. **Advanced Analytics**
   - Prompt performance metrics
   - Usage patterns
   - Cost analysis
   - ROI tracking

3. **Security Enhancements**
   - Prompt encryption
   - Access control
   - Audit logging
   - Compliance checks

4. **Integration Features**
   - External system integration
   - API gateway support
   - Webhook notifications
   - Event streaming

This enhancement positions ORBIT's prompt management as a **comprehensive prompt orchestration platform** that can handle complex prompt scenarios, maintain compliance, and provide enterprise-grade features for prompt management and optimization.

## Specific Prompt Types and Migration

### 1. Safety Prompts

```yaml
# config.yaml - Safety prompt template
prompts:
  - name: "safety_evaluator"
    template: |
      You are a content safety evaluator. Your role is to evaluate queries for safety and content policy compliance.

      UNSAFE Categories Include:
      {unsafe_categories}

      You MUST respond with EXACTLY "SAFE: true" if the query is safe, or "SAFE: false" if it is not safe. Do not add any explanation or other text to your response.
    variables:
      required: ["unsafe_categories"]
      optional: []
    metadata:
      tags: ["safety", "compliance", "content-moderation"]
      model_compatibility: ["gpt-3.5-turbo", "gpt-4", "claude-2"]
      version: "1.0"
```

### 2. Example-Based Prompts

```yaml
prompts:
  - name: "city_guide"
    template: |
      You are a city guide assistant. Use the following examples to understand the expected format:

      {examples}

      Now, answer the following question about {city}:
      {question}
    variables:
      required: ["city", "question"]
      optional: ["examples"]
    context_sources:
      retrievers: ["city_guide_retriever"]
      context_format: "examples"
      max_tokens: 2000
    metadata:
      tags: ["city-guide", "examples"]
      model_compatibility: ["gpt-3.5-turbo", "gpt-4"]
```

### 3. Activity Prompts

```yaml
prompts:
  - name: "activity_recommendation"
    template: |
      Based on the following context and user preferences, recommend activities:

      User Preferences: {preferences}
      Location Context: {location_context}
      Activity History: {activity_history}

      Provide recommendations in the following format:
      {format_instructions}
    variables:
      required: ["preferences", "location_context"]
      optional: ["activity_history", "format_instructions"]
    context_sources:
      retrievers: ["activity_retriever", "user_history_retriever"]
      context_format: "structured"
      max_tokens: 1500
    metadata:
      tags: ["activities", "recommendations"]
      model_compatibility: ["gpt-3.5-turbo", "gpt-4"]
```

## Migration Examples

### 1. Converting Safety Prompt

```python
# Original safety_prompt.txt
async def migrate_safety_prompt():
    with open("prompts/safety_prompt.txt", "r") as f:
        content = f.read()
    
    # Extract unsafe categories
    unsafe_categories = content.split("UNSAFE Categories Include:")[1].split("You MUST respond")[0].strip()
    
    # Create enhanced prompt template
    prompt_doc = {
        "name": "safety_evaluator",
        "template": content,
        "variables": {
            "required": ["unsafe_categories"],
            "optional": []
        },
        "metadata": {
            "tags": ["safety", "compliance"],
            "model_compatibility": ["gpt-3.5-turbo", "gpt-4"],
            "version": "1.0"
        }
    }
    
    return await prompt_service.create_prompt_template(**prompt_doc)
```

### 2. Converting Example Prompts

```python
async def migrate_example_prompts():
    # Load example prompts from directory structure
    example_dirs = ["prompts/examples/city", "prompts/examples/activity"]
    
    for dir_path in example_dirs:
        examples = []
        for file in os.listdir(dir_path):
            with open(os.path.join(dir_path, file), "r") as f:
                examples.append(f.read())
        
        # Create template with examples
        prompt_doc = {
            "name": f"{os.path.basename(dir_path)}_guide",
            "template": "Use these examples:\n{examples}\n\nAnswer: {question}",
            "variables": {
                "required": ["question"],
                "optional": ["examples"],
                "defaults": {
                    "examples": "\n".join(examples)
                }
            },
            "metadata": {
                "tags": [os.path.basename(dir_path), "examples"],
                "model_compatibility": ["gpt-3.5-turbo", "gpt-4"]
            }
        }
        
        await prompt_service.create_prompt_template(**prompt_doc)
```

### 3. Migration Script

```bash
# Migrate all existing prompts to the new format
orbit prompt migrate --source prompts/ --target enhanced-prompts/ \
  --strategy template-based \
  --preserve-structure

# Verify migration
orbit prompt verify --source enhanced-prompts/ \
  --check-templates \
  --check-variables \
  --check-metadata
```

## Best Practices for Prompt Organization

1. **Directory Structure**
```
prompts/
├── safety/
│   ├── content_moderation.yaml
│   └── compliance_check.yaml
├── examples/
│   ├── city/
│   │   ├── template.yaml
│   │   └── examples/
│   └── activity/
│       ├── template.yaml
│       └── examples/
└── metadata/
    ├── tags.yaml
    └── model_compatibility.yaml
```

2. **Template Versioning**
```yaml
# prompts/safety/content_moderation.yaml
name: "content_moderation"
version: "1.0.0"
template: |
  {safety_instructions}
variables:
  required: ["safety_instructions"]
metadata:
  tags: ["safety", "moderation"]
  model_compatibility: ["gpt-3.5-turbo", "gpt-4"]
  changelog:
    - version: "1.0.0"
      date: "2024-03-20"
      changes: "Initial version"
```

3. **Example Management**
```yaml
# prompts/examples/city/template.yaml
name: "city_guide"
template: |
  {examples}
  Question: {question}
variables:
  required: ["question"]
  optional: ["examples"]
examples:
  - file: "examples/basic_guide.txt"
    weight: 1.0
  - file: "examples/advanced_guide.txt"
    weight: 0.8
```

This enhancement provides a structured way to manage your existing prompts while adding powerful new features like:
- Template versioning and tracking
- Example-based prompt management
- Safety and compliance checks
- Flexible context injection
- Metadata and tagging