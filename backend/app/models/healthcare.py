import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict, model_validator


class HealthcareFacilityType(str, Enum):
    HOSPITAL = "Hospital"
    TRAUMA_CENTER = "Trauma Center"
    CLINIC = "Clinic"
    SPECIALTY_CENTER = "Specialty Center"
    FIELD_HOSPITAL = "Field Hospital"
    MATERNITY_PEDIATRIC = "Maternity & Pediatric Center"
    OTHER = "Other"


class HealthcareOperationalStatus(str, Enum):
    ACTIVE = "ACTIVE"
    LIMITED = "LIMITED"
    CLOSED = "CLOSED"
    MAINTENANCE = "MAINTENANCE"


class HealthcareLocation(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Latitude coordinate")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Longitude coordinate")
    address: str = Field(..., min_length=1, description="Street / physical address")
    city: str = Field(default="Bangalore", description="City / municipality")
    district: str = Field(default="Urban", description="Administrative district")
    state: str = Field(default="Karnataka", description="State / Province")
    country: str = Field(default="India", description="Country")
    postal_code: str = Field(default="560001", description="Postal code")
    zone: Optional[str] = Field(default="Central", description="Emergency response zone")


class HealthcareCapabilities(BaseModel):
    emergency_care: bool = Field(default=True, description="24/7 Emergency response capability")
    trauma_care: bool = Field(default=False, description="Specialized trauma stabilization & surgery")
    icu: bool = Field(default=False, description="Intensive Care Unit capability")
    surgery: bool = Field(default=False, description="Operating theater / surgical suite")
    oxygen_support: bool = Field(default=True, description="Dedicated piped / cylinder medical oxygen")
    ventilator_support: bool = Field(default=False, description="Mechanical ventilator support")
    ambulance_support: bool = Field(default=False, description="Dedicated BLS/ALS ambulances on-site")
    pediatric_care: bool = Field(default=False, description="Specialized pediatric / neonatal care")
    burn_unit: bool = Field(default=False, description="Specialized burn treatment unit")
    other_capabilities: List[str] = Field(default_factory=list, description="Other medical capabilities")


class HealthcareFacilityCreate(BaseModel):
    facility_name: str = Field(..., min_length=2, max_length=200, description="Official facility name")
    facility_type: HealthcareFacilityType = Field(default=HealthcareFacilityType.HOSPITAL)
    location: HealthcareLocation
    
    # Bed Capacities
    total_beds: int = Field(..., ge=0, description="Total general hospital beds")
    occupied_beds: int = Field(default=0, ge=0, description="Currently occupied general beds")
    
    # ICU Capacities
    total_icu_beds: int = Field(default=0, ge=0, description="Total ICU beds")
    occupied_icu_beds: int = Field(default=0, ge=0, description="Currently occupied ICU beds")
    
    # Emergency Capacities
    total_emergency_beds: int = Field(default=0, ge=0, description="Total emergency triage beds")
    occupied_emergency_beds: int = Field(default=0, ge=0, description="Currently occupied emergency triage beds")
    
    # Other Capacities
    ventilators_total: int = Field(default=0, ge=0, description="Total mechanical ventilators")
    ventilators_available: Optional[int] = Field(default=None, ge=0, description="Available mechanical ventilators")
    oxygen_supported_beds: int = Field(default=0, ge=0, description="Total beds with direct oxygen supply")
    oxygen_available_capacity: Optional[int] = Field(default=None, ge=0, description="Available oxygen-supported beds")
    
    # Capabilities & Status
    capabilities: HealthcareCapabilities = Field(default_factory=HealthcareCapabilities)
    status: HealthcareOperationalStatus = Field(default=HealthcareOperationalStatus.ACTIVE)
    condition: str = Field(default="EXCELLENT", description="Facility physical condition (EXCELLENT, GOOD, FAIR, DAMAGED)")
    accessibility: str = Field(default="FULLY_ACCESSIBLE", description="Road / transport accessibility")
    contact_phone: Optional[str] = Field(default=None, description="Direct emergency desk phone")
    contact_email: Optional[str] = Field(default=None, description="Administrative contact email")
    operating_hours: str = Field(default="24/7", description="Operating hours")

    @model_validator(mode="after")
    def validate_capacities(self):
        if self.occupied_beds > self.total_beds:
            raise ValueError(f"occupied_beds ({self.occupied_beds}) cannot exceed total_beds ({self.total_beds})")
        if self.occupied_icu_beds > self.total_icu_beds:
            raise ValueError(f"occupied_icu_beds ({self.occupied_icu_beds}) cannot exceed total_icu_beds ({self.total_icu_beds})")
        if self.occupied_emergency_beds > self.total_emergency_beds:
            raise ValueError(f"occupied_emergency_beds ({self.occupied_emergency_beds}) cannot exceed total_emergency_beds ({self.total_emergency_beds})")
        
        # Ventilators available default
        if self.ventilators_available is None:
            self.ventilators_available = self.ventilators_total
        elif self.ventilators_available > self.ventilators_total:
            raise ValueError(f"ventilators_available ({self.ventilators_available}) cannot exceed ventilators_total ({self.ventilators_total})")
            
        # Oxygen available default
        if self.oxygen_available_capacity is None:
            self.oxygen_available_capacity = self.oxygen_supported_beds
        elif self.oxygen_available_capacity > self.oxygen_supported_beds:
            raise ValueError(f"oxygen_available_capacity ({self.oxygen_available_capacity}) cannot exceed oxygen_supported_beds ({self.oxygen_supported_beds})")
            
        return self


class HealthcareCapacityUpdate(BaseModel):
    occupied_beds: Optional[int] = Field(default=None, ge=0, description="Updated occupied general beds")
    occupied_icu_beds: Optional[int] = Field(default=None, ge=0, description="Updated occupied ICU beds")
    occupied_emergency_beds: Optional[int] = Field(default=None, ge=0, description="Updated occupied emergency beds")
    ventilators_available: Optional[int] = Field(default=None, ge=0, description="Updated available ventilators")
    oxygen_available_capacity: Optional[int] = Field(default=None, ge=0, description="Updated available oxygen capacity")
    reason: Optional[str] = Field(default=None, description="Reason for capacity adjustment")


class HealthcareFacilityUpdate(BaseModel):
    facility_name: Optional[str] = Field(default=None, min_length=2, max_length=200)
    facility_type: Optional[HealthcareFacilityType] = None
    location: Optional[HealthcareLocation] = None
    total_beds: Optional[int] = Field(default=None, ge=0)
    occupied_beds: Optional[int] = Field(default=None, ge=0)
    total_icu_beds: Optional[int] = Field(default=None, ge=0)
    occupied_icu_beds: Optional[int] = Field(default=None, ge=0)
    total_emergency_beds: Optional[int] = Field(default=None, ge=0)
    occupied_emergency_beds: Optional[int] = Field(default=None, ge=0)
    ventilators_total: Optional[int] = Field(default=None, ge=0)
    ventilators_available: Optional[int] = Field(default=None, ge=0)
    oxygen_supported_beds: Optional[int] = Field(default=None, ge=0)
    oxygen_available_capacity: Optional[int] = Field(default=None, ge=0)
    capabilities: Optional[HealthcareCapabilities] = None
    status: Optional[HealthcareOperationalStatus] = None
    condition: Optional[str] = None
    accessibility: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    operating_hours: Optional[str] = None


class HealthcareFacilityResponse(BaseModel):
    id: str = Field(alias="_id")
    facility_id: str
    facility_name: str
    facility_type: HealthcareFacilityType
    location: HealthcareLocation
    
    # General Beds
    total_beds: int
    occupied_beds: int
    available_beds: int
    bed_occupancy_rate: float
    
    # ICU
    total_icu_beds: int
    occupied_icu_beds: int
    available_icu_beds: int
    icu_occupancy_rate: float
    
    # Emergency
    total_emergency_beds: int
    occupied_emergency_beds: int
    available_emergency_beds: int
    emergency_occupancy_rate: float
    
    # Other Capacities
    ventilators_total: int
    ventilators_available: int
    oxygen_supported_beds: int
    oxygen_available_capacity: int
    
    # Capabilities & Status
    capabilities: HealthcareCapabilities
    status: HealthcareOperationalStatus
    condition: str
    accessibility: str
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    operating_hours: str
    
    # Audit & Timestamps
    created_by_id: Optional[str] = None
    created_by_name: Optional[str] = None
    last_updated_by_id: Optional[str] = None
    last_updated_by_name: Optional[str] = None
    last_updated: datetime
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(populate_by_name=True)


class PaginatedHealthcareFacilitiesResponse(BaseModel):
    items: List[HealthcareFacilityResponse]
    total_count: int
    page: int
    limit: int
    total_pages: int


class HealthcareStatsResponse(BaseModel):
    total_facilities: int = 0
    active_facilities: int = 0
    total_available_beds: int = 0
    total_occupied_beds: int = 0
    total_beds: int = 0
    available_icu_beds: int = 0
    total_icu_beds: int = 0
    available_emergency_beds: int = 0
    total_emergency_beds: int = 0
    available_ventilators: int = 0
    total_ventilators: int = 0
    available_oxygen_capacity: int = 0
    total_oxygen_supported_beds: int = 0
    overall_bed_utilization: float = 0.0
    overall_icu_utilization: float = 0.0
