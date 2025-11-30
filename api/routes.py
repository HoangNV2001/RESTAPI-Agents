"""
FastAPI Routes for API Agent
"""
import os
from typing import Any

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from core import APIAgentApp
from models import (
    AnalysisResult,
    ChatWithAgentRequest,
    CreateScenarioRequest,
    FinalizeAgentRequest,
    RefineAPIRequest,
    Scenario,
    Session,
    UploadAPIRequest,
)

# Initialize FastAPI app
app = FastAPI(
    title="API Agent",
    description="AI-powered API documentation and Q&A agent builder",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize application
api_agent_app: APIAgentApp | None = None


def get_app() -> APIAgentApp:
    """Get or create application instance"""
    global api_agent_app
    if api_agent_app is None:
        api_key = os.getenv("OPENAI_API_KEY")
        api_agent_app = APIAgentApp(openai_api_key=api_key)
    return api_agent_app


# =============================================================================
# Session Endpoints
# =============================================================================

@app.post("/sessions", response_model=dict)
async def create_session():
    """Create a new session"""
    app_instance = get_app()
    session = await app_instance.create_session()
    return {"session_id": session.id, "status": session.status.value}


@app.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """Get session details"""
    app_instance = get_app()
    session = await app_instance.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {
        "id": session.id,
        "status": session.status.value,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
        "has_api_spec": session.api_spec is not None,
        "scenario_count": len(session.scenarios),
        "api_title": session.api_spec.title if session.api_spec else None
    }


@app.get("/sessions")
async def list_sessions():
    """List all sessions"""
    app_instance = get_app()
    sessions = await app_instance.list_sessions()
    return [
        {
            "id": s.id,
            "status": s.status.value,
            "updated_at": s.updated_at.isoformat(),
            "api_title": s.api_spec.title if s.api_spec else None
        }
        for s in sessions
    ]


# =============================================================================
# API Setup Endpoints
# =============================================================================

@app.post("/sessions/{session_id}/api-spec")
async def upload_api_spec(
    session_id: str,
    content: str = Form(...),
    format: str = Form("yaml")
):
    """Upload and analyze API specification"""
    app_instance = get_app()
    
    try:
        result = await app_instance.upload_api_spec(session_id, content, format)
        return {
            "success": True,
            "api_title": result.api_spec.title,
            "endpoint_count": len(result.api_spec.endpoints),
            "issues": result.issues,
            "suggestions": result.suggestions,
            "missing_descriptions": result.missing_descriptions
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/sessions/{session_id}/api-spec/file")
async def upload_api_spec_file(
    session_id: str,
    file: UploadFile = File(...)
):
    """Upload API spec from file"""
    app_instance = get_app()
    
    content = await file.read()
    content_str = content.decode("utf-8")
    
    # Detect format from filename
    format = "yaml"
    if file.filename and file.filename.endswith(".json"):
        format = "json"
    
    try:
        result = await app_instance.upload_api_spec(session_id, content_str, format)
        return {
            "success": True,
            "api_title": result.api_spec.title,
            "endpoint_count": len(result.api_spec.endpoints),
            "issues": result.issues,
            "suggestions": result.suggestions,
            "missing_descriptions": result.missing_descriptions
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/sessions/{session_id}/api-spec")
async def get_api_spec(session_id: str):
    """Get the parsed API specification"""
    app_instance = get_app()
    session = await app_instance.get_session(session_id)
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if not session.api_spec:
        raise HTTPException(status_code=404, detail="No API spec uploaded")
    
    spec = session.api_spec
    return {
        "title": spec.title,
        "version": spec.version,
        "description": spec.description,
        "base_url": spec.base_url,
        "endpoints": [
            {
                "path": e.path,
                "method": e.method.value,
                "operation_id": e.operation_id,
                "summary": e.summary,
                "description": e.description,
                "tags": e.tags,
                "parameters": [
                    {
                        "name": p.name,
                        "location": p.location.value,
                        "type": p.param_type.value,
                        "description": p.description,
                        "required": p.required
                    }
                    for p in e.parameters
                ],
                "suggested_description": e.suggested_description
            }
            for e in spec.endpoints
        ]
    }


class RefineRequest(BaseModel):
    message: str


@app.post("/sessions/{session_id}/api-spec/refine")
async def refine_api_spec(session_id: str, request: RefineRequest):
    """Refine API spec through chat"""
    app_instance = get_app()
    
    try:
        updated_spec, response = await app_instance.refine_api(
            session_id, request.message
        )
        return {
            "success": True,
            "response": response,
            "endpoint_count": len(updated_spec.endpoints)
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# =============================================================================
# Scenario Endpoints
# =============================================================================

@app.post("/sessions/{session_id}/scenarios/suggest")
async def suggest_scenarios(session_id: str):
    """Get AI-suggested scenarios"""
    app_instance = get_app()
    
    try:
        suggestions = await app_instance.suggest_scenarios(session_id)
        return {"scenarios": suggestions}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class ScenarioRequest(BaseModel):
    name: str
    description: str = ""
    sample_questions: list[str] = []
    required_entities: list[str] = []
    api_mappings: list[dict[str, Any]] = []
    api_mapping: dict[str, Any] | None = None
    response_template: str | dict[str, str] | None = None


@app.post("/sessions/{session_id}/scenarios")
async def create_scenario(session_id: str, request: ScenarioRequest):
    """Create a new scenario"""
    app_instance = get_app()
    
    try:
        scenario = await app_instance.create_scenario(
            session_id, request.model_dump()
        )
        return {
            "success": True,
            "scenario_id": scenario.id,
            "name": scenario.name
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/sessions/{session_id}/scenarios")
async def get_scenarios(session_id: str):
    """Get all scenarios for a session"""
    app_instance = get_app()
    
    try:
        scenarios = await app_instance.get_scenarios(session_id)
        return {
            "scenarios": [
                {
                    "id": s.id,
                    "name": s.name,
                    "description": s.description,
                    "sample_questions": s.sample_questions,
                    "required_entities": s.required_entities,
                    "api_mappings": [
                        {
                            "endpoint_path": m.endpoint_path,
                            "method": m.method.value,
                            "parameter_mappings": [
                                {
                                    "entity_name": pm.entity_name,
                                    "api_parameter": pm.api_parameter,
                                    "transform": pm.transform
                                }
                                for pm in m.parameter_mappings
                            ]
                        }
                        for m in s.api_mappings
                    ],
                    "response_template": s.response_template.template if s.response_template else None
                }
                for s in scenarios
            ]
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/sessions/{session_id}/scenarios/{scenario_id}")
async def update_scenario(
    session_id: str,
    scenario_id: str,
    request: ScenarioRequest
):
    """Update a scenario"""
    app_instance = get_app()
    
    try:
        scenario = await app_instance.update_scenario(
            session_id, scenario_id, request.model_dump()
        )
        return {"success": True, "scenario_id": scenario.id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/sessions/{session_id}/scenarios/{scenario_id}")
async def delete_scenario(session_id: str, scenario_id: str):
    """Delete a scenario"""
    app_instance = get_app()
    
    try:
        result = await app_instance.delete_scenario(session_id, scenario_id)
        if not result:
            raise HTTPException(status_code=404, detail="Scenario not found")
        return {"success": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# =============================================================================
# Agent Endpoints
# =============================================================================

class FinalizeRequest(BaseModel):
    name: str = "API Agent"
    auth_config: dict[str, Any] = {}
    use_mock_api: bool = False


@app.post("/sessions/{session_id}/finalize")
async def finalize_agent(session_id: str, request: FinalizeRequest):
    """Finalize session and create Q&A agent"""
    app_instance = get_app()
    
    try:
        agent_id = await app_instance.finalize_agent(
            session_id,
            name=request.name,
            auth_config=request.auth_config,
            use_mock_api=request.use_mock_api
        )
        return {"success": True, "agent_id": agent_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/agents")
async def list_agents():
    """List all agents"""
    app_instance = get_app()
    agents = await app_instance.list_agents()
    return {"agents": agents}


@app.get("/agents/{agent_id}")
async def get_agent(agent_id: str):
    """Get agent details"""
    app_instance = get_app()
    
    agent = await app_instance.load_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    capabilities = await agent.list_capabilities()
    return {
        "agent_id": agent_id,
        "name": agent.config.name,
        "description": agent.config.description,
        "capabilities": capabilities
    }


class ChatRequest(BaseModel):
    question: str


@app.post("/agents/{agent_id}/chat")
async def chat_with_agent(agent_id: str, request: ChatRequest):
    """Chat with an agent"""
    app_instance = get_app()
    
    try:
        response = await app_instance.chat_with_agent(agent_id, request.question)
        return {
            "answer": response.answer,
            "scenario_used": response.scenario_used,
            "api_calls": response.api_calls_made
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# =============================================================================
# Utility Endpoints
# =============================================================================

class TemplateValidateRequest(BaseModel):
    template: str


@app.post("/utils/validate-template")
async def validate_template(request: TemplateValidateRequest):
    """Validate a response template"""
    app_instance = get_app()
    
    is_valid, error = app_instance.validate_template(request.template)
    variables = app_instance.get_template_variables(request.template)
    
    return {
        "valid": is_valid,
        "error": error,
        "variables": variables
    }


class TemplatePreviewRequest(BaseModel):
    template: str
    data: dict[str, Any]


@app.post("/utils/preview-template")
async def preview_template(request: TemplatePreviewRequest):
    """Preview template with sample data"""
    app_instance = get_app()
    
    result = app_instance.preview_template(request.template, request.data)
    return {"result": result}


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "version": "1.0.0"}


# Run with: uvicorn api.routes:app --reload
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)