# ConPort MCP Server Schema Fix for OpenAI Compatibility

## Problem

OpenAI's API (gpt-5.2 and newer models) has stricter JSON Schema validation that requires all object schemas to explicitly set `"additionalProperties": false`. The current ConPort MCP server's `update_product_context` and `update_active_context` tools fail with this error:

```
Invalid schema for function 'mcp--conport--update_product_context': 
In context=('properties', 'content', 'anyOf', '0'), 
'additionalProperties' is required to be supplied and to be false.
```

## Root Cause

The `UpdateContextArgs` Pydantic model in `/tmp/context_portal_mcp/db/models.py` (lines 110-125) uses `Optional[Dict[str, Any]]` for both `content` and `patch_content` fields. When Pydantic generates the JSON schema, it creates an `anyOf` with object schemas that don't include `"additionalProperties": false`.

## Solution

Add a `model_json_schema()` class method to `UpdateContextArgs` that post-processes the generated schema to add `"additionalProperties": false` to all object schemas.

### Code Fix

Replace the `UpdateContextArgs` class (lines 110-125) with:

```python
class UpdateContextArgs(BaseArgs):
    """Arguments for updating product or active context.
    Provide either 'content' for a full update or 'patch_content' for a partial update.
    """
    content: Optional[Dict[str, Any]] = Field(None, description="The full new context content as a dictionary. Overwrites existing.")
    patch_content: Optional[Dict[str, Any]] = Field(None, description="A dictionary of changes to apply to the existing context (add/update keys).")

    @model_validator(mode='before')
    @classmethod
    def check_content_or_patch(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        content, patch_content = values.get('content'), values.get('patch_content')
        if content is None and patch_content is None:
            raise ValueError("Either 'content' or 'patch_content' must be provided.")
        if content is not None and patch_content is not None:
            raise ValueError("Provide either 'content' for a full update or 'patch_content' for a partial update, not both.")
        return values

    @classmethod
    def model_json_schema(cls, **kwargs) -> Dict[str, Any]:
        """Override to add additionalProperties: false for OpenAI compatibility."""
        schema = super().model_json_schema(**kwargs)
        
        # Add additionalProperties: false to all object schemas in anyOf
        for field_name in ['content', 'patch_content']:
            if 'properties' in schema and field_name in schema['properties']:
                field_schema = schema['properties'][field_name]
                if 'anyOf' in field_schema:
                    for option in field_schema['anyOf']:
                        if isinstance(option, dict) and option.get('type') == 'object':
                            option['additionalProperties'] = False
        
        return schema
```

## Alternative Solution (More Robust)

For a more comprehensive fix that handles all Dict[str, Any] fields across all models, add a base class method:

```python
class BaseArgs(BaseModel):
    """Base model for arguments requiring a workspace ID."""
    workspace_id: Annotated[str, Field(description="Identifier for the workspace (e.g., absolute path)")]
    
    @classmethod
    def model_json_schema(cls, **kwargs) -> Dict[str, Any]:
        """Override to add additionalProperties: false to all object schemas for OpenAI compatibility."""
        schema = super().model_json_schema(**kwargs)
        
        def add_additional_properties_false(obj):
            """Recursively add additionalProperties: false to all object schemas."""
            if isinstance(obj, dict):
                if obj.get('type') == 'object' and 'additionalProperties' not in obj:
                    obj['additionalProperties'] = False
                
                # Handle anyOf, oneOf, allOf
                for key in ['anyOf', 'oneOf', 'allOf']:
                    if key in obj:
                        for item in obj[key]:
                            add_additional_properties_false(item)
                
                # Handle properties
                if 'properties' in obj:
                    for prop_value in obj['properties'].values():
                        add_additional_properties_false(prop_value)
                
                # Handle items (for arrays)
                if 'items' in obj:
                    add_additional_properties_false(obj['items'])
        
        add_additional_properties_false(schema)
        return schema
```

## Testing

After applying the fix, test with:

```python
from context_portal_mcp.db.models import UpdateContextArgs
import json

# Generate schema
schema = UpdateContextArgs.model_json_schema()

# Check that additionalProperties is set
content_schema = schema['properties']['content']
print(json.dumps(content_schema, indent=2))

# Verify anyOf options have additionalProperties: false
for option in content_schema.get('anyOf', []):
    if option.get('type') == 'object':
        assert option.get('additionalProperties') == False, "Missing additionalProperties: false"

print("✓ Schema validation passed!")
```

## Files to Modify

1. **Primary file**: `context_portal_mcp/db/models.py`
   - Modify `UpdateContextArgs` class (lines 110-125)
   - OR modify `BaseArgs` class (lines 77-79) for comprehensive fix

2. **Test the fix**: Restart the MCP server and test with OpenAI's gpt-5.2 model

## Package Update Required

After fixing the code, the maintainer needs to:

1. Update version in `pyproject.toml` or `setup.py`
2. Build new package: `python -m build`
3. Publish to PyPI: `python -m twine upload dist/*`
4. Users update with: `uvx --from context-portal-mcp@latest conport-mcp ...`

## Workaround (Temporary)

Until the package is updated, users can:

1. Clone the repository locally
2. Apply the fix manually
3. Install from local source: `pip install -e /path/to/context-portal-mcp`
4. Update MCP configuration to use local installation instead of `uvx`

## References

- OpenAI Function Calling Schema Requirements: https://platform.openai.com/docs/guides/function-calling
- Pydantic JSON Schema: https://docs.pydantic.dev/latest/concepts/json_schema/
- MCP Protocol: https://modelcontextprotocol.io/
