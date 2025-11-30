"""
Session Manager Service - Manage user sessions and state
"""
import json
import os
from datetime import datetime
from typing import Any
from uuid import uuid4

import aiosqlite

from models import (
    AgentConfig,
    APISpec,
    Scenario,
    Session,
    SessionStatus,
)


class SessionManager:
    """Manage sessions with SQLite backend"""
    
    def __init__(self, db_path: str = "api_agent.db"):
        self.db_path = db_path
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize database tables"""
        if self._initialized:
            return
        
        async with aiosqlite.connect(self.db_path) as db:
            # Sessions table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    api_spec TEXT,
                    original_spec_content TEXT,
                    scenarios TEXT,
                    agent_config TEXT,
                    chat_history TEXT
                )
            """)
            
            # Agents table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS agents (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    config TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                )
            """)
            
            await db.commit()
        
        self._initialized = True
    
    async def create_session(self) -> Session:
        """Create a new session"""
        await self.initialize()
        
        session = Session(
            id=str(uuid4()),
            status=SessionStatus.CREATED,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO sessions (id, status, created_at, updated_at, scenarios, chat_history)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    session.id,
                    session.status.value,
                    session.created_at.isoformat(),
                    session.updated_at.isoformat(),
                    "[]",
                    "[]"
                )
            )
            await db.commit()
        
        return session
    
    async def get_session(self, session_id: str) -> Session | None:
        """Get session by ID"""
        await self.initialize()
        
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM sessions WHERE id = ?",
                (session_id,)
            ) as cursor:
                row = await cursor.fetchone()
                
                if not row:
                    return None
                
                return self._row_to_session(dict(row))
    
    async def update_session(self, session: Session) -> None:
        """Update session"""
        await self.initialize()
        
        session.updated_at = datetime.now()
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE sessions SET
                    status = ?,
                    updated_at = ?,
                    api_spec = ?,
                    original_spec_content = ?,
                    scenarios = ?,
                    agent_config = ?,
                    chat_history = ?
                WHERE id = ?
                """,
                (
                    session.status.value,
                    session.updated_at.isoformat(),
                    session.api_spec.model_dump_json() if session.api_spec else None,
                    session.original_spec_content,
                    json.dumps([s.model_dump() for s in session.scenarios]),
                    json.dumps(session.agent_config),
                    json.dumps(session.chat_history),
                    session.id
                )
            )
            await db.commit()
    
    async def delete_session(self, session_id: str) -> bool:
        """Delete session"""
        await self.initialize()
        
        async with aiosqlite.connect(self.db_path) as db:
            result = await db.execute(
                "DELETE FROM sessions WHERE id = ?",
                (session_id,)
            )
            await db.commit()
            return result.rowcount > 0
    
    async def list_sessions(self, limit: int = 50) -> list[Session]:
        """List recent sessions"""
        await self.initialize()
        
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ?",
                (limit,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [self._row_to_session(dict(row)) for row in rows]
    
    async def save_agent(self, agent_config: AgentConfig) -> str:
        """Save agent configuration"""
        await self.initialize()
        
        agent_id = str(uuid4())
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO agents (id, session_id, name, config, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    agent_id,
                    agent_config.session_id,
                    agent_config.name,
                    agent_config.model_dump_json(),
                    datetime.now().isoformat()
                )
            )
            await db.commit()
        
        return agent_id
    
    async def get_agent(self, agent_id: str) -> AgentConfig | None:
        """Get agent by ID"""
        await self.initialize()
        
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM agents WHERE id = ?",
                (agent_id,)
            ) as cursor:
                row = await cursor.fetchone()
                
                if not row:
                    return None
                
                return AgentConfig(**json.loads(row["config"]))
    
    async def list_agents(self, session_id: str | None = None) -> list[dict[str, Any]]:
        """List agents"""
        await self.initialize()
        
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            if session_id:
                query = "SELECT id, session_id, name, created_at FROM agents WHERE session_id = ?"
                params = (session_id,)
            else:
                query = "SELECT id, session_id, name, created_at FROM agents ORDER BY created_at DESC"
                params = ()
            
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    
    def _row_to_session(self, row: dict) -> Session:
        """Convert database row to Session object"""
        api_spec = None
        if row.get("api_spec"):
            api_spec = APISpec(**json.loads(row["api_spec"]))
        
        scenarios = []
        if row.get("scenarios"):
            scenarios_data = json.loads(row["scenarios"])
            scenarios = [Scenario(**s) for s in scenarios_data]
        
        return Session(
            id=row["id"],
            status=SessionStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            api_spec=api_spec,
            original_spec_content=row.get("original_spec_content") or "",
            scenarios=scenarios,
            agent_config=json.loads(row.get("agent_config") or "{}"),
            chat_history=json.loads(row.get("chat_history") or "[]")
        )