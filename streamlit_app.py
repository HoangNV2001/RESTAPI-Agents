"""
Streamlit Demo for API Agent
"""
import asyncio
import os
import sys

import streamlit as st

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import APIAgentApp


# Initialize app
@st.cache_resource
def get_app():
    api_key = os.getenv("OPENAI_API_KEY", "")
    return APIAgentApp(openai_api_key=api_key if api_key else None)


def run_async(coro):
    """Run async function in sync context"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# Page config
st.set_page_config(
    page_title="API Agent Builder",
    page_icon="🤖",
    layout="wide"
)

st.title("🤖 API Agent Builder")
st.markdown("Build intelligent Q&A agents from your API specifications")

# Sidebar for API key
with st.sidebar:
    st.header("⚙️ Configuration")
    
    api_key = st.text_input(
        "Openai API Key",
        value=os.getenv("OPENAI_API_KEY", ""),
        type="password",
        help="Required for AI features"
    )
    
    if api_key:
        os.environ["OPENAI_API_KEY"] = api_key
        app = get_app()
        if not app.ai_service:
            app.set_api_key(api_key)
        st.success("✅ API Key configured")
    else:
        st.warning("⚠️ Enter API key for AI features")

# Initialize session state
if "current_session_id" not in st.session_state:
    st.session_state.current_session_id = None
if "current_agent_id" not in st.session_state:
    st.session_state.current_agent_id = None
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# Main tabs
tab1, tab2, tab3, tab4 = st.tabs([
    "📄 1. Upload API Spec",
    "🎯 2. Define Scenarios",
    "🚀 3. Create Agent",
    "💬 4. Chat with Agent"
])

app = get_app()

# =============================================================================
# Tab 1: Upload API Spec
# =============================================================================
with tab1:
    st.header("Upload API Specification")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        # Create new session
        if st.button("🆕 Create New Session"):
            session = run_async(app.create_session())
            st.session_state.current_session_id = session.id
            st.success(f"Created session: {session.id[:8]}...")
        
        if st.session_state.current_session_id:
            st.info(f"Current Session: `{st.session_state.current_session_id[:8]}...`")
    
    with col2:
        # List existing sessions
        sessions = run_async(app.list_sessions())
        if sessions:
            session_options = {
                f"{s.id[:8]}... - {s.api_spec.title if s.api_spec else 'No API'} ({s.status.value})": s.id
                for s in sessions
            }
            selected = st.selectbox("Or select existing session:", [""] + list(session_options.keys()))
            if selected:
                st.session_state.current_session_id = session_options[selected]
    
    st.divider()
    
    if st.session_state.current_session_id:
        # Upload method
        upload_method = st.radio("Upload method:", ["Paste content", "Upload file", "Use sample"])
        
        if upload_method == "Paste content":
            spec_content = st.text_area(
                "Paste your OpenAPI spec (YAML or JSON):",
                height=300,
                placeholder="openapi: 3.0.0\ninfo:\n  title: My API\n..."
            )
            spec_format = st.selectbox("Format:", ["yaml", "json"])
            
            if st.button("📤 Upload & Analyze") and spec_content:
                with st.spinner("Analyzing API spec..."):
                    try:
                        result = run_async(app.upload_api_spec(
                            st.session_state.current_session_id,
                            spec_content,
                            spec_format
                        ))
                        
                        st.success(f"✅ Uploaded: {result.api_spec.title}")
                        st.metric("Endpoints", len(result.api_spec.endpoints))
                        
                        if result.issues:
                            st.warning("**Issues found:**")
                            for issue in result.issues:
                                st.write(f"- {issue}")
                        
                        if result.suggestions:
                            st.info("**Suggestions:**")
                            for suggestion in result.suggestions:
                                st.write(f"- {suggestion}")
                    
                    except Exception as e:
                        st.error(f"Error: {str(e)}")
        
        elif upload_method == "Upload file":
            uploaded_file = st.file_uploader(
                "Upload OpenAPI spec file",
                type=["yaml", "yml", "json"]
            )
            
            if uploaded_file and st.button("📤 Upload & Analyze"):
                content = uploaded_file.read().decode("utf-8")
                spec_format = "json" if uploaded_file.name.endswith(".json") else "yaml"
                
                with st.spinner("Analyzing API spec..."):
                    try:
                        result = run_async(app.upload_api_spec(
                            st.session_state.current_session_id,
                            content,
                            spec_format
                        ))
                        
                        st.success(f"✅ Uploaded: {result.api_spec.title}")
                        st.metric("Endpoints", len(result.api_spec.endpoints))
                    
                    except Exception as e:
                        st.error(f"Error: {str(e)}")
        
        else:  # Use sample
            st.markdown("**Sample APIs:**")
            
            sample_api = """openapi: 3.0.0
info:
  title: E-Commerce API
  version: 1.0.0
  description: Sample e-commerce API for products and orders
servers:
  - url: https://api.example.com/v1
paths:
  /products:
    get:
      operationId: listProducts
      summary: List all products
      tags:
        - Products
      parameters:
        - name: category
          in: query
          schema:
            type: string
          description: Filter by category
        - name: limit
          in: query
          schema:
            type: integer
            default: 10
      responses:
        '200':
          description: List of products
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/Product'
  /products/{productId}:
    get:
      operationId: getProduct
      summary: Get product by ID
      tags:
        - Products
      parameters:
        - name: productId
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Product details
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Product'
              example:
                id: "prod-123"
                name: "Laptop Pro"
                price: 25000000
                category: "electronics"
                stock: 50
  /orders:
    get:
      operationId: listOrders
      summary: List orders
      tags:
        - Orders
      parameters:
        - name: status
          in: query
          schema:
            type: string
            enum: [pending, processing, shipped, delivered]
      responses:
        '200':
          description: List of orders
    post:
      operationId: createOrder
      summary: Create new order
      tags:
        - Orders
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                productId:
                  type: string
                quantity:
                  type: integer
      responses:
        '201':
          description: Order created
  /orders/{orderId}:
    get:
      operationId: getOrder
      summary: Get order by ID
      tags:
        - Orders
      parameters:
        - name: orderId
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Order details
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Order'
              example:
                id: "ord-456"
                status: "processing"
                total: 25000000
                created_at: "2024-01-15T10:30:00Z"
components:
  schemas:
    Product:
      type: object
      properties:
        id:
          type: string
        name:
          type: string
        price:
          type: number
        category:
          type: string
        stock:
          type: integer
    Order:
      type: object
      properties:
        id:
          type: string
        status:
          type: string
        total:
          type: number
        created_at:
          type: string
"""
            
            if st.button("📤 Load Sample E-Commerce API"):
                with st.spinner("Loading sample API..."):
                    try:
                        result = run_async(app.upload_api_spec(
                            st.session_state.current_session_id,
                            sample_api,
                            "yaml"
                        ))
                        
                        st.success(f"✅ Loaded: {result.api_spec.title}")
                        st.metric("Endpoints", len(result.api_spec.endpoints))
                    
                    except Exception as e:
                        st.error(f"Error: {str(e)}")
        
        # Show current API spec
        session = run_async(app.get_session(st.session_state.current_session_id))
        if session and session.api_spec:
            st.divider()
            st.subheader("📋 Current API Spec")
            
            spec = session.api_spec
            st.write(f"**Title:** {spec.title}")
            st.write(f"**Version:** {spec.version}")
            st.write(f"**Base URL:** {spec.base_url or 'Not specified'}")
            
            with st.expander("View Endpoints"):
                for endpoint in spec.endpoints:
                    st.markdown(f"**{endpoint.method.value}** `{endpoint.path}`")
                    st.write(f"  - {endpoint.summary or endpoint.description or 'No description'}")
                    if endpoint.parameters:
                        params = ", ".join([p.name for p in endpoint.parameters])
                        st.write(f"  - Parameters: {params}")
            
            # Refine with AI
            if app.ai_service:
                st.divider()
                st.subheader("🔧 Refine with AI")
                
                refine_msg = st.text_input(
                    "Enter refinement instruction:",
                    placeholder="e.g., Add descriptions to all endpoints"
                )
                
                if st.button("✨ Refine") and refine_msg:
                    with st.spinner("Refining..."):
                        try:
                            _, response = run_async(app.refine_api(
                                st.session_state.current_session_id,
                                refine_msg
                            ))
                            st.success("✅ Refinement applied")
                            st.write(response)
                        except Exception as e:
                            st.error(f"Error: {str(e)}")

# =============================================================================
# Tab 2: Define Scenarios
# =============================================================================
with tab2:
    st.header("Define Q&A Scenarios")
    
    if not st.session_state.current_session_id:
        st.warning("Please create a session and upload an API spec first.")
    else:
        session = run_async(app.get_session(st.session_state.current_session_id))
        
        if not session or not session.api_spec:
            st.warning("Please upload an API spec first.")
        else:
            col1, col2 = st.columns([1, 1])
            
            with col1:
                st.subheader("➕ Create Scenario")
                
                # Get AI suggestions
                if app.ai_service:
                    if st.button("🤖 Get AI Suggestions"):
                        with st.spinner("Generating suggestions..."):
                            try:
                                suggestions = run_async(app.suggest_scenarios(
                                    st.session_state.current_session_id
                                ))
                                st.session_state.scenario_suggestions = suggestions
                                st.success(f"Generated {len(suggestions)} suggestions")
                            except Exception as e:
                                st.error(f"Error: {str(e)}")
                    
                    # Show suggestions
                    if "scenario_suggestions" in st.session_state and st.session_state.scenario_suggestions:
                        st.write("**AI Suggestions:**")
                        for i, suggestion in enumerate(st.session_state.scenario_suggestions):
                            with st.expander(f"{suggestion.get('name', f'Scenario {i+1}')}"):
                                st.write(f"**Description:** {suggestion.get('description', '')}")
                                st.write(f"**Sample Questions:** {', '.join(suggestion.get('sample_questions', []))}")
                                st.write(f"**Required Entities:** {', '.join(suggestion.get('required_entities', []))}")
                                
                                if st.button(f"Use this suggestion", key=f"use_suggestion_{i}"):
                                    st.session_state.prefill_scenario = suggestion
                
                st.divider()
                
                # Manual scenario creation
                st.write("**Create Scenario Manually:**")
                
                # Prefill from suggestion if available
                prefill = st.session_state.get("prefill_scenario", {})
                
                scenario_name = st.text_input("Name:", value=prefill.get("name", ""))
                scenario_desc = st.text_area("Description:", value=prefill.get("description", ""))
                
                sample_questions = st.text_area(
                    "Sample Questions (one per line):",
                    value="\n".join(prefill.get("sample_questions", []))
                )
                
                required_entities = st.text_input(
                    "Required Entities (comma-separated):",
                    value=", ".join(prefill.get("required_entities", []))
                )
                
                # API mapping
                st.write("**API Mapping:**")
                endpoints = [(f"{e.method.value} {e.path}", e) for e in session.api_spec.endpoints]
                endpoint_options = [e[0] for e in endpoints]
                
                selected_endpoint = st.selectbox("Select endpoint:", endpoint_options)
                
                # Parameter mappings
                if selected_endpoint:
                    selected_ep = next((e[1] for e in endpoints if e[0] == selected_endpoint), None)
                    if selected_ep and selected_ep.parameters:
                        st.write("**Parameter Mappings:**")
                        param_mappings = []
                        for param in selected_ep.parameters:
                            entity = st.text_input(
                                f"Entity for '{param.name}':",
                                key=f"param_{param.name}",
                                placeholder=f"e.g., {param.name}"
                            )
                            if entity:
                                param_mappings.append({
                                    "entity_name": entity,
                                    "api_parameter": param.name
                                })
                
                # Response template
                response_template = st.text_area(
                    "Response Template (Jinja2):",
                    value=prefill.get("response_template", ""),
                    placeholder="Example: Sản phẩm {{ name }} có giá {{ price | format_currency }}"
                )
                
                if st.button("💾 Create Scenario"):
                    if not scenario_name:
                        st.error("Please enter a scenario name")
                    else:
                        # Parse inputs
                        questions = [q.strip() for q in sample_questions.split("\n") if q.strip()]
                        entities = [e.strip() for e in required_entities.split(",") if e.strip()]
                        
                        # Build API mapping
                        api_mapping = None
                        if selected_endpoint:
                            parts = selected_endpoint.split(" ", 1)
                            api_mapping = {
                                "endpoint_path": parts[1] if len(parts) > 1 else parts[0],
                                "method": parts[0],
                                "parameter_mappings": param_mappings if 'param_mappings' in dir() else []
                            }
                        
                        scenario_data = {
                            "name": scenario_name,
                            "description": scenario_desc,
                            "sample_questions": questions,
                            "required_entities": entities,
                            "api_mapping": api_mapping,
                            "response_template": response_template if response_template else None
                        }
                        
                        try:
                            scenario = run_async(app.create_scenario(
                                st.session_state.current_session_id,
                                scenario_data
                            ))
                            st.success(f"✅ Created scenario: {scenario.name}")
                            
                            # Clear prefill
                            if "prefill_scenario" in st.session_state:
                                del st.session_state.prefill_scenario
                        
                        except Exception as e:
                            st.error(f"Error: {str(e)}")
            
            with col2:
                st.subheader("📋 Current Scenarios")
                
                scenarios = run_async(app.get_scenarios(st.session_state.current_session_id))
                
                if not scenarios:
                    st.info("No scenarios defined yet.")
                else:
                    for scenario in scenarios:
                        with st.expander(f"🎯 {scenario.name}"):
                            st.write(f"**Description:** {scenario.description}")
                            st.write(f"**Sample Questions:**")
                            for q in scenario.sample_questions:
                                st.write(f"  - {q}")
                            st.write(f"**Required Entities:** {', '.join(scenario.required_entities)}")
                            
                            if scenario.api_mappings:
                                st.write("**API Mappings:**")
                                for mapping in scenario.api_mappings:
                                    st.write(f"  - {mapping.method.value} {mapping.endpoint_path}")
                            
                            if scenario.response_template:
                                st.write(f"**Template:** `{scenario.response_template.template[:100]}...`")
                            
                            if st.button(f"🗑️ Delete", key=f"delete_{scenario.id}"):
                                run_async(app.delete_scenario(
                                    st.session_state.current_session_id,
                                    scenario.id
                                ))
                                st.rerun()

# =============================================================================
# Tab 3: Create Agent
# =============================================================================
with tab3:
    st.header("Finalize & Create Agent")
    
    if not st.session_state.current_session_id:
        st.warning("Please create a session first.")
    else:
        session = run_async(app.get_session(st.session_state.current_session_id))
        
        if not session or not session.api_spec:
            st.warning("Please upload an API spec first.")
        elif not session.scenarios:
            st.warning("Please define at least one scenario first.")
        else:
            st.success("✅ Ready to create agent!")
            
            st.write(f"**API:** {session.api_spec.title}")
            st.write(f"**Scenarios:** {len(session.scenarios)}")
            
            st.divider()
            
            agent_name = st.text_input("Agent Name:", value=f"{session.api_spec.title} Agent")
            
            # Auth config
            st.subheader("🔐 Authentication (Optional)")
            auth_type = st.selectbox("Auth Type:", ["None", "Bearer Token", "API Key", "Basic Auth"])
            
            auth_config = {}
            if auth_type == "Bearer Token":
                token = st.text_input("Bearer Token:", type="password")
                if token:
                    auth_config = {"type": "bearer", "token": token}
            elif auth_type == "API Key":
                key_name = st.text_input("Header Name:", value="X-API-Key")
                key_value = st.text_input("API Key:", type="password")
                if key_value:
                    auth_config = {
                        "type": "api_key",
                        "key_name": key_name,
                        "key_value": key_value,
                        "key_location": "header"
                    }
            elif auth_type == "Basic Auth":
                username = st.text_input("Username:")
                password = st.text_input("Password:", type="password")
                if username and password:
                    auth_config = {
                        "type": "basic",
                        "username": username,
                        "password": password
                    }
            
            # Mock API option
            use_mock = st.checkbox("Use Mock API (for testing without real API)")
            
            st.divider()
            
            if st.button("🚀 Create Agent", type="primary"):
                if not app.ai_service:
                    st.error("Please configure Openai API key first.")
                else:
                    with st.spinner("Creating agent..."):
                        try:
                            agent_id = run_async(app.finalize_agent(
                                st.session_state.current_session_id,
                                name=agent_name,
                                auth_config=auth_config,
                                use_mock_api=use_mock
                            ))
                            
                            st.session_state.current_agent_id = agent_id
                            st.success(f"✅ Agent created! ID: {agent_id[:8]}...")
                            st.balloons()
                        
                        except Exception as e:
                            st.error(f"Error: {str(e)}")
            
            # List existing agents
            st.divider()
            st.subheader("📋 Existing Agents")
            
            agents = run_async(app.list_agents())
            if agents:
                for agent in agents:
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.write(f"**{agent['name']}** (`{agent['id'][:8]}...`)")
                    with col2:
                        if st.button("Use", key=f"use_agent_{agent['id']}"):
                            st.session_state.current_agent_id = agent['id']
                            st.success(f"Selected agent: {agent['name']}")
            else:
                st.info("No agents created yet.")

# =============================================================================
# Tab 4: Chat with Agent
# =============================================================================
with tab4:
    st.header("Chat with Agent")
    
    if not st.session_state.current_agent_id:
        st.warning("Please create or select an agent first.")
        
        # Quick select
        agents = run_async(app.list_agents())
        if agents:
            agent_options = {f"{a['name']} ({a['id'][:8]}...)": a['id'] for a in agents}
            selected = st.selectbox("Select an agent:", [""] + list(agent_options.keys()))
            if selected:
                st.session_state.current_agent_id = agent_options[selected]
                st.rerun()
    else:
        # Load agent
        try:
            agent = run_async(app.load_agent(st.session_state.current_agent_id, use_mock_api=True))
            
            if not agent:
                st.error("Agent not found.")
            else:
                st.success(f"🤖 Chatting with: **{agent.config.name}**")
                
                # Show capabilities
                with st.expander("📚 Agent Capabilities"):
                    capabilities = run_async(agent.list_capabilities())
                    for cap in capabilities:
                        st.write(f"**{cap['name']}:** {cap['description']}")
                        st.write(f"  Sample: {cap['sample_questions'][0] if cap['sample_questions'] else 'N/A'}")
                
                st.divider()
                
                # Chat interface
                for msg in st.session_state.chat_history:
                    if msg["role"] == "user":
                        st.chat_message("user").write(msg["content"])
                    else:
                        st.chat_message("assistant").write(msg["content"])
                
                # Input
                if prompt := st.chat_input("Ask a question..."):
                    # Add user message
                    st.session_state.chat_history.append({"role": "user", "content": prompt})
                    st.chat_message("user").write(prompt)
                    
                    # Get response
                    with st.chat_message("assistant"):
                        with st.spinner("Thinking..."):
                            try:
                                response = run_async(app.chat_with_agent(
                                    st.session_state.current_agent_id,
                                    prompt
                                ))
                                
                                st.write(response.answer)
                                
                                # Show details
                                if response.scenario_used:
                                    st.caption(f"📎 Scenario: {response.scenario_used}")
                                if response.api_calls_made:
                                    with st.expander("API Calls"):
                                        for call in response.api_calls_made:
                                            status = "✅" if call.get("success") else "❌"
                                            st.write(f"{status} {call.get('endpoint')}")
                                
                                # Add to history
                                st.session_state.chat_history.append({
                                    "role": "assistant",
                                    "content": response.answer
                                })
                            
                            except Exception as e:
                                st.error(f"Error: {str(e)}")
                
                # Clear chat button
                if st.button("🗑️ Clear Chat"):
                    st.session_state.chat_history = []
                    st.rerun()
        
        except Exception as e:
            st.error(f"Error loading agent: {str(e)}")

# Footer
st.divider()
st.caption("API Agent Builder v1.0 - Built with Streamlit & Claude")