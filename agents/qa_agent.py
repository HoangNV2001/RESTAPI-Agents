"""
Q&A Agent - The intelligent agent that handles user questions
"""
from typing import Any

from models import (
    AgentConfig,
    AgentResponse,
    ExtractedEntity,
    Scenario,
    ScenarioMatch,
)
from services import AIService, APIExecutor, TemplateRenderer


class QAAgent:
    """
    Q&A Agent that matches user questions to scenarios,
    executes API calls, and renders responses.
    """
    
    def __init__(
        self,
        config: AgentConfig,
        ai_service: AIService,
        use_mock_api: bool = False
    ):
        self.config = config
        self.ai_service = ai_service
        self.use_mock_api = use_mock_api
        
        # Initialize API executor
        if use_mock_api:
            from services import MockAPIExecutor
            self.api_executor = MockAPIExecutor(
                config.api_spec,
                auth_config=config.auth_config
            )
        else:
            self.api_executor = APIExecutor(
                config.api_spec,
                auth_config=config.auth_config
            )
        
        # Initialize template renderer
        self.template_renderer = TemplateRenderer()
    
    async def answer(self, question: str) -> AgentResponse:
        """
        Process user question and return answer.
        
        Steps:
        1. Match question to scenario
        2. Extract entities from question
        3. Execute API calls
        4. Render response using template
        """
        
        # Step 1 & 2: Match scenario and extract entities
        match_result = await self.ai_service.match_scenario(
            question,
            self.config.scenarios
        )
        
        if not match_result or match_result.confidence < 0.3:
            return AgentResponse(
                answer="Xin lỗi, tôi không hiểu câu hỏi của bạn. "
                       "Vui lòng thử diễn đạt theo cách khác.",
                scenario_used=None,
                api_calls_made=[],
                raw_api_responses=[]
            )
        
        scenario = match_result.scenario
        entities = match_result.extracted_entities
        
        # Check if all required entities are extracted
        missing_entities = self._check_missing_entities(scenario, entities)
        if missing_entities:
            return AgentResponse(
                answer=f"Vui lòng cung cấp thêm thông tin: {', '.join(missing_entities)}",
                scenario_used=scenario.name,
                api_calls_made=[],
                raw_api_responses=[]
            )
        
        # Step 3: Execute API calls
        api_results = await self.api_executor.execute_scenario(scenario, entities)
        
        # Step 4: Render response
        if scenario.response_template:
            answer = self.template_renderer.render_api_response(
                scenario.response_template.template,
                api_results,
                error_template=scenario.response_template.error_template,
                no_data_template=scenario.response_template.no_data_template
            )
        else:
            # Use AI to generate response if no template
            successful_data = [
                r["data"] for r in api_results
                if r.get("success") and r.get("data")
            ]
            
            if successful_data:
                answer = await self.ai_service.generate_response(
                    question,
                    scenario,
                    successful_data[0] if len(successful_data) == 1 else successful_data
                )
            else:
                errors = [r.get("error", "Unknown error") for r in api_results if not r.get("success")]
                answer = f"Xin lỗi, không thể lấy thông tin. Lỗi: {'; '.join(errors)}"
        
        return AgentResponse(
            answer=answer,
            scenario_used=scenario.name,
            api_calls_made=[
                {"endpoint": r["endpoint"], "success": r["success"]}
                for r in api_results
            ],
            raw_api_responses=api_results
        )
    
    def _check_missing_entities(
        self,
        scenario: Scenario,
        entities: list[ExtractedEntity]
    ) -> list[str]:
        """Check for missing required entities"""
        extracted_names = {e.name for e in entities}
        missing = []
        
        for required in scenario.required_entities:
            if required not in extracted_names:
                missing.append(required)
        
        return missing
    
    async def list_capabilities(self) -> list[dict[str, Any]]:
        """List what the agent can do"""
        capabilities = []
        
        for scenario in self.config.scenarios:
            capabilities.append({
                "name": scenario.name,
                "description": scenario.description,
                "sample_questions": scenario.sample_questions,
                "required_info": scenario.required_entities
            })
        
        return capabilities
    
    def get_scenario_by_name(self, name: str) -> Scenario | None:
        """Get scenario by name"""
        for scenario in self.config.scenarios:
            if scenario.name == name:
                return scenario
        return None


class AgentManager:
    """Manage multiple Q&A agents"""
    
    def __init__(self, ai_service: AIService):
        self.ai_service = ai_service
        self.agents: dict[str, QAAgent] = {}
    
    def create_agent(
        self,
        agent_id: str,
        config: AgentConfig,
        use_mock_api: bool = False
    ) -> QAAgent:
        """Create and register a new agent"""
        agent = QAAgent(config, self.ai_service, use_mock_api)
        self.agents[agent_id] = agent
        return agent
    
    def get_agent(self, agent_id: str) -> QAAgent | None:
        """Get agent by ID"""
        return self.agents.get(agent_id)
    
    def remove_agent(self, agent_id: str) -> bool:
        """Remove agent"""
        if agent_id in self.agents:
            del self.agents[agent_id]
            return True
        return False
    
    def list_agents(self) -> list[str]:
        """List all agent IDs"""
        return list(self.agents.keys())