"""
AI Service - Integration with OpenAI GPT-4.1 for intelligent features
"""
import json
import os
from typing import Any

from openai import OpenAI

from models import (
    APIEndpoint,
    APIParameter,
    APISpec,
    ExtractedEntity,
    ParameterLocation,
    ParameterType,
    Scenario,
    ScenarioMatch,
)


class AIService:
    """Service for AI-powered features using OpenAI GPT-4.1"""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is required")

        self.client = OpenAI(api_key=self.api_key)
        self.model = "gpt-4.1"

    # --------------- Helper for LLM calls -----------------
    def _ask_llm(self, prompt: str, max_tokens: int = 4096) -> str:
        """Wrapper for OpenAI chat API"""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=0
        )
        return response.choices[0].message["content"]

    # ------------------------------------------------------

    async def analyze_api_spec(self, api_spec: APISpec) -> dict[str, Any]:
        api_context = self._build_api_context(api_spec)

        prompt = f"""Analyze the following API specification and provide:
1. A list of issues (missing descriptions, inconsistent naming, etc.)
2. Suggestions for improvements
3. Missing descriptions that should be added

API Specification:
{api_context}

Respond in JSON format:
{{
    "issues": ["issue1", "issue2"],
    "suggestions": ["suggestion1", "suggestion2"],
    "missing_descriptions": [
        {{"path": "/endpoint", "method": "GET", "suggested_description": "description"}}
    ],
    "endpoint_improvements": [
        {{
            "path": "/endpoint",
            "method": "GET",
            "suggested_summary": "summary",
            "suggested_description": "description",
            "parameter_suggestions": [
                {{"name": "param", "suggested_description": "description"}}
            ]
        }}
    ]
}}"""

        raw = self._ask_llm(prompt)
        try:
            return json.loads(raw)
        except:
            # Attempt salvage JSON from markdown
            start, end = raw.find("{"), raw.rfind("}") + 1
            if start != -1:
                return json.loads(raw[start:end])
            return {
                "issues": [],
                "suggestions": [raw],
                "missing_descriptions": [],
                "endpoint_improvements": []
            }

    async def suggest_scenarios(self, api_spec: APISpec) -> list[dict[str, Any]]:
        api_context = self._build_api_context(api_spec)

        prompt = f"""Based on the following API specification, suggest practical Q&A scenarios.
Each scenario should represent a common user question that can be answered by calling the API.

API Specification:
{api_context}

Respond in JSON format:
{{
    "scenarios": [
        {{
            "name": "scenario_name",
            "description": "What this scenario does",
            "sample_questions": ["Question 1?", "Question 2?"],
            "required_entities": ["entity1", "entity2"],
            "api_mapping": {{
                "endpoint_path": "/path",
                "method": "GET",
                "parameter_mappings": [
                    {{"entity_name": "entity1", "api_parameter": "param1"}}
                ]
            }},
            "response_template": "Template with {{{{ data.field }}}}"
        }}
    ]
}}"""

        raw = self._ask_llm(prompt)
        try:
            return json.loads(raw).get("scenarios", [])
        except:
            start, end = raw.find("{"), raw.rfind("}") + 1
            if start != -1:
                return json.loads(raw[start:end]).get("scenarios", [])
            return []

    async def refine_api_with_chat(
        self,
        api_spec: APISpec,
        user_message: str,
        chat_history: list[dict[str, str]]
    ) -> tuple[APISpec, str]:

        api_context = self._build_api_context(api_spec)

        history_context = ""
        for msg in chat_history[-10:]:
            history_context += f"{msg['role'].upper()}: {msg['content']}\n"

        prompt = f"""You are helping refine an API specification. The user wants to improve or modify the API documentation.

Current API Specification:
{api_context}

Previous conversation:
{history_context}

User's request: {user_message}

Respond in JSON format:
{{
    "response": "Your natural language response to the user",
    "changes": [
        {{
            "type": "update_description|update_parameter|add_parameter|update_summary",
            "path": "/endpoint",
            "method": "GET",
            "field": "field_name",
            "old_value": "old value",
            "new_value": "new value"
        }}
    ]
}}"""

        raw = self._ask_llm(prompt, max_tokens=2048)
        try:
            data = json.loads(raw)
        except:
            start, end = raw.find("{"), raw.rfind("}") + 1
            data = json.loads(raw[start:end])

        updated_spec = self._apply_changes(api_spec, data.get("changes", []))
        return updated_spec, data.get("response", "")

    async def match_scenario(
        self,
        question: str,
        scenarios: list[Scenario]
    ) -> ScenarioMatch | None:

        scenarios_context = self._build_scenarios_context(scenarios)

        prompt = f"""Given the following user question and available scenarios, determine:
1. Which scenario best matches the question
2. Extract entities

User Question: "{question}"

Available Scenarios:
{scenarios_context}

Respond in JSON format:
{{
    "matched_scenario_id": "scenario_id",
    "confidence": 0.0,
    "extracted_entities": [
        {{"name": "entity_name", "value": "value", "confidence": 1.0}}
    ]
}}"""

        raw = self._ask_llm(prompt, max_tokens=1024)
        try:
            result = json.loads(raw)
        except:
            start, end = raw.find("{"), raw.rfind("}") + 1
            result = json.loads(raw[start:end])

        matched_id = result.get("matched_scenario_id")
        if not matched_id:
            return None

        scenario = next((s for s in scenarios if s.id == matched_id), None)
        if not scenario:
            return None

        entities = [
            ExtractedEntity(
                name=e.get("name", ""),
                value=e.get("value"),
                confidence=e.get("confidence", 1.0)
            )
            for e in result.get("extracted_entities", [])
        ]

        return ScenarioMatch(
            scenario=scenario,
            confidence=result.get("confidence", 0.5),
            extracted_entities=entities
        )

    async def generate_response(
        self,
        question: str,
        scenario: Scenario,
        api_response: dict[str, Any],
        template: str | None = None
    ) -> str:

        prompt = f"""Generate a helpful response to the user based on the API data.

User Question: "{question}"
Scenario: {scenario.name} - {scenario.description}
API Response Data:
{json.dumps(api_response, indent=2, ensure_ascii=False)}

{"Response Template: " + template if template else ""}

Answer in Vietnamese."""

        return self._ask_llm(prompt, max_tokens=1024)

    # ------------------- Builders & Patcher -----------------------------
    def _build_api_context(self, api_spec: APISpec) -> str:
        lines = [
            f"API: {api_spec.title} (v{api_spec.version})",
            f"Description: {api_spec.description}",
            f"Base URL: {api_spec.base_url}",
            "",
            "Endpoints:"
        ]

        for endpoint in api_spec.endpoints:
            lines.append(f"\n  {endpoint.method.value} {endpoint.path}")
            lines.append(f"    Summary: {endpoint.summary}")
            lines.append(f"    Description: {endpoint.description}")
            if endpoint.parameters:
                lines.append("    Parameters:")
                for param in endpoint.parameters:
                    lines.append(
                        f"      - {param.name} ({param.location.value}, {param.param_type.value})"
                    )
        return "\n".join(lines)

    def _build_scenarios_context(self, scenarios: list[Scenario]) -> str:
        chunks = []
        for s in scenarios:
            chunks.append(
                f"""
Scenario ID: {s.id}
  Name: {s.name}
  Description: {s.description}
  Sample Questions: {", ".join(s.sample_questions)}
  Required Entities: {", ".join(s.required_entities)}
"""
            )
        return "\n".join(chunks)

    def _apply_changes(self, api_spec: APISpec, changes: list[dict[str, Any]]) -> APISpec:
        spec_dict = api_spec.model_dump()

        for change in changes:
            path = change.get("path")
            method = change.get("method")
            for ep in spec_dict["endpoints"]:
                if ep["path"] == path and ep["method"] == method:
                    ctype = change["type"]
                    if ctype == "update_description":
                        ep["description"] = change["new_value"]
                    elif ctype == "update_summary":
                        ep["summary"] = change["new_value"]
                    elif ctype == "update_parameter":
                        field = change["field"]
                        for p in ep["parameters"]:
                            if p["name"] == field:
                                p["description"] = change["new_value"]
                    elif ctype == "add_parameter":
                        ep["parameters"].append({
                            "name": change["field"],
                            "location": "query",
                            "param_type": "string",
                            "description": change["new_value"],
                            "required": False
                        })
        return APISpec(**spec_dict)
