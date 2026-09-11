import secrets
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, model_validator
from app.models.enums import (
    ResourceType,
    ResourceStatus,
    ResourceCondition,
    NeedUrgency,
    AllocationStatus,
    BottleneckType,
    BottleneckSeverity,
)


def generate_resource_id() -> str:
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    suffix = "".join(secrets.choice(alphabet) for _ in range(8))
    return f"RES-AST-{suffix}"


def generate_need_id() -> str:
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    suffix = "".join(secrets.choice(alphabet) for _ in range(8))
    return f"NED-{suffix}"


def generate_allocation_id() -> str:
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    suffix = "".join(secrets.choice(alphabet) for _ in range(8))
    return f"ALC-{suffix}"


class ResourceLocation(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    address: Optional[str] = None
    street_address: Optional[str] = None
    landmark: Optional[str] = None
    zone_or_district: Optional[str] = None
    district: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None


class ResourceCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    resource_type: ResourceType
    category: Optional[str] = None
    quantity_total: float = Field(..., ge=0.0)
    quantity_available: float = Field(..., ge=0.0)
    unit: str = Field(..., min_length=1, max_length=50)
    location: ResourceLocation
    status: ResourceStatus = ResourceStatus.AVAILABLE
    condition: ResourceCondition = ResourceCondition.GOOD
    owner: Optional[str] = None
    contact: Optional[str] = None
    notes: Optional[str] = None

    @model_validator(mode="after")
    def validate_quantities(self):
        if self.quantity_available > self.quantity_total:
            raise ValueError("Available quantity cannot exceed total quantity")
        if self.quantity_available == 0 and self.status == ResourceStatus.AVAILABLE:
            self.status = ResourceStatus.UNAVAILABLE
        elif self.quantity_available < self.quantity_total and self.quantity_available > 0 and self.status == ResourceStatus.AVAILABLE:
            self.status = ResourceStatus.PARTIALLY_AVAILABLE
        return self


class ResourceUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=200)
    resource_type: Optional[ResourceType] = None
    category: Optional[str] = None
    quantity_total: Optional[float] = Field(None, ge=0.0)
    quantity_available: Optional[float] = Field(None, ge=0.0)
    unit: Optional[str] = Field(None, min_length=1, max_length=50)
    location: Optional[ResourceLocation] = None
    status: Optional[ResourceStatus] = None
    condition: Optional[ResourceCondition] = None
    owner: Optional[str] = None
    contact: Optional[str] = None
    notes: Optional[str] = None


class ResourceQuantityUpdate(BaseModel):
    quantity_total: Optional[float] = Field(None, ge=0.0)
    quantity_available: float = Field(..., ge=0.0)
    reason: Optional[str] = None


class ResourceStatusUpdate(BaseModel):
    status: ResourceStatus
    reason: Optional[str] = None


class ResourceResponse(BaseModel):
    resource_id: str
    name: str
    resource_type: ResourceType
    category: Optional[str] = None
    quantity_total: float
    quantity_available: float
    unit: str
    location: ResourceLocation
    status: ResourceStatus
    condition: ResourceCondition
    owner: Optional[str] = None
    contact: Optional[str] = None
    notes: Optional[str] = None
    created_by: Optional[str] = None
    created_by_name: Optional[str] = None
    updated_by: Optional[str] = None
    updated_by_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class PaginatedResourcesResponse(BaseModel):
    items: List[ResourceResponse]
    total: int
    page: int
    limit: int
    total_pages: int


class ResourceStatsResponse(BaseModel):
    total_resources: int
    available_resources: int
    partially_available: int
    unavailable: int
    type_counts: Dict[str, int] = Field(default_factory=dict)


# --- Needs Assessment Models ---

class EmergencyNeedItem(BaseModel):
    need_id: str = Field(default_factory=generate_need_id)
    resource_type: ResourceType
    requested_quantity: float = Field(..., gt=0.0)
    unit: str = Field(..., min_length=1, max_length=50)
    urgency: NeedUrgency = NeedUrgency.HIGH
    reason: Optional[str] = None


class NeedsAssessmentCreate(BaseModel):
    needs: List[EmergencyNeedItem] = Field(..., min_length=1)


class NeedsAssessmentResponse(BaseModel):
    report_id: str
    needs: List[EmergencyNeedItem]
    assessed_by: str
    assessed_by_id: str
    assessed_at: datetime
    updated_at: datetime


class AINeedsSuggestionItem(BaseModel):
    resource_type: ResourceType
    suggested_quantity: float
    unit: str
    urgency: NeedUrgency
    reasoning: str
    confidence: float = Field(..., ge=0.0, le=1.0)


class AINeedsSuggestionResponse(BaseModel):
    report_id: str
    suggestions: List[AINeedsSuggestionItem]
    ai_available: bool = True
    disclaimer: str = "AI recommendations are advisory only. Emergency Officer verification is mandatory."


# --- Resource Matching Models ---

class ResourceMatchCandidate(BaseModel):
    resource_id: str
    name: str
    resource_type: ResourceType
    quantity_available: float
    unit: str
    distance_km: float
    match_score: float
    location: ResourceLocation
    status: ResourceStatus
    condition: ResourceCondition
    reasoning: List[str] = Field(default_factory=list)
    recommended_allocation: float


class NeedMatchResult(BaseModel):
    need_id: str
    resource_type: ResourceType
    requested_quantity: float
    unit: str
    urgency: NeedUrgency
    candidates: List[ResourceMatchCandidate] = Field(default_factory=list)
    total_matched_available: float = 0.0
    is_fully_matchable: bool = False


class ResourceMatchingResponse(BaseModel):
    report_id: str
    needs_matches: List[NeedMatchResult]
    generated_at: datetime
    ai_explanation: Optional[str] = None


# --- Allocation Models ---

class AllocationCreateRequest(BaseModel):
    need_id: str
    resource_id: str
    requested_quantity: float = Field(..., gt=0.0)
    notes: Optional[str] = None


class AllocationActionRequest(BaseModel):
    reason: Optional[str] = None


class AllocationResponse(BaseModel):
    allocation_id: str
    report_id: str
    need_id: str
    resource_id: str
    resource_name: str
    resource_type: ResourceType
    requested_quantity: float
    approved_quantity: float
    unit: str
    status: AllocationStatus
    proposed_by: str
    proposed_by_id: str
    approved_by: Optional[str] = None
    approved_by_id: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


# --- Phase D: Resource Bottleneck Intelligence Models ---

def generate_bottleneck_id() -> str:
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    suffix = "".join(secrets.choice(alphabet) for _ in range(8))
    return f"BTN-{suffix}"


class AffectedSituationRef(BaseModel):
    situation_id: str
    title: str = "Emergency Incident"
    emergency_type: Optional[str] = None
    required_quantity: float
    urgency: NeedUrgency = NeedUrgency.HIGH
    severity_level: Optional[str] = None


class AffectedTaskRef(BaseModel):
    task_id: str
    situation_id: str
    title: str
    status: str
    allocated_quantity: float
    consumed_quantity: float = 0.0


class ContentionDetail(BaseModel):
    total_demand: float
    eligible_supply: float
    contention_deficit: float
    competing_situations: List[Dict[str, Any]] = Field(default_factory=list)


class AlternativeResourceOption(BaseModel):
    resource_id: str
    name: str
    resource_type: ResourceType
    quantity_available: float
    unit: str
    location_name: Optional[str] = None
    distance_km: Optional[float] = None
    feasibility_notes: Optional[str] = None


class ResourceBottleneckItem(BaseModel):
    bottleneck_id: str = Field(default_factory=generate_bottleneck_id)
    resource_type: ResourceType
    resource_name: Optional[str] = None
    severity: BottleneckSeverity = BottleneckSeverity.HIGH
    bottleneck_type: BottleneckType = BottleneckType.RESOURCE_SHORTAGE
    required: float
    available: float
    allocated: float = 0.0
    consumed: float = 0.0
    shortfall: float
    unit: str
    affected_situations: List[AffectedSituationRef] = Field(default_factory=list)
    affected_tasks: List[AffectedTaskRef] = Field(default_factory=list)
    contention: Optional[ContentionDetail] = None
    alternative_options: List[AlternativeResourceOption] = Field(default_factory=list)
    why_bottleneck: str
    recommended_action: str
    supporting_records: Dict[str, Any] = Field(default_factory=dict)
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class ResourceBottleneckSummary(BaseModel):
    total_bottlenecks: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    total_shortfall_by_type: Dict[str, float] = Field(default_factory=dict)
    affected_situations_count: int = 0
    contention_count: int = 0
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class ResourceBottlenecksResponse(BaseModel):
    summary: ResourceBottleneckSummary
    items: List[ResourceBottleneckItem]
    total: int
    page: int
    limit: int
    total_pages: int
