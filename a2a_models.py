from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field
from datetime import datetime

# --- Core A2A Types ---

class Part(BaseModel):
    text: Optional[str] = None
    raw: Optional[str] = None
    url: Optional[str] = None
    data: Optional[Any] = None
    mimeType: Optional[str] = None
    mediaType: Optional[str] = None

class Message(BaseModel):
    messageId: str = Field(..., description="Unique ID of the message")
    role: str = Field(..., description="ROLE_USER or ROLE_AGENT")
    parts: List[Part]
    taskId: Optional[str] = None
    contextId: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    created: Optional[datetime] = None

class Artifact(BaseModel):
    artifactId: str
    name: Optional[str] = None
    parts: List[Part]
    metadata: Optional[Dict[str, Any]] = None

class TaskStatus(BaseModel):
    state: str = Field(..., description="Task state: submitted, working, completed, failed, input_required")
    block: Optional[str] = None
    message: Optional[Message] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class Task(BaseModel):
    id: str
    contextId: Optional[str] = None
    status: TaskStatus
    artifacts: Optional[List[Artifact]] = None
    history: Optional[List[Message]] = None
    metadata: Optional[Dict[str, Any]] = None

# --- API Request/Response Types ---

class SendMessageRequest(BaseModel):
    message: Message
    conversationId: Optional[str] = None
    contextId: Optional[str] = None

class A2AResponse(BaseModel):
    task: Optional[Task] = None
    message: Optional[Message] = None

# --- Agent Discovery (Agent Card) ---

class AgentInterface(BaseModel):
    url: str
    protocolBinding: str = "HTTP+JSON"
    protocolVersion: str = "0.3"

class AgentProvider(BaseModel):
    organization: str
    url: str

class AgentCapability(BaseModel):
    streaming: bool = False
    pushNotifications: bool = False
    extensions: List[dict] = []

class AgentCard(BaseModel):
    name: str = "EverLearn"
    description: str = "EverLearn is a iterative learning agent with quality ratchet"
    version: str = "1.0.0"
    supportedInterfaces: List[AgentInterface]
    provider: AgentProvider
    capabilities: AgentCapability
    defaultInputModes: List[str] = ["text/plain"]
    defaultOutputModes: List[str] = ["application/json", "text/markdown"]
