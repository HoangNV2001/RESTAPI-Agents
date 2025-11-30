"""
OpenAPI Parser Service - Parse and normalize OpenAPI specifications
"""
import json
import re
from typing import Any

import yaml

from models import (
    APIEndpoint,
    APIParameter,
    APIResponse,
    APISpec,
    HTTPMethod,
    ParameterLocation,
    ParameterType,
)


class OpenAPIParserError(Exception):
    """Custom exception for parsing errors"""
    pass


class OpenAPIParser:
    """Parse OpenAPI 3.x specifications"""
    
    SUPPORTED_VERSIONS = ["3.0", "3.1"]
    
    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []
    
    def parse(self, content: str, format: str = "yaml") -> APISpec:
        """Parse OpenAPI spec from string content"""
        self.errors = []
        self.warnings = []
        
        try:
            if format.lower() == "yaml":
                spec_dict = yaml.safe_load(content)
            else:
                spec_dict = json.loads(content)
        except yaml.YAMLError as e:
            raise OpenAPIParserError(f"Invalid YAML format: {e}")
        except json.JSONDecodeError as e:
            raise OpenAPIParserError(f"Invalid JSON format: {e}")
        
        if not isinstance(spec_dict, dict):
            raise OpenAPIParserError("API spec must be a valid object/dictionary")
        
        self._validate_version(spec_dict)
        
        return self._parse_spec(spec_dict)
    
    def _validate_version(self, spec: dict) -> None:
        """Validate OpenAPI version"""
        openapi_version = spec.get("openapi", "")
        
        if not openapi_version:
            raise OpenAPIParserError("Missing 'openapi' version field")
        
        major_minor = ".".join(openapi_version.split(".")[:2])
        if major_minor not in self.SUPPORTED_VERSIONS:
            raise OpenAPIParserError(
                f"Unsupported OpenAPI version: {openapi_version}. "
                f"Supported versions: {', '.join(self.SUPPORTED_VERSIONS)}"
            )
    
    def _parse_spec(self, spec: dict) -> APISpec:
        """Parse the complete spec"""
        info = spec.get("info", {})
        
        # Parse servers
        servers = []
        for server in spec.get("servers", []):
            servers.append({
                "url": server.get("url", ""),
                "description": server.get("description", "")
            })
        
        # Determine base URL
        base_url = servers[0]["url"] if servers else ""
        
        # Parse security schemes
        security_schemes = {}
        components = spec.get("components", {})
        if "securitySchemes" in components:
            security_schemes = components["securitySchemes"]
        
        # Parse endpoints
        endpoints = self._parse_paths(spec.get("paths", {}), components)
        
        return APISpec(
            title=info.get("title", "Untitled API"),
            version=info.get("version", "1.0.0"),
            description=info.get("description", ""),
            base_url=base_url,
            endpoints=endpoints,
            servers=servers,
            security_schemes=security_schemes,
            original_spec=spec
        )
    
    def _parse_paths(self, paths: dict, components: dict) -> list[APIEndpoint]:
        """Parse all paths/endpoints"""
        endpoints = []
        
        for path, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue
            
            # Handle path-level parameters
            path_params = self._parse_parameters(
                path_item.get("parameters", []),
                components
            )
            
            for method in ["get", "post", "put", "patch", "delete"]:
                if method in path_item:
                    operation = path_item[method]
                    endpoint = self._parse_operation(
                        path, method.upper(), operation, path_params, components
                    )
                    endpoints.append(endpoint)
        
        return endpoints
    
    def _parse_operation(
        self,
        path: str,
        method: str,
        operation: dict,
        path_params: list[APIParameter],
        components: dict
    ) -> APIEndpoint:
        """Parse a single operation"""
        
        # Parse operation-level parameters
        op_params = self._parse_parameters(
            operation.get("parameters", []),
            components
        )
        
        # Merge path and operation parameters
        all_params = {p.name: p for p in path_params}
        for p in op_params:
            all_params[p.name] = p
        
        # Parse request body
        request_body = None
        if "requestBody" in operation:
            request_body = self._parse_request_body(
                operation["requestBody"],
                components
            )
        
        # Parse responses
        responses = self._parse_responses(
            operation.get("responses", {}),
            components
        )
        
        # Generate operation_id if missing
        operation_id = operation.get("operationId", "")
        if not operation_id:
            operation_id = self._generate_operation_id(path, method)
            self.warnings.append(
                f"Missing operationId for {method} {path}, generated: {operation_id}"
            )
        
        return APIEndpoint(
            path=path,
            method=HTTPMethod(method),
            operation_id=operation_id,
            summary=operation.get("summary", ""),
            description=operation.get("description", ""),
            tags=operation.get("tags", []),
            parameters=list(all_params.values()),
            request_body=request_body,
            responses=responses
        )
    
    def _parse_parameters(
        self,
        parameters: list,
        components: dict
    ) -> list[APIParameter]:
        """Parse parameters list"""
        result = []
        
        for param in parameters:
            # Resolve reference
            if "$ref" in param:
                param = self._resolve_ref(param["$ref"], components)
                if not param:
                    continue
            
            # Map location
            location_map = {
                "path": ParameterLocation.PATH,
                "query": ParameterLocation.QUERY,
                "header": ParameterLocation.HEADER,
            }
            location = location_map.get(
                param.get("in", "query"),
                ParameterLocation.QUERY
            )
            
            # Map type
            schema = param.get("schema", {})
            param_type = self._map_type(schema.get("type", "string"))
            
            result.append(APIParameter(
                name=param.get("name", ""),
                location=location,
                param_type=param_type,
                description=param.get("description", ""),
                required=param.get("required", False),
                default=schema.get("default"),
                example=param.get("example") or schema.get("example"),
                enum=schema.get("enum")
            ))
        
        return result
    
    def _parse_request_body(
        self,
        request_body: dict,
        components: dict
    ) -> dict[str, Any]:
        """Parse request body"""
        # Resolve reference
        if "$ref" in request_body:
            request_body = self._resolve_ref(request_body["$ref"], components)
            if not request_body:
                return {}
        
        content = request_body.get("content", {})
        result = {
            "required": request_body.get("required", False),
            "description": request_body.get("description", ""),
            "content": {}
        }
        
        for media_type, media_content in content.items():
            schema = media_content.get("schema", {})
            # Resolve schema reference
            if "$ref" in schema:
                schema = self._resolve_ref(schema["$ref"], components)
            
            result["content"][media_type] = {
                "schema": schema,
                "example": media_content.get("example")
            }
        
        return result
    
    def _parse_responses(
        self,
        responses: dict,
        components: dict
    ) -> list[APIResponse]:
        """Parse responses"""
        result = []
        
        for status_code, response in responses.items():
            # Resolve reference
            if "$ref" in response:
                response = self._resolve_ref(response["$ref"], components)
                if not response:
                    continue
            
            # Parse status code
            try:
                code = int(status_code)
            except ValueError:
                code = 200  # Default for non-numeric status codes
            
            # Extract schema from content
            content = response.get("content", {})
            schema = {}
            example = None
            
            if "application/json" in content:
                json_content = content["application/json"]
                schema = json_content.get("schema", {})
                if "$ref" in schema:
                    schema = self._resolve_ref(schema["$ref"], components) or {}
                example = json_content.get("example")
            
            result.append(APIResponse(
                status_code=code,
                description=response.get("description", ""),
                schema=schema,
                example=example
            ))
        
        return result
    
    def _resolve_ref(self, ref: str, components: dict) -> dict | None:
        """Resolve $ref reference"""
        if not ref.startswith("#/"):
            self.warnings.append(f"External reference not supported: {ref}")
            return None
        
        parts = ref.split("/")[1:]  # Remove leading '#'
        
        current = {"components": components}
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                self.warnings.append(f"Could not resolve reference: {ref}")
                return None
        
        return current if isinstance(current, dict) else None
    
    def _map_type(self, type_str: str) -> ParameterType:
        """Map OpenAPI type to ParameterType"""
        type_map = {
            "string": ParameterType.STRING,
            "integer": ParameterType.INTEGER,
            "number": ParameterType.NUMBER,
            "boolean": ParameterType.BOOLEAN,
            "array": ParameterType.ARRAY,
            "object": ParameterType.OBJECT,
        }
        return type_map.get(type_str, ParameterType.STRING)
    
    def _generate_operation_id(self, path: str, method: str) -> str:
        """Generate operation ID from path and method"""
        # Remove path parameters
        clean_path = re.sub(r'\{[^}]+\}', '', path)
        # Convert to snake_case
        clean_path = clean_path.replace('/', '_').strip('_')
        clean_path = re.sub(r'_+', '_', clean_path)
        
        return f"{method.lower()}_{clean_path}" if clean_path else method.lower()
    
    def get_errors(self) -> list[str]:
        """Get parsing errors"""
        return self.errors
    
    def get_warnings(self) -> list[str]:
        """Get parsing warnings"""
        return self.warnings