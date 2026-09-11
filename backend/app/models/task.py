import secrets
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from pydantic import BaseModel, Field

from app.models.enums import (
    ResponseTaskStatus,
    TaskType,
    FieldUpdateType,
    SeverityLevel,
    UserRole,
)


def generate_task_id() -> str:
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    suffix = "".join(secrets.choice(alphabet) for _ in range(8))
    return f"TSK-{suffix}"


def generate_update_id() -> str:
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    suffix = "".join(secrets.choice(alphabet) for _ in range(8))
    return f"UPD-{suffix}"


class TaskLocation(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class AssignedResourceItem(BaseModel):
    resource_id: str
    resource_name: str
    resource_type: str
    allocated_quantity: float
    unit: str
    depot_location: Optional[str] = None
    consumed_quantity: float = 0.0


class FieldUpdateRecord(BaseModel):
    update_id: str = Field(default_factory=generate_update_id)
    task_id: str
    situation_id: str
    actor_id: str
    actor_name: str
    actor_role: str
    event_type: FieldUpdateType
    message: str
    location: Optional[TaskLocation] = None
    details: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ResponseTask(BaseModel):
    task_id: str = Field(default_factory=generate_task_id)
    situation_id: str = ""
    plan_id: str = ""
    plan_version: int = 1
    task_type: TaskType = TaskType.RESOURCE_DELIVERY
    title: str = "Field Task"
    description: str = ""
    priority: SeverityLevel = SeverityLevel.MEDIUM
    status: ResponseTaskStatus = ResponseTaskStatus.PENDING_APPROVAL
    
    # Team and Responder Assignments
    assigned_team_id: Optional[str] = None
    assigned_team_name: Optional[str] = None
    assigned_volunteer_ids: List[str] = Field(default_factory=list)
    assigned_volunteer_names: List[str] = Field(default_factory=list)
    
    # Vehicle and Transport Assignments
    assigned_vehicle_id: Optional[str] = None
    assigned_vehicle_name: Optional[str] = None
    assigned_vehicle_type: Optional[str] = None
    
    # Resource Allocations
    assigned_resource_ids: List[str] = Field(default_factory=list)
    assigned_resources: List[AssignedResourceItem] = Field(default_factory=list)
    
    # Plan Source and Spatial Waypoints
    source_plan_component: str = "general"
    location: Optional[TaskLocation] = None
    destination: Optional[TaskLocation] = None
    route_id: Optional[str] = None
    
    # Dependencies and Lifecycle Tracking
    dependencies: List[str] = Field(default_factory=list)
    estimated_duration_minutes: Optional[float] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    completion_notes: Optional[str] = None
    failure_reason: Optional[str] = None
    blocked_reason: Optional[str] = None
    
    # Audit trail & Field Updates Stream
    field_updates: List[FieldUpdateRecord] = Field(default_factory=list)
    created_by: Optional[str] = None
    approved_by: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# API Payload Schemas

class TaskAssignmentRequest(BaseModel):
    assigned_team_id: Optional[str] = None
    assigned_team_name: Optional[str] = None
    assigned_volunteer_ids: Optional[List[str]] = None
    assigned_volunteer_names: Optional[List[str]] = None
    assigned_vehicle_id: Optional[str] = None
    assigned_vehicle_name: Optional[str] = None
    notes: Optional[str] = None


class TaskStatusTransitionRequest(BaseModel):
    notes: Optional[str] = None
    reason: Optional[str] = None
    completion_notes: Optional[str] = None
    consumed_resources: Optional[List[Dict[str, Any]]] = None


class FieldUpdateCreateRequest(BaseModel):
    event_type: FieldUpdateType
    message: str
    location: Optional[TaskLocation] = None
    details: Dict[str, Any] = Field(default_factory=dict)


class IncidentResolutionRequest(BaseModel):
    resolution_notes: str = Field(..., min_length=5, max_length=2000)
    force_override_uncompleted: bool = False
    override_reason: Optional[str] = None


class IncidentCloseRequest(BaseModel):
    close_notes: str = Field(..., min_length=5, max_length=2000)
    final_summary_notes: Optional[str] = None
    force_override_uncompleted: bool = False
    override_reason: Optional[str] = None


# Aggregated Response Schemas

class OperationsOverviewResponse(BaseModel):
    active_plans_count: int = 0
    total_tasks_count: int = 0
    active_tasks_count: int = 0
    pending_tasks_count: int = 0
    approved_tasks_count: int = 0
    assigned_tasks_count: int = 0
    in_progress_tasks_count: int = 0
    completed_tasks_count: int = 0
    blocked_tasks_count: int = 0
    escalated_tasks_count: int = 0
    resources_in_use_count: int = 0
    active_teams_count: int = 0
    active_volunteers_count: int = 0
    active_vehicles_count: int = 0


class PaginatedTasksResponse(BaseModel):
    items: List[ResponseTask]
    total: int
    page: int
    limit: int
    total_pages: int


class IncidentResolutionSummary(BaseModel):
    situation_id: str
    title: str
    emergency_type: str
    severity_level: str
    final_status: str
    total_citizen_reports: int = 0
    active_plan_versions: int = 0
    total_tasks_created: int = 0
    tasks_completed: int = 0
    tasks_blocked_or_failed: int = 0
    resources_utilized: List[Dict[str, Any]] = Field(default_factory=list)
    volunteers_involved_count: int = 0
    vehicles_involved_count: int = 0
    monitoring_events_count: int = 0
    replanning_iterations_count: int = 0
    notifications_sent_count: int = 0
    resolved_by: Optional[str] = None
    resolved_at: Optional[datetime] = None
    closed_by: Optional[str] = None
    closed_at: Optional[datetime] = None
    resolution_notes: Optional[str] = None
    duration_hours: float = 0.0
    created_at: datetime
    updated_at: datetime


class PostIncidentAnalytics(BaseModel):
    situation_id: str
    response_duration_minutes: float = 0.0
    task_completion_rate: float = 0.0
    total_resources_consumed: Dict[str, float] = Field(default_factory=dict)
    average_task_duration_minutes: float = 0.0
    monitoring_events_detected: int = 0
    plan_revision_count: int = 0
    in_app_notifications_count: int = 0
    whatsapp_notifications_count: int = 0
    volunteer_mobilization_count: int = 0
    vehicle_utilization_count: int = 0
