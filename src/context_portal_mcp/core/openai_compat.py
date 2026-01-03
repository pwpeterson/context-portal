"""OpenAI-compatible schema patching for FastMCP."""

import logging
from typing import Any, Dict

log = logging.getLogger(__name__)


def patch_schema_for_openai(schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively patch a JSON schema to add additionalProperties: false to all object types.
    
    This is required for OpenAI's gpt-5.2 and newer models which enforce strict schema validation.
    
    Args:
        schema: The JSON schema dictionary to patch
        
    Returns:
        The patched schema (modifies in place and returns for convenience)
    """
    if not isinstance(schema, dict):
        return schema
    
    # If this is an object type, force additionalProperties to false
    if schema.get('type') == 'object':
        schema['additionalProperties'] = False
    
    # Recursively patch anyOf, oneOf, allOf
    for key in ['anyOf', 'oneOf', 'allOf']:
        if key in schema and isinstance(schema[key], list):
            for item in schema[key]:
                patch_schema_for_openai(item)
    
    # Recursively patch properties
    if 'properties' in schema and isinstance(schema['properties'], dict):
        for prop_value in schema['properties'].values():
            patch_schema_for_openai(prop_value)
    
    # Recursively patch items (for arrays)
    if 'items' in schema:
        patch_schema_for_openai(schema['items'])
    
    # Recursively patch additionalProperties if it's a schema
    if 'additionalProperties' in schema and isinstance(schema['additionalProperties'], dict):
        patch_schema_for_openai(schema['additionalProperties'])
    
    return schema


def patch_mcp_server_for_openai(server):
    """
    Patch an MCP server instance to generate OpenAI-compatible tool schemas.
    
    This wraps the server's list_tools method to automatically patch all tool schemas.
    
    Args:
        server: The FastMCP server instance to patch
    """
    try:
        # Store the original list_tools method
        if hasattr(server, 'list_tools'):
            original_list_tools = server.list_tools
            
            async def patched_list_tools(*args, **kwargs):
                """Patched list_tools that fixes schemas for OpenAI."""
                # Call the original method
                result = await original_list_tools(*args, **kwargs)
                
                # Patch all tool schemas
                if hasattr(result, 'tools'):
                    for tool in result.tools:
                        if hasattr(tool, 'inputSchema') and tool.inputSchema:
                            patch_schema_for_openai(tool.inputSchema)
                            log.debug(f"Patched schema for tool: {tool.name}")
                
                return result
            
            # Replace the method
            server.list_tools = patched_list_tools
            log.info("Successfully patched MCP server for OpenAI compatibility")
            return True
            
    except Exception as e:
        log.error(f"Failed to patch MCP server for OpenAI compatibility: {e}")
        return False
    
    return False
