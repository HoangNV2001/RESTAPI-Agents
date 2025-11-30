"""
Pydantic models for API Agent
"""
from datetime import datetime
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class HTTPMethod(str, Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"


class ParameterLocation(str, Enum):
    PATH = "path"
    QUERY = "query"
    HEADER = "header"
    BODY = "body"


class ParameterType(str, Enum):
    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"


# =============================================================================
# API Spec Models
# =============================================================================

class APIParameter(BaseModel):
    """Represents an API parameter"""
    name: str
    location: ParameterLocation
    param_type: ParameterType = Field(default=ParameterType.STRING)
    description: str = ""
    required: bool = False
    default: Any = None
    example: Any = None
    enum: list[str] | None = None


class APIResponse(BaseModel):
    """Represents an API response schema"""
    status_code: int
    description: str = ""
    schema: dict[str, Any] = Field(default_factory=dict)
    example: dict[str, Any] | None = None


class APIEndpoint(BaseModel):
    """Represents a single API endpoint"""
    path: str
    method: HTTPMethod
    operation_id: str = ""
    summary: str = ""
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    parameters: list[APIParameter] = Field(default_factory=list)
    request_body: dict[str, Any] | None = None
    responses: list[APIResponse] = Field(default_factory=list)
    
    # AI-generated suggestions
    suggested_description: str | None = None
    suggested_parameters: list[APIParameter] | None = None


class APISpec(BaseModel):
    """Represents a complete API specification"""
    title: str
    version: str = "1.0.0"
    description: str = ""
    base_url: str = ""
    endpoints: list[APIEndpoint] = Field(default_factory=list)
    servers: list[dict[str, str]] = Field(default_factory=list)
    security_schemes: dict[str, Any] = Field(default_factory=dict)
    
    # Original spec for reference
    original_spec: dict[str, Any] | None = None


# =============================================================================
# Scenario Models
# =============================================================================

class ParameterMapping(BaseModel):
    """Maps extracted entities to API parameters"""
    entity_name: str  # Name extracted from user question
    api_parameter: str  # Corresponding API parameter name
    transform: str | None = None  # Optional transformation (e.g., "lowercase", "date_format")


class APIMapping(BaseModel):
    """Maps a scenario to API endpoint(s)"""
    endpoint_path: str
    method: HTTPMethod
    parameter_mappings: list[ParameterMapping] = Field(default_factory=list)
    static_params: dict[str, Any] = Field(default_factory=dict)  # Fixed parameters


class ResponseTemplate(BaseModel):
    """Template for rendering API response"""
    template: str  # Jinja2 template
    error_template: str = "Xin lỗi, không thể lấy thông tin. Lỗi: {{ error }}"
    no_data_template: str = "Không tìm thấy dữ liệu phù hợp."


class Scenario(BaseModel):
    """Represents a Q&A scenario"""
    id: str = ""
    name: str
    description: str = ""
    sample_questions: list[str] = Field(default_factory=list)
    required_entities: list[str] = Field(default_factory=list)  # Entities to extract
    api_mappings: list[APIMapping] = Field(default_factory=list)
    response_template: ResponseTemplate | None = None
    
    # AI-generated suggestions
    suggested_questions: list[str] | None = None
    suggested_entities: list[str] | None = None


# =============================================================================
# Session Models
# =============================================================================

class SessionStatus(str, Enum):
    CREATED = "created"
    API_UPLOADED = "api_uploaded"
    API_REFINED = "api_refined"
    SCENARIOS_DEFINED = "scenarios_defined"
    AGENT_CREATED = "agent_created"


class Session(BaseModel):
    """Represents a user session"""
    id: str
    status: SessionStatus = SessionStatus.CREATED
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    
    # API spec
    api_spec: APISpec | None = None
    original_spec_content: str = ""  # Original uploaded content
    
    # Scenarios
    scenarios: list[Scenario] = Field(default_factory=list)
    
    # Agent config
    agent_config: dict[str, Any] = Field(default_factory=dict)
    
    # Chat history for refinement
    chat_history: list[dict[str, str]] = Field(default_factory=list)


# =============================================================================
# Agent Models
# =============================================================================

class AgentConfig(BaseModel):
    """Configuration for Q&A Agent"""
    session_id: str
    name: str = "API Agent"
    description: str = ""
    api_spec: APISpec
    scenarios: list[Scenario]
    auth_config: dict[str, Any] = Field(default_factory=dict)


class ExtractedEntity(BaseModel):
    """Entity extracted from user question"""
    name: str
    value: Any
    confidence: float = 1.0


class ScenarioMatch(BaseModel):
    """Result of scenario matching"""
    scenario: Scenario
    confidence: float
    extracted_entities: list[ExtractedEntity]


class AgentResponse(BaseModel):
    """Response from Q&A Agent"""
    answer: str
    scenario_used: str | None = None
    api_calls_made: list[dict[str, Any]] = Field(default_factory=list)
    raw_api_responses: list[dict[str, Any]] = Field(default_factory=list)


# =============================================================================
# API Request/Response Models
# =============================================================================

class UploadAPIRequest(BaseModel):
    """Request to upload API spec"""
    content: str  # YAML or JSON content
    format: str = "yaml"  # "yaml" or "json"


class RefineAPIRequest(BaseModel):
    """Request to refine API spec"""
    session_id: str
    message: str  # User's refinement instruction


class CreateScenarioRequest(BaseModel):
    """Request to create a scenario"""
    session_id: str
    scenario: Scenario


class UpdateScenarioRequest(BaseModel):
    """Request to update a scenario"""
    session_id: str
    scenario_id: str
    scenario: Scenario


class SuggestScenariosRequest(BaseModel):
    """Request AI to suggest scenarios"""
    session_id: str


class FinalizeAgentRequest(BaseModel):
    """Request to finalize and create agent"""
    session_id: str
    name: str = "API Agent"
    auth_config: dict[str, Any] = Field(default_factory=dict)


class ChatWithAgentRequest(BaseModel):
    """Request to chat with agent"""
    agent_id: str
    question: str


class AnalysisResult(BaseModel):
    """Result of API analysis"""
    api_spec: APISpec
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    missing_descriptions: list[dict[str, str]] = Field(default_factory=list)