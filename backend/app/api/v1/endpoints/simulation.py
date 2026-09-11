import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.mongodb import get_database
from app.api.deps import require_officer
from app.models.user import UserResponse
from app.models.simulation import (
    SimulationRun,
    SimulationScenario,
    CreateSimulationRequest,
    AddScenarioRequest,
    SimulationTargetLookupResponse,
    RunSimulationResponse,
)
from app.models.monitoring import PlanDiffResult
from app.services.monitoring.simulation_service import SimulationService

logger = logging.getLogger("resilience.api.simulation")
router = APIRouter()


@router.post(
    "",
    response_model=SimulationRun,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new draft what-if simulation",
)
async def create_simulation(
    payload: CreateSimulationRequest,
    current_user: UserResponse = Depends(require_officer),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    actor_dict = {
        "id": current_user.id,
        "full_name": current_user.full_name,
        "role": current_user.role.value,
    }
    try:
        return await SimulationService.create_simulation(
            situation_id=payload.situation_id,
            name=payload.simulation_name,
            officer_actor=actor_dict,
            db=db,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "",
    response_model=List[SimulationRun],
    summary="List previous simulation runs",
)
async def list_simulations(
    situation_id: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
    current_user: UserResponse = Depends(require_officer),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    query = {}
    if situation_id:
        query["situation_id"] = situation_id.strip().upper()
    if status_filter:
        query["status"] = status_filter.strip().upper()

    cursor = db["simulations"].find(query).sort("created_at", -1).limit(limit)
    raw_sims = await cursor.to_list(length=limit)

    results = []
    for s in raw_sims:
        # Check staleness on read
        sim_obj = SimulationRun(**s)
        if sim_obj.status == "COMPLETED":
            is_stale, _ = await SimulationService.check_simulation_stale(sim_obj.simulation_id, db)
            if is_stale:
                sim_obj.status = "STALE"
        results.append(sim_obj)

    return results


@router.get(
    "/targets/{situation_id}",
    response_model=SimulationTargetLookupResponse,
    summary="Get real operational entities for scenario builder (zero dummy data)",
)
async def get_simulation_targets(
    situation_id: str,
    current_user: UserResponse = Depends(require_officer),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    try:
        return await SimulationService.get_target_entities(situation_id=situation_id, db=db)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.get(
    "/{simulation_id}",
    response_model=SimulationRun,
    summary="Get simulation details",
)
async def get_simulation_details(
    simulation_id: str,
    current_user: UserResponse = Depends(require_officer),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    sim_doc = await db["simulations"].find_one({"simulation_id": simulation_id})
    if not sim_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Simulation '{simulation_id}' not found.",
        )

    sim_obj = SimulationRun(**sim_doc)
    if sim_obj.status == "COMPLETED":
        is_stale, _ = await SimulationService.check_simulation_stale(simulation_id, db)
        if is_stale:
            sim_obj.status = "STALE"

    return sim_obj


@router.post(
    "/{simulation_id}/scenarios",
    response_model=SimulationScenario,
    status_code=status.HTTP_201_CREATED,
    summary="Add a what-if scenario to a draft simulation",
)
async def add_scenario(
    simulation_id: str,
    payload: AddScenarioRequest,
    current_user: UserResponse = Depends(require_officer),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    actor_dict = {
        "id": current_user.id,
        "full_name": current_user.full_name,
        "role": current_user.role.value,
    }
    try:
        return await SimulationService.add_scenario(
            simulation_id=simulation_id,
            payload=payload,
            officer_actor=actor_dict,
            db=db,
        )
    except ValueError as e:
        err_msg = str(e)
        if "SCENARIO_CONFLICT" in err_msg:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=err_msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err_msg)


@router.delete(
    "/{simulation_id}/scenarios/{scenario_id}",
    summary="Remove a scenario from a draft simulation",
)
async def remove_scenario(
    simulation_id: str,
    scenario_id: str,
    current_user: UserResponse = Depends(require_officer),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    actor_dict = {
        "id": current_user.id,
        "full_name": current_user.full_name,
        "role": current_user.role.value,
    }
    success = await SimulationService.remove_scenario(
        simulation_id=simulation_id,
        scenario_id=scenario_id,
        officer_actor=actor_dict,
        db=db,
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scenario '{scenario_id}' not found in simulation '{simulation_id}'.",
        )
    return {"success": True, "message": f"Scenario {scenario_id} removed."}


@router.post(
    "/{simulation_id}/run",
    response_model=RunSimulationResponse,
    summary="Execute isolated what-if simulation with zero DB mutation",
)
async def run_simulation(
    simulation_id: str,
    current_user: UserResponse = Depends(require_officer),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    actor_dict = {
        "id": current_user.id,
        "full_name": current_user.full_name,
        "role": current_user.role.value,
    }
    try:
        return await SimulationService.run_simulation(
            simulation_id=simulation_id,
            officer_actor=actor_dict,
            db=db,
        )
    except ValueError as e:
        err_msg = str(e)
        if "SIMULATION_BASELINE_STALE" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=err_msg,
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=err_msg,
        )


@router.get(
    "/{simulation_id}/diff",
    response_model=PlanDiffResult,
    summary="Get simulated vs baseline plan diff",
)
async def get_simulation_diff(
    simulation_id: str,
    current_user: UserResponse = Depends(require_officer),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    sim_doc = await db["simulations"].find_one({"simulation_id": simulation_id})
    if not sim_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Simulation '{simulation_id}' not found.",
        )

    diff_doc = sim_doc.get("diff_result")
    if not diff_doc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Simulation has not been run yet. Run the simulation to generate a plan diff.",
        )

    return PlanDiffResult(**diff_doc)


@router.post(
    "/{simulation_id}/discard",
    summary="Discard a simulation run",
)
async def discard_simulation(
    simulation_id: str,
    current_user: UserResponse = Depends(require_officer),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    actor_dict = {
        "id": current_user.id,
        "full_name": current_user.full_name,
        "role": current_user.role.value,
    }
    success = await SimulationService.discard_simulation(
        simulation_id=simulation_id,
        officer_actor=actor_dict,
        db=db,
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Simulation '{simulation_id}' not found.",
        )
    return {"success": True, "message": f"Simulation {simulation_id} discarded."}
