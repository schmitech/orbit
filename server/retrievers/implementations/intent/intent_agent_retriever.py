"""
Agent-based intent retriever with function-calling capabilities.

This retriever extends IntentHTTPRetriever to support tool/function execution
using YAML-defined tools. Supports both single-model and multi-model patterns
(e.g., FunctionGemma-style with separate inference and function models).

Features:
- Native function-calling with models like FunctionGemma
- YAML-defined tools with function_schema and execution config
- Built-in tools (calculator, date_time, json_transform)
- HTTP tool execution (reuses parent HTTP logic)
- Optional response synthesis for natural language output
- Fallback to template matching when function calling unavailable
"""

from __future__ import annotations

import json
import logging
import re
import traceback
from typing import Any, Dict, List, Optional, Tuple

from retrievers.base.intent_http_base import IntentHTTPRetriever
from retrievers.base.base_retriever import RetrieverFactory

from .agent.tool_definitions import (
    ToolDefinition,
    ToolResultStatus,
    ExecutionType,
)
from .agent.tool_executor import ToolExecutor
from .agent.response_synthesizer import ResponseSynthesizer

logger = logging.getLogger(__name__)


class IntentAgentRetriever(IntentHTTPRetriever):
    """
    Intent-based retriever with function/tool calling capabilities.

    Extends IntentHTTPRetriever to handle `tool_type: "function"` templates,
    executing built-in tools or HTTP calls based on the template configuration.

    Supports two modes:
    1. Native function calling (preferred): Send all tools to FunctionGemma,
       let it choose which function to call and extract parameters.
    2. Template matching (fallback): Use vector similarity to find matching
       templates, then extract parameters with LLM.

    Configuration options:
        function_model_provider: Optional separate provider for function calling
        function_model: Optional separate model for function calling
        use_native_function_calling: Use native tool-calling API (default: True)
        enable_builtin_tools: Enable calculator, date_time, json_transform
        synthesize_response: Generate natural language response from tool results
        function_output_format: Output format (json or text)
    """

    def __init__(
        self,
        config: Dict[str, Any],
        domain_adapter=None,
        datasource=None,
        **kwargs
    ):
        """
        Initialize the agent retriever.

        Args:
            config: Configuration dictionary with adapter settings
            domain_adapter: Optional domain adapter
            datasource: Optional datasource instance
            **kwargs: Additional arguments
        """
        super().__init__(
            config=config,
            domain_adapter=domain_adapter,
            datasource=datasource,
            **kwargs
        )

        # Agent-specific configuration
        self.function_model_provider = self.intent_config.get('function_model_provider')
        self.function_model = self.intent_config.get('function_model')
        self.use_native_function_calling = self.intent_config.get('use_native_function_calling', True)
        self.enable_builtin_tools = self.intent_config.get('enable_builtin_tools', True)
        self.synthesize_response_enabled = self.intent_config.get('synthesize_response', True)
        self.function_output_format = self.intent_config.get('function_output_format', 'json')
        self.verbose = self.intent_config.get('verbose', False)

        # Will be initialized during initialize()
        self.function_client = None
        self.tool_executor: Optional[ToolExecutor] = None
        self.response_synthesizer: Optional[ResponseSynthesizer] = None

        # Cache for loaded function tools
        self._function_tools: Optional[List[ToolDefinition]] = None
        self._function_tools_map: Optional[Dict[str, ToolDefinition]] = None

        logger.info(
            f"IntentAgentRetriever configured with "
            f"function_model={self.function_model or 'same as inference'}, "
            f"native_function_calling={self.use_native_function_calling}, "
            f"builtin_tools={self.enable_builtin_tools}"
        )

    def _get_datasource_name(self) -> str:
        """Return the datasource identifier for the agent retriever."""
        return "agent"

    async def initialize(self) -> None:
        """Initialize the agent retriever with function model and tool executor."""
        # Initialize parent (HTTP client, embedding, inference, vector store, etc.)
        await super().initialize()

        # Initialize function model client
        await self._initialize_function_client()

        # Initialize tool executor with HTTP executor callback
        self.tool_executor = ToolExecutor(
            http_executor=self._execute_http_tool,
            verbose=self.verbose,
        )

        # Initialize response synthesizer
        self.response_synthesizer = ResponseSynthesizer(
            inference_client=self.inference_client,
            verbose=self.verbose,
        )

        # Load and cache function tools
        await self._load_function_tools()

        logger.info("IntentAgentRetriever initialization complete")

    async def _initialize_function_client(self) -> None:
        """
        Initialize the function-calling model client.

        If function_model_provider and function_model are configured,
        creates a separate client. Otherwise, uses the main inference client.

        Uses deep copy to avoid mutating the shared config and properly
        applies the model override for the function model.
        """
        if self.function_model_provider and self.function_model:
            # Create separate function model client
            import copy
            from inference.pipeline.providers import UnifiedProviderFactory as ProviderFactory

            logger.info(
                f"Initializing separate function model: "
                f"{self.function_model_provider}/{self.function_model}"
            )

            # Deep copy to avoid mutating shared config
            function_config = copy.deepcopy(self.config)
            function_config['inference_provider'] = self.function_model_provider

            # Ensure the inference section exists for the provider
            if 'inference' not in function_config:
                function_config['inference'] = {}
            if self.function_model_provider not in function_config['inference']:
                function_config['inference'][self.function_model_provider] = {}

            # Set the model - this is what OllamaConfig reads
            function_config['inference'][self.function_model_provider]['model'] = self.function_model

            # For Ollama, also check if we should use a preset
            if self.function_model_provider == 'ollama':
                ollama_presets = function_config.get('ollama_presets', {})
                if self.function_model in ollama_presets:
                    # Apply preset configuration
                    preset = ollama_presets[self.function_model]
                    for key, value in preset.items():
                        function_config['inference']['ollama'][key] = value
                    logger.info(
                        f"Applied Ollama preset '{self.function_model}' "
                        f"(actual model: {preset.get('model', self.function_model)})"
                    )
                else:
                    logger.info(f"Using Ollama model directly: {self.function_model}")

            try:
                self.function_client = ProviderFactory.create_provider_by_name(
                    self.function_model_provider, function_config
                )
                await self.function_client.initialize()
                actual_model = getattr(self.function_client, 'model', self.function_model)
                logger.info(f"Function model initialized: {actual_model}")
            except Exception as e:
                logger.warning(
                    f"Failed to initialize function model {self.function_model}: {e}. "
                    f"Falling back to inference model."
                )
                self.function_client = self.inference_client
        else:
            # Use same model for inference and function calling
            logger.info("Using inference model for function calling (single-model mode)")
            self.function_client = self.inference_client

    async def _load_function_tools(self) -> None:
        """
        Load all function-type templates and convert them to ToolDefinitions.

        Caches the tools for use with native function calling.
        """
        if self._function_tools is not None:
            return  # Already loaded

        self._function_tools = []
        self._function_tools_map = {}

        # Get all templates from the domain adapter (same source as parent class)
        if not self.domain_adapter:
            logger.warning("Domain adapter not available, cannot load function tools")
            return

        try:
            # Get all templates from domain adapter
            all_templates = self.domain_adapter.get_all_templates()

            if not all_templates:
                logger.warning("No templates found in domain adapter")
                return

            for template in all_templates:
                if not isinstance(template, dict):
                    continue

                # Only process function-type templates
                if template.get('tool_type') != 'function':
                    continue

                tool_def = self.tool_executor.convert_template_to_tool_definition(template)
                if tool_def:
                    self._function_tools.append(tool_def)
                    self._function_tools_map[tool_def.id] = tool_def

                    # Also map by function name
                    func_name = tool_def.function_schema.name
                    if func_name and func_name != tool_def.id:
                        self._function_tools_map[func_name] = tool_def

            logger.info(f"Loaded {len(self._function_tools)} function tools for native calling")

            if self._function_tools:
                tool_names = [t.function_schema.name for t in self._function_tools]
                logger.info(f"Available function tools: {tool_names}")

        except Exception as e:
            logger.error(f"Error loading function tools: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self._function_tools = []
            self._function_tools_map = {}

    def _build_openai_tools(self) -> List[Dict[str, Any]]:
        """
        Build OpenAI-compatible tool schemas for function calling.

        Returns:
            List of tool definitions in OpenAI format
        """
        if not self._function_tools:
            return []

        return [tool.to_openai_tool() for tool in self._function_tools]

    async def get_relevant_context(
        self,
        query: str,
        api_key: Optional[str] = None,
        collection_name: Optional[str] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Get relevant context for the query using function calling or template matching.

        Flow:
        1. If native function calling is enabled and tools are available:
           - Send query + all tools to FunctionGemma
           - FunctionGemma chooses which function to call and extracts parameters
           - Execute the chosen function
        2. If function calling fails or is disabled:
           - Fall back to template matching (vector similarity)
           - Extract parameters with LLM
           - Execute the matched template
        """
        # Ensure initialized
        if not self.initialized:
            await self.initialize()

        logger.info(
            f"get_relevant_context called - native_function_calling={self.use_native_function_calling}, "
            f"function_tools_count={len(self._function_tools) if self._function_tools else 0}, "
            f"function_model={self.function_model}"
        )

        # Try native function calling first
        if self.use_native_function_calling and self._function_tools:
            result = await self._try_native_function_calling(query)
            if result:
                return result
            logger.info("Native function calling did not return a result, falling back to template matching")

        # Fall back to template matching
        return await self._template_matching_flow(query)

    async def _try_native_function_calling(self, query: str) -> Optional[List[Dict[str, Any]]]:
        """
        Try to handle the query using native function calling.

        Sends the query and all available tools to the function model,
        letting it decide which function to call and extract parameters.

        Args:
            query: The user's query

        Returns:
            Formatted results if successful, None if function calling fails
        """
        try:
            # Build tool schemas
            tools = self._build_openai_tools()

            if not tools:
                logger.debug("No tools available for native function calling")
                return None

            logger.info(f"Attempting native function calling with {len(tools)} tools")
            if self.verbose:
                tool_names = [t.get('function', {}).get('name', 'unknown') for t in tools]
                logger.debug(f"Available tools for function calling: {tool_names}")

            # Call the function model with tools
            function_call = await self._call_function_model(query, tools)

            if not function_call:
                logger.info("Function model did not return a valid function call")
                return None

            # Extract function name and arguments
            func_name = function_call.get('name') or function_call.get('function', {}).get('name')
            arguments = function_call.get('arguments') or function_call.get('function', {}).get('arguments', {})

            if not func_name:
                logger.warning("Function call missing function name")
                return None

            # Parse arguments if they're a string
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    logger.warning(f"Could not parse function arguments: {arguments}")
                    arguments = {}

            logger.info(f"Function model selected: {func_name} with arguments: {arguments}")

            # Find the tool definition
            tool_def = self._function_tools_map.get(func_name)

            if not tool_def:
                logger.warning(f"Unknown function called: {func_name}")
                return None

            # Execute the tool
            result = await self.tool_executor.execute(tool_def, arguments)

            if result.status == ToolResultStatus.ERROR:
                logger.warning(f"Tool execution failed: {result.error}")
                return None

            # Format and return results
            template = {
                'id': tool_def.id,
                'description': tool_def.description,
                'function_schema': {
                    'name': tool_def.function_schema.name,
                    'description': tool_def.function_schema.description,
                },
                'tool_type': 'function',
            }

            return self._format_function_results(
                results=result.data,
                template=template,
                parameters=arguments,
                similarity=1.0,  # Native function calling = high confidence
                query=query
            )

        except Exception as e:
            logger.error(f"Error in native function calling: {e}")
            logger.error(traceback.format_exc())
            return None

    def _parse_functiongemma_response(self, response: str) -> Optional[Dict[str, Any]]:
        """
        Parse FunctionGemma's custom output format.

        FunctionGemma outputs:
        <start_function_call>call:function_name{param:<escape>value<escape>}<end_function_call>

        Args:
            response: Raw response string from FunctionGemma

        Returns:
            Dict with 'name' and 'arguments', or None if parsing fails
        """
        if not response:
            return None

        # Look for the function call pattern
        pattern = r'<start_function_call>call:(\w+)\{([^}]*)\}<end_function_call>'
        match = re.search(pattern, response)

        if not match:
            # Try without the special tokens (some outputs may be cleaner)
            pattern_simple = r'call:(\w+)\{([^}]*)\}'
            match = re.search(pattern_simple, response)

        if not match:
            return None

        function_name = match.group(1)
        params_str = match.group(2)

        # Parse parameters: param:<escape>value<escape>
        arguments = {}
        if params_str:
            # Split by comma for multiple params, but be careful with escaped values
            # Pattern: param_name:<escape>value<escape>
            param_pattern = r'(\w+):<escape>([^<]*)<escape>'
            param_matches = re.findall(param_pattern, params_str)

            for param_name, param_value in param_matches:
                # Try to convert to appropriate type
                param_value = param_value.strip()

                # Try numeric conversion
                try:
                    if '.' in param_value:
                        arguments[param_name] = float(param_value)
                    else:
                        arguments[param_name] = int(param_value)
                except ValueError:
                    # Check for boolean
                    if param_value.lower() == 'true':
                        arguments[param_name] = True
                    elif param_value.lower() == 'false':
                        arguments[param_name] = False
                    # Check for array (comma-separated in brackets)
                    elif param_value.startswith('[') and param_value.endswith(']'):
                        try:
                            arguments[param_name] = json.loads(param_value)
                        except json.JSONDecodeError:
                            arguments[param_name] = param_value
                    else:
                        arguments[param_name] = param_value

            # If no escape-style params found, try simple key:value format
            if not arguments and ':' in params_str:
                simple_pattern = r'(\w+):([^,}]+)'
                simple_matches = re.findall(simple_pattern, params_str)
                for param_name, param_value in simple_matches:
                    param_value = param_value.strip()
                    try:
                        if '.' in param_value:
                            arguments[param_name] = float(param_value)
                        else:
                            arguments[param_name] = int(param_value)
                    except ValueError:
                        arguments[param_name] = param_value

        logger.debug(f"Parsed FunctionGemma response: {function_name}({arguments})")
        return {"name": function_name, "arguments": arguments}

    def _build_functiongemma_prompt(
        self,
        query: str,
        tools: List[Dict[str, Any]]
    ) -> str:
        """
        Build a prompt in FunctionGemma's expected format.

        FunctionGemma expects:
        - A developer role message to activate function calling
        - Tools as JSON schema definitions
        - User query

        Args:
            query: The user's query
            tools: List of tool definitions in OpenAI format

        Returns:
            Formatted prompt string
        """
        # Build tool definitions as JSON
        tool_json = json.dumps(tools, indent=2)

        # FunctionGemma format with developer role
        prompt = f"""<start_of_turn>developer
You are a model that can do function calling with the following functions:

{tool_json}

Based on the user's query, call the appropriate function with the correct parameters.
Output format: <start_function_call>call:function_name{{param:<escape>value<escape>}}<end_function_call>
<end_of_turn>
<start_of_turn>user
{query}
<end_of_turn>
<start_of_turn>model
"""
        return prompt

    async def _call_function_model(
        self,
        query: str,
        tools: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        Call the function model with tools and get a function call response.

        Supports multiple response formats:
        1. FunctionGemma-style: <start_function_call>call:func{param:<escape>val<escape>}<end_function_call>
        2. OpenAI-style: {"function_call": {"name": "...", "arguments": {...}}}
        3. Ollama-style: {"message": {"tool_calls": [{"function": {...}}]}}
        4. Direct format: {"name": "...", "arguments": {...}}

        Args:
            query: The user's query
            tools: List of tool definitions in OpenAI format

        Returns:
            Function call dict with 'name' and 'arguments', or None
        """
        if not self.function_client:
            return None

        try:
            # Check if the client supports native tool calling
            if hasattr(self.function_client, 'generate_with_tools'):
                # Use native tool calling API
                response = await self.function_client.generate_with_tools(
                    prompt=query,
                    tools=tools
                )
            elif hasattr(self.function_client, 'chat_with_tools'):
                # Alternative method name
                response = await self.function_client.chat_with_tools(
                    messages=[{"role": "user", "content": query}],
                    tools=tools
                )
            else:
                # Fall back to prompt-based function calling
                response = await self._prompt_based_function_calling(query, tools)
                return response

            # Parse the response based on format
            if isinstance(response, str):
                # Check for FunctionGemma format first
                gemma_result = self._parse_functiongemma_response(response)
                if gemma_result:
                    return gemma_result
                # Try JSON parsing
                return self._parse_json_response(response)

            if isinstance(response, dict):
                # Check if response contains text that might be FunctionGemma format
                text_content = response.get('response') or response.get('text') or response.get('content', '')
                if text_content and '<start_function_call>' in text_content:
                    gemma_result = self._parse_functiongemma_response(text_content)
                    if gemma_result:
                        return gemma_result

                # OpenAI format
                if 'function_call' in response:
                    return response['function_call']

                # Ollama format
                if 'message' in response and 'tool_calls' in response.get('message', {}):
                    tool_calls = response['message']['tool_calls']
                    if tool_calls and len(tool_calls) > 0:
                        return tool_calls[0].get('function', tool_calls[0])

                # Direct format
                if 'name' in response:
                    return response

                # Check for choices (OpenAI chat completion format)
                if 'choices' in response and len(response['choices']) > 0:
                    choice = response['choices'][0]
                    message = choice.get('message', {})
                    if 'function_call' in message:
                        return message['function_call']
                    if 'tool_calls' in message and message['tool_calls']:
                        return message['tool_calls'][0].get('function')

            return None

        except Exception as e:
            error_msg = str(e) if str(e) else type(e).__name__
            logger.error(f"Error calling function model: {error_msg}")
            if self.verbose:
                logger.error(traceback.format_exc())
            return None

    async def _prompt_based_function_calling(
        self,
        query: str,
        tools: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        Fallback: Use a prompt to get the model to output a function call.

        Uses FunctionGemma's format when function_model contains 'gemma' or 'functiongemma',
        otherwise uses a generic JSON-based format.
        """
        # Check if we're using FunctionGemma
        is_functiongemma = (
            self.function_model and
            ('functiongemma' in self.function_model.lower() or
             'function-gemma' in self.function_model.lower() or
             'function_gemma' in self.function_model.lower())
        )

        if is_functiongemma:
            # Use FunctionGemma-specific format
            prompt = self._build_functiongemma_prompt(query, tools)
            logger.info("Using FunctionGemma format for function calling")
            try:
                response = await self.function_client.generate(prompt)
                logger.info(f"FunctionGemma raw response: {response[:500] if response else 'None'}...")

                result = self._parse_functiongemma_response(response)
                if result:
                    logger.info(f"FunctionGemma parsed result: {result}")
                    return result

                # Fall back to JSON parsing if FunctionGemma format not found
                logger.info("FunctionGemma format not found, trying JSON parsing")
                json_result = self._parse_json_response(response)
                if json_result:
                    logger.info(f"JSON parsed result: {json_result}")
                    return json_result

                logger.warning("Could not parse FunctionGemma response as function call")
                return None
            except Exception as e:
                error_msg = str(e) if str(e) else type(e).__name__
                logger.error(f"Error in FunctionGemma function calling: {error_msg}")
                if self.verbose:
                    logger.error(traceback.format_exc())
                return None

        # Generic prompt-based function calling (for other models)
        tool_descriptions = []
        for tool in tools:
            func = tool.get('function', {})
            name = func.get('name', 'unknown')
            desc = func.get('description', '')
            params = func.get('parameters', {}).get('properties', {})

            param_strs = []
            for pname, pinfo in params.items():
                ptype = pinfo.get('type', 'any')
                pdesc = pinfo.get('description', '')
                param_strs.append(f"    - {pname} ({ptype}): {pdesc}")

            tool_desc = f"- {name}: {desc}"
            if param_strs:
                tool_desc += "\n  Parameters:\n" + "\n".join(param_strs)
            tool_descriptions.append(tool_desc)

        prompt = f"""You are a function-calling assistant. Based on the user's query, decide which function to call and extract the required parameters.

Available functions:
{chr(10).join(tool_descriptions)}

User query: "{query}"

Instructions:
- Choose the most appropriate function for the query
- Extract parameter values from the query
- Return ONLY a JSON object in this exact format:
{{"name": "function_name", "arguments": {{"param1": value1, "param2": value2}}}}
- Use appropriate types (numbers for numeric values, arrays for lists)
- Do not include any explanation, just the JSON

Response:"""

        try:
            response = await self.function_client.generate(prompt)
            return self._parse_json_response(response)
        except Exception as e:
            error_msg = str(e) if str(e) else type(e).__name__
            logger.error(f"Error in prompt-based function calling: {error_msg}")
            if self.verbose:
                logger.error(traceback.format_exc())
            return None

    async def _template_matching_flow(self, query: str) -> List[Dict[str, Any]]:
        """
        Handle the query using template matching (fallback flow).

        Uses vector similarity to find matching templates, then extracts
        parameters with LLM.
        """
        # Find matching templates
        matching_templates = await self._find_best_templates(query)

        if not matching_templates:
            logger.warning(f"No matching templates found for query: {query[:100]}...")
            return []

        # Try templates in order of similarity
        for template_info in matching_templates:
            template = template_info['template']
            similarity = template_info['similarity']
            template_id = template.get('id', 'unknown')
            tool_type = template.get('tool_type', 'query')

            if similarity < self.confidence_threshold:
                continue

            logger.debug(f"Attempting template: {template_id} (similarity: {similarity:.2%}, type: {tool_type})")

            # Handle function templates with custom extraction
            if tool_type == 'function':
                # Extract parameters using LLM based on function schema
                parameters = await self._extract_function_parameters(query, template)

                # Always log extracted parameters for debugging
                logger.info(f"Template {template_id}: Extracted parameters: {parameters}")

                # Execute the function template
                results, error = await self._execute_function_template(template, parameters)

                if error:
                    logger.warning(f"Template {template_id} execution failed: {error}")
                    continue

                # Format results for function templates (handles simple values)
                return self._format_function_results(results, template, parameters, similarity, query)

            else:
                # Use parent's parameter extraction for query templates
                if self.parameter_extractor:
                    parameters = await self.parameter_extractor.extract_parameters(query, template)
                else:
                    parameters = {}

                # Execute query template
                results, error = await self._execute_http_query_template(template, parameters)

                if error:
                    logger.warning(f"Template {template_id} execution failed: {error}")
                    continue

                # Use parent's formatting for query templates
                return self._format_http_results(results, template, parameters, similarity)

        logger.warning(f"All templates failed for query: {query[:100]}...")
        return []

    async def _extract_function_parameters(
        self,
        query: str,
        template: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Extract function parameters from the query using LLM.

        Uses the function_schema to understand what parameters are needed
        and extracts them from the natural language query.
        """
        function_schema = template.get('function_schema', {})
        parameters_schema = function_schema.get('parameters', [])

        if not parameters_schema:
            return {}

        # Build parameter descriptions for the LLM
        param_descriptions = []
        for param in parameters_schema:
            param_name = param.get('name', '')
            param_type = param.get('type', 'string')
            param_desc = param.get('description', '')
            param_required = param.get('required', False)
            param_example = param.get('example', '')

            desc = f"- {param_name} ({param_type}): {param_desc}"
            if param_example:
                desc += f" Example: {param_example}"
            if param_required:
                desc += " [REQUIRED]"
            param_descriptions.append(desc)

        # Create extraction prompt
        extraction_prompt = f"""Extract parameter values from the user's query for a function call.

Function: {function_schema.get('name', 'unknown')}
Description: {function_schema.get('description', '')}

Parameters needed (extract each as a SEPARATE top-level key):
{chr(10).join(param_descriptions)}

User query: "{query}"

Instructions:
- Extract EACH parameter as a separate top-level key in the JSON response
- For 'data' or array parameters: extract the array/list exactly as provided, do NOT add extra fields to objects
- For other parameters like 'field', 'order', 'operator': extract from the descriptive text of the query
- Return ONLY a valid JSON object with parameter names as keys
- Use appropriate types (numbers for numeric values, strings for text)
- If a parameter value is not found in the query, omit it from the response
- Do not include any explanation, just the JSON object

Example for a sort operation:
Query: "Sort this by price descending: [{{"name": "A", "price": 10}}, {{"name": "B", "price": 5}}]"
Correct response: {{"data": [{{"name": "A", "price": 10}}, {{"name": "B", "price": 5}}], "field": "price", "order": "desc"}}
WRONG response: {{"data": [{{"name": "A", "price": 10, "field": "price"}}, ...]}}

JSON response:"""

        try:
            # Use function model (or inference model in single-model mode)
            client = self.function_client or self.inference_client

            if client:
                response = await client.generate(extraction_prompt)

                # Parse JSON from response
                parameters = self._parse_json_response(response)

                if self.verbose:
                    logger.debug(f"LLM extraction response: {response[:500]}")
                    logger.debug(f"Parsed parameters: {parameters}")

                return parameters
            else:
                logger.warning("No inference client available for parameter extraction")
                return {}

        except Exception as e:
            logger.error(f"Error extracting function parameters: {e}")
            return {}

    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        """Parse JSON from LLM response, handling various formats."""
        if not response:
            return {}

        # Clean up the response
        response = response.strip()

        # Try to find JSON in the response
        # Look for JSON block markers
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', response)
        if json_match:
            response = json_match.group(1).strip()

        # Try to find a JSON object
        json_start = response.find('{')
        json_end = response.rfind('}')

        if json_start != -1 and json_end != -1:
            json_str = response[json_start:json_end + 1]
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass

        # Try parsing the whole response
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            logger.warning(f"Could not parse JSON from response: {response[:200]}")
            return {}

    def _format_function_results(
        self,
        results: Any,
        template: Dict[str, Any],
        parameters: Dict[str, Any],
        similarity: float,
        query: str
    ) -> List[Dict[str, Any]]:
        """
        Format function execution results for the pipeline.

        Handles simple values (numbers, strings) as well as complex types.
        Optionally synthesizes a natural language response.
        """
        template_id = template.get('id', 'unknown')
        template_description = template.get('description', '')
        function_name = template.get('function_schema', {}).get('name', template_id)

        # Build content based on result type
        if results is None:
            content = "The operation completed but returned no data."
        elif isinstance(results, (int, float)):
            content = f"Result: {results}"
        elif isinstance(results, bool):
            content = f"Result: {'Yes' if results else 'No'}"
        elif isinstance(results, str):
            content = results
        elif isinstance(results, list):
            if len(results) == 0:
                content = "No results found."
            else:
                try:
                    content = json.dumps(results, indent=2, default=str)
                except (TypeError, ValueError):
                    content = str(results)
        elif isinstance(results, dict):
            try:
                content = json.dumps(results, indent=2, default=str)
            except (TypeError, ValueError):
                content = str(results)
        else:
            content = str(results)

        return [{
            "content": content,
            "metadata": {
                "source": "intent_agent",
                "template_id": template_id,
                "function_name": function_name,
                "template_description": template_description,
                "tool_type": "function",
                "parameters_used": parameters,
                "result_type": type(results).__name__,
                "similarity": similarity,
                "native_function_calling": similarity == 1.0,  # 1.0 indicates native calling was used
            },
            "confidence": similarity
        }]

    def _format_http_results(
        self,
        results: Any,
        template: Dict[str, Any],
        parameters: Dict[str, Any],
        similarity: float
    ) -> List[Dict[str, Any]]:
        """
        Format HTTP query template results into context documents.

        Required abstract method from IntentHTTPRetriever base class.
        Handles standard query templates (non-function type).

        Args:
            results: HTTP API results
            template: The template that was executed
            parameters: Parameters used in the request
            similarity: Template matching similarity score

        Returns:
            List of formatted context items
        """
        template_id = template.get('id', 'unknown')
        template_description = template.get('description', '')

        if not results:
            return [{
                "content": "No results found for your request.",
                "metadata": {
                    "source": "intent_agent_http",
                    "template_id": template_id,
                    "template_description": template_description,
                    "parameters_used": parameters,
                    "similarity": similarity,
                    "result_count": 0
                },
                "confidence": similarity
            }]

        # Format results based on type
        if isinstance(results, list):
            result_count = len(results)
            try:
                content = json.dumps(results, indent=2, default=str)
            except (TypeError, ValueError):
                content = str(results)
        elif isinstance(results, dict):
            result_count = 1
            try:
                content = json.dumps(results, indent=2, default=str)
            except (TypeError, ValueError):
                content = str(results)
        else:
            result_count = 1
            content = str(results)

        return [{
            "content": content,
            "metadata": {
                "source": "intent_agent_http",
                "template_id": template_id,
                "template_description": template_description,
                "tool_type": "query",
                "parameters_used": parameters,
                "similarity": similarity,
                "result_count": result_count,
                "results": results
            },
            "confidence": similarity
        }]

    async def _execute_template(
        self,
        template: Dict[str, Any],
        parameters: Dict[str, Any]
    ) -> Tuple[Any, Optional[str]]:
        """
        Execute a template, routing between query and function types.

        Overrides parent to handle `tool_type: "function"` templates.

        Args:
            template: The matched template dictionary
            parameters: Extracted parameters for execution

        Returns:
            Tuple of (results, error_message)
        """
        tool_type = template.get('tool_type', 'query')

        if tool_type == 'function':
            return await self._execute_function_template(template, parameters)

        # Fall back to parent HTTP execution for query templates
        return await self._execute_http_query_template(template, parameters)

    async def _execute_function_template(
        self,
        template: Dict[str, Any],
        parameters: Dict[str, Any]
    ) -> Tuple[Any, Optional[str]]:
        """
        Execute a function-type template.

        Args:
            template: Template with tool_type="function"
            parameters: Extracted parameters

        Returns:
            Tuple of (results, error_message)
        """
        template_id = template.get('id', 'unknown')

        try:
            # Convert template to ToolDefinition
            tool_def = self.tool_executor.convert_template_to_tool_definition(template)

            if not tool_def:
                return [], f"Failed to parse tool definition from template {template_id}"

            if self.verbose:
                logger.debug(f"Executing function tool: {tool_def.id}")
                logger.debug(f"Parameters: {parameters}")

            # For builtin tools, execute directly
            if tool_def.execution.type == ExecutionType.BUILTIN:
                if not self.enable_builtin_tools:
                    return [], "Built-in tools are disabled"

                result = await self.tool_executor.execute(tool_def, parameters)

            elif tool_def.execution.type == ExecutionType.HTTP_CALL:
                # HTTP tools are executed through the tool executor
                result = await self.tool_executor.execute(tool_def, parameters)

            else:
                return [], f"Unknown execution type: {tool_def.execution.type}"

            # Handle execution result
            if result.status == ToolResultStatus.ERROR:
                return [], result.error

            # Return the result data
            return result.data, None

        except Exception as e:
            logger.error(f"Error executing function template {template_id}: {e}")
            logger.error(traceback.format_exc())
            return [], str(e)

    async def _execute_http_query_template(
        self,
        template: Dict[str, Any],
        parameters: Dict[str, Any]
    ) -> Tuple[Any, Optional[str]]:
        """
        Execute an HTTP query template (non-function type).

        This handles standard query templates that use HTTP requests
        without the function-calling abstraction.

        Args:
            template: Template dictionary with HTTP configuration
            parameters: Extracted parameters

        Returns:
            Tuple of (results, error_message)
        """
        try:
            # Get HTTP method (default to GET)
            http_method = template.get('http_method', 'GET').upper()

            # Process endpoint template with path parameters
            endpoint = self._process_endpoint_template(
                template.get('endpoint_template', template.get('endpoint', '/')),
                parameters
            )

            # Build query parameters
            query_params = self._build_query_params(template, parameters)

            # Build request headers
            headers = self._build_request_headers(template, parameters)

            # Build request body (for POST, PUT, PATCH)
            request_body = None
            if http_method in ['POST', 'PUT', 'PATCH']:
                request_body = self._build_request_body(template, parameters)

            template_id = template.get('id', 'unknown')
            if self.verbose:
                logger.debug(f"[Template {template_id}] Executing HTTP {http_method} to: {endpoint}")

            # Execute the HTTP request
            response = await self._execute_rest_request(
                method=http_method,
                endpoint=endpoint,
                params=query_params,
                headers=headers,
                json_data=request_body,
                timeout=template.get('timeout', self.timeout)
            )

            # Parse and extract results
            results = self._parse_response(response, template)

            return results, None

        except Exception as e:
            template_id = template.get('id', 'unknown')
            error_msg = str(e)
            logger.error(f"[Template {template_id}] Error executing HTTP template: {error_msg}")
            return [], error_msg

    async def _execute_http_tool(
        self,
        template: Dict[str, Any],
        parameters: Dict[str, Any]
    ) -> Tuple[Any, Optional[str]]:
        """
        Callback for ToolExecutor to execute HTTP-based tools.

        This method is passed to ToolExecutor as the http_executor callback.

        Args:
            template: HTTP template configuration
            parameters: Parameters for the request

        Returns:
            Tuple of (results, error_message)
        """
        return await self._execute_http_query_template(template, parameters)

    async def _execute_rest_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None
    ) -> Any:
        """
        Execute a REST API request.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint
            params: Query parameters
            headers: Request headers
            json_data: JSON body for POST/PUT/PATCH
            timeout: Request timeout

        Returns:
            Parsed JSON response
        """
        import httpx

        try:
            request_kwargs = {
                'method': method,
                'url': endpoint,
                'params': params,
                'headers': headers,
                'timeout': timeout or self.timeout,
            }

            if json_data:
                request_kwargs['json'] = json_data

            response = await self.http_client.request(**request_kwargs)
            response.raise_for_status()

            return response.json()

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP {e.response.status_code}: {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"HTTP request failed: {e}")
            raise

    def _process_endpoint_template(
        self,
        endpoint_template: str,
        parameters: Dict[str, Any]
    ) -> str:
        """
        Process endpoint template with path parameter substitution.

        Args:
            endpoint_template: Endpoint template like "/users/{user_id}/posts"
            parameters: Parameters for substitution

        Returns:
            Processed endpoint string
        """
        endpoint = endpoint_template

        # Use template processor if available (for Jinja2 syntax)
        if self.template_processor and '{{' in endpoint_template:
            endpoint = self.template_processor.render_sql(
                endpoint_template,
                parameters=parameters,
                preserve_unknown=False
            )
        else:
            # Simple string substitution for {param} syntax
            for key, value in parameters.items():
                endpoint = endpoint.replace(f"{{{{{key}}}}}", str(value))
                endpoint = endpoint.replace(f"{{{key}}}", str(value))

        return endpoint

    def _build_query_params(
        self,
        template: Dict[str, Any],
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build query parameters from template and extracted parameters."""
        query_params = {}

        # Get query params template
        template_params = template.get('query_params', {})

        for key, value_template in template_params.items():
            if isinstance(value_template, str) and '{{' in value_template:
                # Jinja2 template
                if self.template_processor:
                    rendered = self.template_processor.render_sql(
                        value_template,
                        parameters=parameters,
                        preserve_unknown=False
                    )
                    if rendered and rendered != value_template:
                        query_params[key] = rendered
            else:
                # Direct value
                query_params[key] = value_template

        # Add parameters that should go in query string
        for param in template.get('parameters', []):
            param_name = param.get('name')
            location = param.get('location', 'query')
            if location == 'query' and param_name in parameters:
                query_params[param_name] = parameters[param_name]

        return query_params

    def _build_request_headers(
        self,
        template: Dict[str, Any],
        parameters: Dict[str, Any]
    ) -> Dict[str, str]:
        """Build request headers from template."""
        headers = {}

        # Get headers from template
        template_headers = template.get('headers', {})
        headers.update(template_headers)

        # Add auth headers
        auth_headers = self._build_auth_headers(template)
        headers.update(auth_headers)

        return headers

    def _build_request_body(
        self,
        template: Dict[str, Any],
        parameters: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Build request body from template and parameters."""
        body_template = template.get('body_template', template.get('request_body'))

        if not body_template:
            return None

        if isinstance(body_template, str):
            # Jinja2 template string
            if self.template_processor:
                rendered = self.template_processor.render_sql(
                    body_template,
                    parameters=parameters,
                    preserve_unknown=False
                )
                try:
                    return json.loads(rendered)
                except json.JSONDecodeError:
                    return {"data": rendered}
            return {"data": body_template}

        elif isinstance(body_template, dict):
            # Template dict with placeholders
            body = {}
            for key, value in body_template.items():
                if isinstance(value, str) and '{{' in value:
                    if self.template_processor:
                        body[key] = self.template_processor.render_sql(
                            value,
                            parameters=parameters,
                            preserve_unknown=False
                        )
                    else:
                        body[key] = value
                else:
                    body[key] = value
            return body

        return None

    def _parse_response(
        self,
        response: Any,
        template: Dict[str, Any]
    ) -> Any:
        """
        Parse HTTP response according to template configuration.

        Args:
            response: Raw JSON response
            template: Template with response_mapping configuration

        Returns:
            Extracted/transformed response data
        """
        if response is None:
            return []

        response_mapping = template.get('response_mapping', {})
        items_path = response_mapping.get('items_path', '$')

        # Extract items using JSONPath-like syntax
        if items_path == '$':
            items = response
        elif items_path.startswith('$.'):
            path_parts = items_path[2:].split('.')
            items = response
            for part in path_parts:
                if isinstance(items, dict):
                    items = items.get(part, [])
                elif isinstance(items, list) and part.isdigit():
                    items = items[int(part)]
                else:
                    break
        else:
            items = response

        # Ensure we return a list for consistency
        if not isinstance(items, list):
            items = [items] if items else []

        return items

    async def close(self) -> None:
        """Close the retriever and clean up resources."""
        # Close function client if it's separate from inference client
        if self.function_client and self.function_client != self.inference_client:
            try:
                if hasattr(self.function_client, 'close'):
                    await self.function_client.close()
            except Exception as e:
                logger.warning(f"Error closing function client: {e}")

        # Close parent resources
        await super().close()


# Register the retriever with the factory
try:
    RetrieverFactory.register_retriever("intent_agent", IntentAgentRetriever)
    logger.debug("Registered IntentAgentRetriever with factory")
except Exception as e:
    logger.debug(f"Could not register IntentAgentRetriever: {e}")
