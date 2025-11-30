"""
API Executor Service - Execute API calls based on scenarios
"""
import json
import re
from typing import Any
from urllib.parse import urljoin, urlencode

import httpx

from models import (
    APIMapping,
    APISpec,
    ExtractedEntity,
    HTTPMethod,
    ParameterLocation,
    Scenario,
)


class APIExecutionError(Exception):
    """Custom exception for API execution errors"""
    pass


class APIExecutor:
    """Execute API calls based on scenarios and extracted entities"""
    
    def __init__(
        self,
        api_spec: APISpec,
        auth_config: dict[str, Any] | None = None,
        timeout: float = 30.0
    ):
        self.api_spec = api_spec
        self.auth_config = auth_config or {}
        self.timeout = timeout
        self.base_url = api_spec.base_url.rstrip("/") if api_spec.base_url else ""
    
    async def execute_scenario(
        self,
        scenario: Scenario,
        extracted_entities: list[ExtractedEntity]
    ) -> list[dict[str, Any]]:
        """Execute all API calls for a scenario"""
        results = []
        
        # Build entity map
        entity_map = {e.name: e.value for e in extracted_entities}
        
        for api_mapping in scenario.api_mappings:
            try:
                result = await self._execute_api_call(api_mapping, entity_map)
                results.append({
                    "endpoint": f"{api_mapping.method.value} {api_mapping.endpoint_path}",
                    "success": True,
                    "data": result,
                    "error": None
                })
            except APIExecutionError as e:
                results.append({
                    "endpoint": f"{api_mapping.method.value} {api_mapping.endpoint_path}",
                    "success": False,
                    "data": None,
                    "error": str(e)
                })
            except Exception as e:
                results.append({
                    "endpoint": f"{api_mapping.method.value} {api_mapping.endpoint_path}",
                    "success": False,
                    "data": None,
                    "error": f"Unexpected error: {str(e)}"
                })
        
        return results
    
    async def _execute_api_call(
        self,
        api_mapping: APIMapping,
        entity_map: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute a single API call"""
        
        # Find endpoint definition
        endpoint = self._find_endpoint(api_mapping.endpoint_path, api_mapping.method)
        
        # Build URL with path parameters
        url = self._build_url(api_mapping.endpoint_path, api_mapping, entity_map)
        
        # Build query parameters
        query_params = self._build_query_params(endpoint, api_mapping, entity_map)
        
        # Build headers
        headers = self._build_headers(endpoint, api_mapping, entity_map)
        
        # Build request body
        body = self._build_body(endpoint, api_mapping, entity_map)
        
        # Execute request
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.request(
                    method=api_mapping.method.value,
                    url=url,
                    params=query_params if query_params else None,
                    headers=headers,
                    json=body if body else None
                )
                
                # Check for errors
                if response.status_code >= 400:
                    raise APIExecutionError(
                        f"API returned error {response.status_code}: {response.text}"
                    )
                
                # Parse response
                content_type = response.headers.get("content-type", "")
                if "application/json" in content_type:
                    return response.json()
                else:
                    return {"raw_response": response.text}
                    
            except httpx.TimeoutException:
                raise APIExecutionError(f"Request timeout after {self.timeout}s")
            except httpx.RequestError as e:
                raise APIExecutionError(f"Request failed: {str(e)}")
    
    def _find_endpoint(self, path: str, method: HTTPMethod):
        """Find endpoint definition in API spec"""
        for endpoint in self.api_spec.endpoints:
            if endpoint.path == path and endpoint.method == method:
                return endpoint
        return None
    
    def _build_url(
        self,
        path: str,
        api_mapping: APIMapping,
        entity_map: dict[str, Any]
    ) -> str:
        """Build URL with path parameters"""
        url_path = path
        
        # Replace path parameters
        for mapping in api_mapping.parameter_mappings:
            # Check if this is a path parameter
            placeholder = "{" + mapping.api_parameter + "}"
            if placeholder in url_path:
                value = entity_map.get(mapping.entity_name, "")
                if mapping.transform:
                    value = self._apply_transform(value, mapping.transform)
                url_path = url_path.replace(placeholder, str(value))
        
        # Also apply static params that might be path params
        for param, value in api_mapping.static_params.items():
            placeholder = "{" + param + "}"
            if placeholder in url_path:
                url_path = url_path.replace(placeholder, str(value))
        
        return urljoin(self.base_url + "/", url_path.lstrip("/"))
    
    def _build_query_params(
        self,
        endpoint,
        api_mapping: APIMapping,
        entity_map: dict[str, Any]
    ) -> dict[str, Any]:
        """Build query parameters"""
        params = {}
        
        if endpoint:
            # Get query parameters from endpoint definition
            query_param_names = {
                p.name for p in endpoint.parameters
                if p.location == ParameterLocation.QUERY
            }
            
            # Add mapped parameters
            for mapping in api_mapping.parameter_mappings:
                if mapping.api_parameter in query_param_names:
                    value = entity_map.get(mapping.entity_name)
                    if value is not None:
                        if mapping.transform:
                            value = self._apply_transform(value, mapping.transform)
                        params[mapping.api_parameter] = value
        
        # Add static query params
        for param, value in api_mapping.static_params.items():
            if "{" not in str(value):  # Not a path param
                # Check if it's a query param
                if endpoint:
                    for p in endpoint.parameters:
                        if p.name == param and p.location == ParameterLocation.QUERY:
                            params[param] = value
                            break
                else:
                    params[param] = value
        
        return params
    
    def _build_headers(
        self,
        endpoint,
        api_mapping: APIMapping,
        entity_map: dict[str, Any]
    ) -> dict[str, str]:
        """Build request headers"""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        # Add auth headers
        if self.auth_config:
            auth_type = self.auth_config.get("type", "")
            
            if auth_type == "bearer":
                token = self.auth_config.get("token", "")
                headers["Authorization"] = f"Bearer {token}"
            
            elif auth_type == "api_key":
                key_name = self.auth_config.get("key_name", "X-API-Key")
                key_value = self.auth_config.get("key_value", "")
                key_location = self.auth_config.get("key_location", "header")
                
                if key_location == "header":
                    headers[key_name] = key_value
            
            elif auth_type == "basic":
                import base64
                username = self.auth_config.get("username", "")
                password = self.auth_config.get("password", "")
                credentials = base64.b64encode(
                    f"{username}:{password}".encode()
                ).decode()
                headers["Authorization"] = f"Basic {credentials}"
        
        # Add header parameters from mapping
        if endpoint:
            header_param_names = {
                p.name for p in endpoint.parameters
                if p.location == ParameterLocation.HEADER
            }
            
            for mapping in api_mapping.parameter_mappings:
                if mapping.api_parameter in header_param_names:
                    value = entity_map.get(mapping.entity_name)
                    if value is not None:
                        headers[mapping.api_parameter] = str(value)
        
        return headers
    
    def _build_body(
        self,
        endpoint,
        api_mapping: APIMapping,
        entity_map: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Build request body"""
        if api_mapping.method in [HTTPMethod.GET, HTTPMethod.DELETE]:
            return None
        
        if not endpoint or not endpoint.request_body:
            return None
        
        body = {}
        
        # Get body parameter names from request body schema
        content = endpoint.request_body.get("content", {})
        json_content = content.get("application/json", {})
        schema = json_content.get("schema", {})
        properties = schema.get("properties", {})
        
        # Add mapped parameters
        for mapping in api_mapping.parameter_mappings:
            if mapping.api_parameter in properties:
                value = entity_map.get(mapping.entity_name)
                if value is not None:
                    if mapping.transform:
                        value = self._apply_transform(value, mapping.transform)
                    body[mapping.api_parameter] = value
        
        # Add static body params
        for param, value in api_mapping.static_params.items():
            if param in properties:
                body[param] = value
        
        return body if body else None
    
    def _apply_transform(self, value: Any, transform: str) -> Any:
        """Apply transformation to value"""
        if transform == "lowercase":
            return str(value).lower()
        elif transform == "uppercase":
            return str(value).upper()
        elif transform == "trim":
            return str(value).strip()
        elif transform == "int":
            return int(value)
        elif transform == "float":
            return float(value)
        elif transform == "bool":
            return str(value).lower() in ["true", "1", "yes"]
        elif transform.startswith("date_format:"):
            # Format: date_format:input_format:output_format
            parts = transform.split(":")
            if len(parts) >= 3:
                from datetime import datetime
                input_fmt = parts[1]
                output_fmt = parts[2]
                try:
                    dt = datetime.strptime(str(value), input_fmt)
                    return dt.strftime(output_fmt)
                except ValueError:
                    return value
        
        return value


class MockAPIExecutor(APIExecutor):
    """Mock API executor for testing"""
    
    def __init__(
        self,
        api_spec: APISpec,
        mock_responses: dict[str, Any] | None = None,
        **kwargs
    ):
        super().__init__(api_spec, **kwargs)
        self.mock_responses = mock_responses or {}
    
    async def _execute_api_call(
        self,
        api_mapping: APIMapping,
        entity_map: dict[str, Any]
    ) -> dict[str, Any]:
        """Return mock response instead of making real API call"""
        
        key = f"{api_mapping.method.value}:{api_mapping.endpoint_path}"
        
        if key in self.mock_responses:
            return self.mock_responses[key]
        
        # Generate mock response based on endpoint schema
        endpoint = self._find_endpoint(api_mapping.endpoint_path, api_mapping.method)
        
        if endpoint and endpoint.responses:
            for response in endpoint.responses:
                if 200 <= response.status_code < 300:
                    if response.example:
                        return response.example
                    elif response.schema:
                        return self._generate_mock_from_schema(response.schema)
        
        return {"message": "Mock response", "success": True}
    
    def _generate_mock_from_schema(self, schema: dict) -> dict[str, Any]:
        """Generate mock data from schema"""
        result = {}
        
        properties = schema.get("properties", {})
        for prop_name, prop_schema in properties.items():
            prop_type = prop_schema.get("type", "string")
            
            if prop_type == "string":
                result[prop_name] = prop_schema.get("example", f"mock_{prop_name}")
            elif prop_type == "integer":
                result[prop_name] = prop_schema.get("example", 123)
            elif prop_type == "number":
                result[prop_name] = prop_schema.get("example", 123.45)
            elif prop_type == "boolean":
                result[prop_name] = prop_schema.get("example", True)
            elif prop_type == "array":
                result[prop_name] = prop_schema.get("example", [])
            elif prop_type == "object":
                result[prop_name] = prop_schema.get("example", {})
        
        return result