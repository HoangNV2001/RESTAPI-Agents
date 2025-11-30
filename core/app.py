"""
Core Application - Main orchestration logic for API Agent
"""
from typing import Any
from uuid import uuid4

from models import (
    AgentConfig,
    AgentResponse,
    AnalysisResult,
    APIMapping,
    APISpec,
    HTTPMethod,
    ParameterMapping,
    ResponseTemplate,
    Scenario,
    Session,
    SessionStatus,
)
from services import (
    AIService,
    OpenAPIParser,
    OpenAPIParserError,
    SessionManager,
    TemplateRenderer,
)
from agents import QAAgent, AgentManager


class APIAgentApp:
    """Main application class that orchestrates all components"""
    
    def __init__(
        self,
        openai_api_key: str | None = None,
        db_path: str = "api_agent.db"
    ):
        self.session_manager = SessionManager(db_path)
        self.parser = OpenAPIParser()
        self.template_renderer = TemplateRenderer()
        
        # AI service (may be None if no API key)
        self.ai_service: AIService | None = None
        if openai_api_key:
            self.ai_service = AIService(openai_api_key)
        
        # Agent manager
        self.agent_manager: AgentManager | None = None
        if self.ai_service:
            self.agent_manager = AgentManager(self.ai_service)
    
    def set_api_key(self, api_key: str) -> None:
        """Set or update Openai API key"""
        self.ai_service = AIService(api_key)
        self.agent_manager = AgentManager(self.ai_service)
    
    # =========================================================================
    # Session Management
    # =========================================================================
    
    async def create_session(self) -> Session:
        """Create a new session"""
        return await self.session_manager.create_session()
    
    async def get_session(self, session_id: str) -> Session | None:
        """Get session by ID"""
        return await self.session_manager.get_session(session_id)
    
    async def list_sessions(self) -> list[Session]:
        """List all sessions"""
        return await self.session_manager.list_sessions()
    
    # =========================================================================
    # API Setup
    # =========================================================================
    
    async def upload_api_spec(
        self,
        session_id: str,
        content: str,
        format: str = "yaml"
    ) -> AnalysisResult:
        """
        Upload and parse API specification.
        Returns analysis with issues and suggestions.
        """
        session = await self.session_manager.get_session(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")
        
        # Parse the spec
        try:
            api_spec = self.parser.parse(content, format)
        except OpenAPIParserError as e:
            raise ValueError(f"Failed to parse API spec: {e}")
        
        # Get parser warnings
        issues = self.parser.get_warnings()
        
        # Analyze with AI if available
        suggestions = []
        missing_descriptions = []
        
        if self.ai_service:
            analysis = await self.ai_service.analyze_api_spec(api_spec)
            issues.extend(analysis.get("issues", []))
            suggestions = analysis.get("suggestions", [])
            missing_descriptions = analysis.get("missing_descriptions", [])
            
            # Apply suggested improvements to endpoints
            for improvement in analysis.get("endpoint_improvements", []):
                for endpoint in api_spec.endpoints:
                    if (endpoint.path == improvement.get("path") and
                        endpoint.method.value == improvement.get("method")):
                        endpoint.suggested_description = improvement.get("suggested_description")
                        # Add parameter suggestions if any
                        if improvement.get("parameter_suggestions"):
                            for param_suggestion in improvement["parameter_suggestions"]:
                                for param in endpoint.parameters:
                                    if param.name == param_suggestion.get("name"):
                                        if not param.description:
                                            param.description = param_suggestion.get("suggested_description", "")
        
        # Update session
        session.api_spec = api_spec
        session.original_spec_content = content
        session.status = SessionStatus.API_UPLOADED
        await self.session_manager.update_session(session)
        
        return AnalysisResult(
            api_spec=api_spec,
            issues=issues,
            suggestions=suggestions,
            missing_descriptions=missing_descriptions
        )
    
    async def refine_api(
        self,
        session_id: str,
        message: str
    ) -> tuple[APISpec, str]:
        """
        Refine API spec through chat interaction.
        Returns updated spec and AI response.
        """
        if not self.ai_service:
            raise ValueError("AI service not configured. Please set OPENAI_API_KEY.")
        
        session = await self.session_manager.get_session(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")
        
        if not session.api_spec:
            raise ValueError("No API spec uploaded. Please upload an API spec first.")
        
        # Add user message to history
        session.chat_history.append({"role": "user", "content": message})
        
        # Refine with AI
        updated_spec, response = await self.ai_service.refine_api_with_chat(
            session.api_spec,
            message,
            session.chat_history
        )
        
        # Add assistant response to history
        session.chat_history.append({"role": "assistant", "content": response})
        
        # Update session
        session.api_spec = updated_spec
        session.status = SessionStatus.API_REFINED
        await self.session_manager.update_session(session)
        
        return updated_spec, response
    
    # =========================================================================
    # Scenario Setup
    # =========================================================================
    
    async def suggest_scenarios(self, session_id: str) -> list[dict[str, Any]]:
        """Get AI-suggested scenarios based on API spec"""
        if not self.ai_service:
            raise ValueError("AI service not configured. Please set OPENAI_API_KEY.")
        
        session = await self.session_manager.get_session(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")
        
        if not session.api_spec:
            raise ValueError("No API spec uploaded. Please upload an API spec first.")
        
        return await self.ai_service.suggest_scenarios(session.api_spec)
    
    async def create_scenario(
        self,
        session_id: str,
        scenario_data: dict[str, Any]
    ) -> Scenario:
        """Create a new scenario"""
        session = await self.session_manager.get_session(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")
        
        # Build scenario from data
        scenario = self._build_scenario_from_data(scenario_data)
        
        # Add to session
        session.scenarios.append(scenario)
        session.status = SessionStatus.SCENARIOS_DEFINED
        await self.session_manager.update_session(session)
        
        return scenario
    
    async def update_scenario(
        self,
        session_id: str,
        scenario_id: str,
        scenario_data: dict[str, Any]
    ) -> Scenario:
        """Update an existing scenario"""
        session = await self.session_manager.get_session(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")
        
        # Find and update scenario
        for i, s in enumerate(session.scenarios):
            if s.id == scenario_id:
                updated = self._build_scenario_from_data(scenario_data)
                updated.id = scenario_id
                session.scenarios[i] = updated
                await self.session_manager.update_session(session)
                return updated
        
        raise ValueError(f"Scenario not found: {scenario_id}")
    
    async def delete_scenario(self, session_id: str, scenario_id: str) -> bool:
        """Delete a scenario"""
        session = await self.session_manager.get_session(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")
        
        for i, s in enumerate(session.scenarios):
            if s.id == scenario_id:
                session.scenarios.pop(i)
                await self.session_manager.update_session(session)
                return True
        
        return False
    
    async def get_scenarios(self, session_id: str) -> list[Scenario]:
        """Get all scenarios for a session"""
        session = await self.session_manager.get_session(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")
        
        return session.scenarios
    
    def _build_scenario_from_data(self, data: dict[str, Any]) -> Scenario:
        """Build Scenario object from dictionary data"""
        # Build API mappings
        api_mappings = []
        for mapping_data in data.get("api_mappings", []):
            if isinstance(mapping_data, dict):
                param_mappings = [
                    ParameterMapping(**pm) if isinstance(pm, dict) else pm
                    for pm in mapping_data.get("parameter_mappings", [])
                ]
                api_mappings.append(APIMapping(
                    endpoint_path=mapping_data.get("endpoint_path", ""),
                    method=HTTPMethod(mapping_data.get("method", "GET")),
                    parameter_mappings=param_mappings,
                    static_params=mapping_data.get("static_params", {})
                ))
        
        # Handle single api_mapping for convenience
        if "api_mapping" in data and not api_mappings:
            mapping_data = data["api_mapping"]
            param_mappings = [
                ParameterMapping(**pm) if isinstance(pm, dict) else pm
                for pm in mapping_data.get("parameter_mappings", [])
            ]
            api_mappings.append(APIMapping(
                endpoint_path=mapping_data.get("endpoint_path", ""),
                method=HTTPMethod(mapping_data.get("method", "GET")),
                parameter_mappings=param_mappings,
                static_params=mapping_data.get("static_params", {})
            ))
        
        # Build response template
        response_template = None
        if "response_template" in data:
            if isinstance(data["response_template"], str):
                response_template = ResponseTemplate(template=data["response_template"])
            elif isinstance(data["response_template"], dict):
                response_template = ResponseTemplate(**data["response_template"])
        
        return Scenario(
            id=data.get("id") or str(uuid4()),
            name=data.get("name", "Unnamed Scenario"),
            description=data.get("description", ""),
            sample_questions=data.get("sample_questions", []),
            required_entities=data.get("required_entities", []),
            api_mappings=api_mappings,
            response_template=response_template
        )
    
    # =========================================================================
    # Agent Management
    # =========================================================================
    
    async def finalize_agent(
        self,
        session_id: str,
        name: str = "API Agent",
        auth_config: dict[str, Any] | None = None,
        use_mock_api: bool = False
    ) -> str:
        """Finalize session and create Q&A agent"""
        if not self.ai_service or not self.agent_manager:
            raise ValueError("AI service not configured. Please set OPENAI_API_KEY.")
        
        session = await self.session_manager.get_session(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")
        
        if not session.api_spec:
            raise ValueError("No API spec uploaded.")
        
        if not session.scenarios:
            raise ValueError("No scenarios defined.")
        
        # Create agent config
        config = AgentConfig(
            session_id=session_id,
            name=name,
            description=f"Q&A Agent for {session.api_spec.title}",
            api_spec=session.api_spec,
            scenarios=session.scenarios,
            auth_config=auth_config or {}
        )
        
        # Save agent
        agent_id = await self.session_manager.save_agent(config)
        
        # Create agent instance
        self.agent_manager.create_agent(agent_id, config, use_mock_api)
        
        # Update session
        session.status = SessionStatus.AGENT_CREATED
        session.agent_config = {"agent_id": agent_id, "name": name}
        await self.session_manager.update_session(session)
        
        return agent_id
    
    async def load_agent(self, agent_id: str, use_mock_api: bool = False) -> QAAgent | None:
        """Load agent from storage"""
        if not self.ai_service or not self.agent_manager:
            raise ValueError("AI service not configured.")
        
        # Check if already loaded
        agent = self.agent_manager.get_agent(agent_id)
        if agent:
            return agent
        
        # Load from storage
        config = await self.session_manager.get_agent(agent_id)
        if not config:
            return None
        
        return self.agent_manager.create_agent(agent_id, config, use_mock_api)
    
    async def chat_with_agent(
        self,
        agent_id: str,
        question: str
    ) -> AgentResponse:
        """Chat with an agent"""
        if not self.agent_manager:
            raise ValueError("AI service not configured.")
        
        # Try to get or load agent
        agent = self.agent_manager.get_agent(agent_id)
        if not agent:
            agent = await self.load_agent(agent_id)
        
        if not agent:
            raise ValueError(f"Agent not found: {agent_id}")
        
        return await agent.answer(question)
    
    async def list_agents(self) -> list[dict[str, Any]]:
        """List all saved agents"""
        return await self.session_manager.list_agents()
    
    # =========================================================================
    # Template Utilities
    # =========================================================================
    
    def validate_template(self, template: str) -> tuple[bool, str | None]:
        """Validate a response template"""
        return self.template_renderer.validate_template(template)
    
    def get_template_variables(self, template: str) -> list[str]:
        """Get variables used in a template"""
        return self.template_renderer.extract_variables(template)
    
    def preview_template(
        self,
        template: str,
        sample_data: dict[str, Any]
    ) -> str:
        """Preview template with sample data"""
        return self.template_renderer.render(template, sample_data)