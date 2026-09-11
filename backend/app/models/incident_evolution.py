from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

from app.models.enums import (
    IncidentEvolutionCategory,
    SeverityLevel,
)


class IncidentEvolutionEvent(BaseModel):
    event_id: str
    target_id: str
    target_type: str  # CITIZEN_REPORT or SITUATION
    category: IncidentEvolutionCategory
    event_type: str
    timestamp: datetime
    actor_id: Optional[str] = None
    actor_name: Optional[str] = None
    actor_role: Optional[str] = None
    summary: str
    details: Optional[str] = None
    severity: str = "INFO"  # INFO, LOW, MEDIUM, HIGH, CRITICAL
    source_reference: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class IncidentEvolutionTimelineResponse(BaseModel):
    target_id: str
    target_type: str
    total_events: int
    events: List[IncidentEvolutionEvent] = Field(default_factory=list)
    generated_at: datetime
