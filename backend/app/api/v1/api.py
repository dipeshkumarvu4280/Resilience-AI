from fastapi import APIRouter
from app.api.v1.endpoints import auth, system, users, citizen, officer, resources, needs_allocations, situations, monitoring, simulation, notifications, field_operations, analytics, healthcare, map, sensors, safety_guidance

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Authentication & Security"])
api_router.include_router(system.router, prefix="/system", tags=["System Telemetry & Health"])
api_router.include_router(users.router, prefix="/users", tags=["Operator & User Management"])
api_router.include_router(citizen.router, prefix="/citizen", tags=["Citizen Emergency Reporting"])
api_router.include_router(safety_guidance.router, prefix="/citizen", tags=["Live Citizen Safety Guidance & Web Push"])
api_router.include_router(safety_guidance.router, prefix="", tags=["Live Citizen Safety Guidance & Web Push"])
api_router.include_router(officer.router, prefix="/officer", tags=["Emergency Operations & Situation Awareness"])

api_router.include_router(map.router, prefix="/map", tags=["Geospatial GIS & Active Hotspots"])
api_router.include_router(map.router, prefix="/citizen/map", tags=["Geospatial GIS & Active Hotspots"])
api_router.include_router(map.router, prefix="/public/map", tags=["Geospatial GIS & Active Hotspots"])
api_router.include_router(resources.router, prefix="/resources", tags=["Resource & Logistics Inventory"])
api_router.include_router(healthcare.router, prefix="/healthcare", tags=["Healthcare & Hospital Capacity Management"])
api_router.include_router(healthcare.router, prefix="/officer/healthcare", tags=["Healthcare & Hospital Capacity Management"])
api_router.include_router(needs_allocations.router, prefix="/officer", tags=["Needs Assessment & Resource Allocation"])
api_router.include_router(needs_allocations.router, prefix="/needs", tags=["Needs Assessment & Resource Allocation"])
api_router.include_router(situations.router, prefix="/officer/situations", tags=["Situation Intelligence & Incident Fusion"])
api_router.include_router(monitoring.router, prefix="/officer/monitoring", tags=["Live Monitoring & Change Impact Analysis"])
api_router.include_router(simulation.router, prefix="/officer/simulations", tags=["Simulation & What-If Scenario Engine"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["Notifications & Alerts Engine"])
api_router.include_router(field_operations.router, prefix="/field-operations", tags=["Field Operations & Response Coordination"])
api_router.include_router(field_operations.router, prefix="/officer/field-operations", tags=["Field Operations & Response Coordination"])
api_router.include_router(field_operations.router, prefix="/field", tags=["Field Operations & Response Coordination"])
api_router.include_router(analytics.router, prefix="/officer/analytics", tags=["Emergency Intelligence & Analytics"])
api_router.include_router(analytics.router, prefix="/admin/analytics", tags=["Emergency Intelligence & Analytics"])
api_router.include_router(sensors.router, prefix="/sensors", tags=["IoT Sensor Intake & Real-Time Monitoring"])
api_router.include_router(sensors.router, prefix="/officer/sensors", tags=["IoT Sensor Intake & Real-Time Monitoring"])






