import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.enums import (
    ResourceType,
    ResourceStatus,
    ResourceCondition,
    NeedUrgency,
    SeverityLevel,
    BottleneckType,
    BottleneckSeverity,
    AllocationStatus,
    ResponseTaskStatus,
)
from app.models.resource import (
    ResourceBottleneckItem,
    ResourceBottleneckSummary,
    ResourceBottlenecksResponse,
    AffectedSituationRef,
    AffectedTaskRef,
    ContentionDetail,
    AlternativeResourceOption,
    generate_bottleneck_id,
)
from app.services.resource_matching import haversine_distance_km

logger = logging.getLogger("resilience.resource_bottleneck_service")


class ResourceBottleneckService:
    """
    Deterministic Resource Bottleneck Intelligence Engine (Phase D).
    Computes operational capacity bottlenecks, shortfalls, and multi-incident contention
    from authoritative Needs Assessments, actual Inventory, Allocations, and Task Consumption.

    SAFETY & INTEGRITY PRINCIPLES:
    - Zero dummy/synthetic data. All metrics derived from genuine MongoDB records.
    - Needs Assessments remain authoritative and are NEVER mutated.
    - Inventory is NEVER automatically consumed or reallocated by analysis.
    - Human-in-the-Loop: all findings and recommendations are advisory for Emergency Officers.
    """

    async def analyze_bottlenecks(
        self,
        db: AsyncIOMotorDatabase,
        situation_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        severity: Optional[str] = None,
        zone: Optional[str] = None,
        page: int = 1,
        limit: int = 50,
    ) -> ResourceBottlenecksResponse:
        """
        Executes deterministic multi-domain bottleneck analysis across active situations,
        authoritative needs assessments, physical inventory, allocations, and field task consumption.
        """
        now = datetime.now(timezone.utc)

        # 1. Fetch all active situations
        sit_query: Dict[str, Any] = {
            "status": {"$nin": ["RESOLVED", "CLOSED"]}
        }
        if situation_id:
            sit_query["situation_id"] = situation_id.strip().upper()

        situations_cursor = db["situations"].find(sit_query)
        situations = await situations_cursor.to_list(length=200)
        situation_map = {s["situation_id"]: s for s in situations}

        # 2. Fetch all genuine Needs Assessments for active situations / reports
        needs_by_type: Dict[str, List[Dict[str, Any]]] = {}
        all_needs_docs = await db["needs_assessments"].find({}).to_list(length=500)

        # Map reports to situations
        report_to_situation: Dict[str, str] = {}
        for s in situations:
            for rep_id in s.get("report_ids", []):
                report_to_situation[rep_id] = s["situation_id"]
            if s.get("primary_report_id"):
                report_to_situation[s["primary_report_id"]] = s["situation_id"]

        for nd in all_needs_docs:
            rep_id = nd.get("report_id")
            sit_id = nd.get("situation_id") or report_to_situation.get(rep_id) or "GENERAL"
            if situation_id and sit_id != situation_id:
                continue

            sit_info = situation_map.get(sit_id) if sit_id else None
            
            # Extract items from nested list or root document
            items_to_process = []
            if isinstance(nd.get("needs"), list) and len(nd["needs"]) > 0:
                items_to_process.extend(nd["needs"])
            elif nd.get("resource_type"):
                items_to_process.append(nd)

            for item in items_to_process:
                r_type = item.get("resource_type")
                if not r_type:
                    continue
                r_type_key = str(r_type).upper()
                if r_type_key not in needs_by_type:
                    needs_by_type[r_type_key] = []
                needs_by_type[r_type_key].append({
                    "need_id": item.get("need_id", item.get("assessment_id", f"NED-{sit_id[-4:]}")),
                    "situation_id": sit_id or "GENERAL",
                    "situation_title": sit_info.get("title", f"Situation {sit_id}") if sit_info else "Emergency Response",
                    "emergency_type": sit_info.get("emergency_type") if sit_info else None,
                    "severity_level": sit_info.get("severity_level") if sit_info else "HIGH",
                    "requested_quantity": float(item.get("requested_quantity", 0.0)),
                    "unit": item.get("unit", "units"),
                    "urgency": item.get("urgency", NeedUrgency.HIGH.value),
                    "reason": item.get("reason"),
                })

        # Also check active Coordination Plans for assessed needs if explicit NeedsAssessment document not created
        plans_cursor = db["coordination_plans"].find({
            "status": {"$in": ["ACTIVE", "APPROVED", "PENDING_OFFICER_REVIEW"]}
        })
        active_plans = await plans_cursor.to_list(length=100)
        for pl in active_plans:
            pl_sit_id = pl.get("situation_id")
            if pl_sit_id in situation_map and (not situation_id or pl_sit_id == situation_id):
                sit_info = situation_map[pl_sit_id]
                for n_item in pl.get("assessed_needs", []):
                    r_type = n_item.get("resource_type")
                    if not r_type:
                        continue
                    r_type_key = str(r_type).upper()
                    already_tracked = any(
                        x["situation_id"] == pl_sit_id and x.get("need_id") == n_item.get("need_id")
                        for x in needs_by_type.get(r_type_key, [])
                    )
                    if not already_tracked:
                        if r_type_key not in needs_by_type:
                            needs_by_type[r_type_key] = []
                        qty = float(n_item.get("quantity", n_item.get("requested_quantity", 0.0)))
                        needs_by_type[r_type_key].append({
                            "need_id": n_item.get("need_id", f"PLAN-NEED-{pl_sit_id[-4:]}"),
                            "situation_id": pl_sit_id,
                            "situation_title": sit_info.get("title", f"Situation {pl_sit_id}"),
                            "emergency_type": sit_info.get("emergency_type"),
                            "severity_level": sit_info.get("severity_level", "HIGH"),
                            "requested_quantity": qty,
                            "unit": n_item.get("unit", "units"),
                            "urgency": n_item.get("urgency", NeedUrgency.HIGH.value),
                            "reason": n_item.get("reasoning") or "Coordinated response requirement",
                        })

        # 3. Fetch genuine Inventory from resources collection
        res_cursor = db["resources"].find({})
        all_resources = await res_cursor.to_list(length=500)
        resources_by_type: Dict[str, List[Dict[str, Any]]] = {}
        for r in all_resources:
            r_type_key = str(r.get("resource_type", "")).upper()
            if r_type_key not in resources_by_type:
                resources_by_type[r_type_key] = []
            resources_by_type[r_type_key].append(r)

        # 4. Fetch Allocations
        alloc_cursor = db["allocations"].find({
            "status": {"$in": [AllocationStatus.PROPOSED.value, AllocationStatus.APPROVED.value, AllocationStatus.DISPATCHED.value]}
        })
        all_allocations = await alloc_cursor.to_list(length=500)
        allocations_by_type: Dict[str, float] = {}
        for a in all_allocations:
            r_type_key = str(a.get("resource_type", "")).upper()
            qty = float(a.get("approved_quantity") or a.get("requested_quantity") or 0.0)
            allocations_by_type[r_type_key] = allocations_by_type.get(r_type_key, 0.0) + qty

        # 5. Fetch actual Task Consumption from response_tasks
        tasks_cursor = db["response_tasks"].find({
            "status": {"$in": [ResponseTaskStatus.IN_PROGRESS.value, ResponseTaskStatus.COMPLETED.value, ResponseTaskStatus.BLOCKED.value, ResponseTaskStatus.ASSIGNED.value, ResponseTaskStatus.ACCEPTED.value]}
        })
        all_tasks = await tasks_cursor.to_list(length=500)
        tasks_by_type: Dict[str, List[Dict[str, Any]]] = {}
        consumption_by_type: Dict[str, float] = {}
        for t in all_tasks:
            for asg_res in t.get("assigned_resources", []):
                r_type_key = str(asg_res.get("resource_type", "")).upper()
                if r_type_key not in tasks_by_type:
                    tasks_by_type[r_type_key] = []
                tasks_by_type[r_type_key].append({
                    "task_id": t.get("task_id"),
                    "situation_id": t.get("situation_id"),
                    "title": t.get("title", "Field Task"),
                    "status": t.get("status"),
                    "allocated_quantity": float(asg_res.get("allocated_quantity", 0.0)),
                    "consumed_quantity": float(asg_res.get("consumed_quantity", 0.0)),
                })
                consumption_by_type[r_type_key] = consumption_by_type.get(r_type_key, 0.0) + float(asg_res.get("consumed_quantity", 0.0))

        # 6. Deterministically evaluate Bottlenecks
        bottlenecks: List[ResourceBottleneckItem] = []

        all_eval_types = set(list(needs_by_type.keys()) + list(resources_by_type.keys()))
        if resource_type and resource_type.upper() != "ALL":
            all_eval_types = {resource_type.upper()}

        for r_type_key in all_eval_types:
            demand_items = needs_by_type.get(r_type_key, [])
            total_required = sum(d["requested_quantity"] for d in demand_items)

            inventory_items = resources_by_type.get(r_type_key, [])
            usable_inventory = [
                r for r in inventory_items
                if r.get("status") in [ResourceStatus.AVAILABLE.value, ResourceStatus.PARTIALLY_AVAILABLE.value]
                and r.get("condition") != ResourceCondition.DAMAGED.value
            ]
            total_available = sum(float(r.get("quantity_available", 0.0)) for r in usable_inventory)

            total_allocated = allocations_by_type.get(r_type_key, 0.0)
            total_consumed = consumption_by_type.get(r_type_key, 0.0)

            primary_unit = demand_items[0]["unit"] if demand_items else (inventory_items[0].get("unit", "units") if inventory_items else "units")

            # Condition 1: No registered resources for an authoritative need
            if total_required > 0 and len(inventory_items) == 0:
                shortfall = total_required
                affected_sits = [
                    AffectedSituationRef(
                        situation_id=d["situation_id"],
                        title=d["situation_title"],
                        emergency_type=d.get("emergency_type"),
                        required_quantity=d["requested_quantity"],
                        urgency=NeedUrgency(d["urgency"]) if d["urgency"] in NeedUrgency._value2member_map_ else NeedUrgency.HIGH,
                        severity_level=d.get("severity_level"),
                    )
                    for d in demand_items
                ]
                affected_tsks = [
                    AffectedTaskRef(
                        task_id=t["task_id"],
                        situation_id=t["situation_id"],
                        title=t["title"],
                        status=t["status"],
                        allocated_quantity=t["allocated_quantity"],
                        consumed_quantity=t["consumed_quantity"],
                    )
                    for t in tasks_by_type.get(r_type_key, [])
                ]

                alternatives = self._find_genuine_alternatives(r_type_key, all_resources)

                item = ResourceBottleneckItem(
                    bottleneck_id=generate_bottleneck_id(),
                    resource_type=self._safe_resource_type(r_type_key),
                    resource_name=f"Emergency {r_type_key.title()}",
                    severity=BottleneckSeverity.CRITICAL if any(d.get("urgency") == "CRITICAL" for d in demand_items) else BottleneckSeverity.HIGH,
                    bottleneck_type=BottleneckType.NO_ELIGIBLE_RESOURCE,
                    required=round(total_required, 2),
                    available=0.0,
                    allocated=round(total_allocated, 2),
                    consumed=round(total_consumed, 2),
                    shortfall=round(shortfall, 2),
                    unit=primary_unit,
                    affected_situations=affected_sits,
                    affected_tasks=affected_tsks,
                    alternative_options=alternatives,
                    why_bottleneck=f"0 units of {r_type_key.title()} are registered in inventory, but {total_required:g} {primary_unit} are required by {len(affected_sits)} active situation(s).",
                    recommended_action="Initiate emergency procurement or check regional depot mutual aid agreements.",
                    supporting_records={"demand_count": len(demand_items), "inventory_count": 0},
                    generated_at=now,
                )
                bottlenecks.append(item)
                continue

            # Condition 2: Shortfall (Demand > Usable Supply)
            if total_required > total_available:
                shortfall = total_required - total_available
                affected_sits = [
                    AffectedSituationRef(
                        situation_id=d["situation_id"],
                        title=d["situation_title"],
                        emergency_type=d.get("emergency_type"),
                        required_quantity=d["requested_quantity"],
                        urgency=NeedUrgency(d["urgency"]) if d["urgency"] in NeedUrgency._value2member_map_ else NeedUrgency.HIGH,
                        severity_level=d.get("severity_level"),
                    )
                    for d in demand_items
                ]
                affected_tsks = [
                    AffectedTaskRef(
                        task_id=t["task_id"],
                        situation_id=t["situation_id"],
                        title=t["title"],
                        status=t["status"],
                        allocated_quantity=t["allocated_quantity"],
                        consumed_quantity=t["consumed_quantity"],
                    )
                    for t in tasks_by_type.get(r_type_key, [])
                ]

                # Detect Multi-Incident Contention
                distinct_sits = list({d["situation_id"] for d in demand_items})
                contention_detail: Optional[ContentionDetail] = None
                b_type = BottleneckType.RESOURCE_SHORTAGE

                if len(distinct_sits) > 1 and total_available < total_required:
                    b_type = BottleneckType.ALLOCATION_CONTENTION
                    contention_detail = ContentionDetail(
                        total_demand=round(total_required, 2),
                        eligible_supply=round(total_available, 2),
                        contention_deficit=round(shortfall, 2),
                        competing_situations=[
                            {
                                "situation_id": sid,
                                "title": situation_map.get(sid, {}).get("title", sid),
                                "demanded": sum(d["requested_quantity"] for d in demand_items if d["situation_id"] == sid),
                            }
                            for sid in distinct_sits
                        ],
                    )

                # Severity calculation
                shortfall_ratio = shortfall / total_required if total_required > 0 else 1.0
                has_critical_urgency = any(d.get("urgency") == NeedUrgency.CRITICAL.value for d in demand_items)
                has_critical_situation = any(situation_map.get(d["situation_id"], {}).get("severity_level") == "CRITICAL" for d in demand_items)

                if has_critical_urgency or (shortfall_ratio >= 0.5 and has_critical_situation):
                    sev = BottleneckSeverity.CRITICAL
                elif shortfall_ratio >= 0.25 or len(distinct_sits) > 1:
                    sev = BottleneckSeverity.HIGH
                else:
                    sev = BottleneckSeverity.MEDIUM

                alternatives = self._find_genuine_alternatives(r_type_key, all_resources)

                explanation = (
                    f"Authoritative demand of {total_required:g} {primary_unit} exceeds available inventory of {total_available:g} {primary_unit} "
                    f"(deficit: {shortfall:g} {primary_unit}) across {len(distinct_sits)} active incident(s)."
                )

                item = ResourceBottleneckItem(
                    bottleneck_id=generate_bottleneck_id(),
                    resource_type=self._safe_resource_type(r_type_key),
                    resource_name=inventory_items[0].get("name") if inventory_items else f"Emergency {r_type_key.title()}",
                    severity=sev,
                    bottleneck_type=b_type,
                    required=round(total_required, 2),
                    available=round(total_available, 2),
                    allocated=round(total_allocated, 2),
                    consumed=round(total_consumed, 2),
                    shortfall=round(shortfall, 2),
                    unit=primary_unit,
                    affected_situations=affected_sits,
                    affected_tasks=affected_tsks,
                    contention=contention_detail,
                    alternative_options=alternatives,
                    why_bottleneck=explanation,
                    recommended_action="Execute priority-first partial allocation to high-urgency incidents and dispatch replenishment." if len(distinct_sits) > 1 else "Reallocate from standby reserves or request external mutual aid.",
                    supporting_records={
                        "demands": len(demand_items),
                        "warehouses": len(usable_inventory),
                        "total_inventory_records": len(inventory_items),
                    },
                    generated_at=now,
                )
                bottlenecks.append(item)
                continue

            # Condition 3: Damaged or Unavailable Inventory constraint
            damaged_items = [r for r in inventory_items if r.get("condition") == ResourceCondition.DAMAGED.value or r.get("status") == ResourceStatus.UNAVAILABLE.value]
            damaged_qty = sum(float(r.get("quantity_total", 0.0)) for r in damaged_items)
            if damaged_qty > 0 and total_required > 0 and total_available < (total_required + damaged_qty):
                affected_sits = [
                    AffectedSituationRef(
                        situation_id=d["situation_id"],
                        title=d["situation_title"],
                        emergency_type=d.get("emergency_type"),
                        required_quantity=d["requested_quantity"],
                        urgency=NeedUrgency(d["urgency"]) if d["urgency"] in NeedUrgency._value2member_map_ else NeedUrgency.HIGH,
                        severity_level=d.get("severity_level"),
                    )
                    for d in demand_items
                ]
                item = ResourceBottleneckItem(
                    bottleneck_id=generate_bottleneck_id(),
                    resource_type=self._safe_resource_type(r_type_key),
                    resource_name=inventory_items[0].get("name") if inventory_items else f"Emergency {r_type_key.title()}",
                    severity=BottleneckSeverity.MEDIUM,
                    bottleneck_type=BottleneckType.CAPABILITY_CONSTRAINT,
                    required=round(total_required, 2),
                    available=round(total_available, 2),
                    allocated=round(total_allocated, 2),
                    consumed=round(total_consumed, 2),
                    shortfall=0.0,
                    unit=primary_unit,
                    affected_situations=affected_sits,
                    affected_tasks=[],
                    alternative_options=[],
                    why_bottleneck=f"{damaged_qty:g} {primary_unit} of {r_type_key.title()} are unusable due to DAMAGED condition or UNAVAILABLE status, constraining buffer capacity.",
                    recommended_action="Schedule maintenance/replacement of damaged stockpile items.",
                    supporting_records={"damaged_items_count": len(damaged_items), "damaged_quantity": damaged_qty},
                    generated_at=now,
                )
                bottlenecks.append(item)

        # Apply Severity filter if specified
        if severity and severity.upper() != "ALL":
            target_sev = severity.upper()
            bottlenecks = [b for b in bottlenecks if b.severity.value == target_sev]

        # Calculate summary metrics
        total_btn = len(bottlenecks)
        critical_c = sum(1 for b in bottlenecks if b.severity == BottleneckSeverity.CRITICAL)
        high_c = sum(1 for b in bottlenecks if b.severity == BottleneckSeverity.HIGH)
        med_c = sum(1 for b in bottlenecks if b.severity == BottleneckSeverity.MEDIUM)
        low_c = sum(1 for b in bottlenecks if b.severity == BottleneckSeverity.LOW)
        contention_c = sum(1 for b in bottlenecks if b.bottleneck_type == BottleneckType.ALLOCATION_CONTENTION)

        shortfall_by_type: Dict[str, float] = {}
        affected_sits_set = set()
        for b in bottlenecks:
            if b.shortfall > 0:
                shortfall_by_type[b.resource_type.value] = shortfall_by_type.get(b.resource_type.value, 0.0) + b.shortfall
            for s in b.affected_situations:
                affected_sits_set.add(s.situation_id)

        # Pagination
        total_pages = max(1, (total_btn + limit - 1) // limit)
        skip = (page - 1) * limit
        paginated_items = bottlenecks[skip : skip + limit]

        summary = ResourceBottleneckSummary(
            total_bottlenecks=total_btn,
            critical_count=critical_c,
            high_count=high_c,
            medium_count=med_c,
            low_count=low_c,
            total_shortfall_by_type=shortfall_by_type,
            affected_situations_count=len(affected_sits_set),
            contention_count=contention_c,
            generated_at=now,
        )

        return ResourceBottlenecksResponse(
            summary=summary,
            items=paginated_items,
            total=total_btn,
            page=page,
            limit=limit,
            total_pages=total_pages,
        )

    def _find_genuine_alternatives(
        self,
        target_type_key: str,
        all_resources: List[Dict[str, Any]],
    ) -> List[AlternativeResourceOption]:
        """
        Discovers genuine alternative supplies from the database without fabricating records.
        """
        alternatives: List[AlternativeResourceOption] = []
        target_type = target_type_key.upper()

        alternative_types: List[str] = []
        if target_type == "WATER":
            alternative_types = ["FOOD", "RATIONS"]
        elif target_type in ["MEDICINE", "FIRST_AID"]:
            alternative_types = ["FIRST_AID", "MEDICAL_EQUIPMENT", "MEDICINE"]
        elif target_type == "BLANKETS":
            alternative_types = ["CLOTHING", "SHELTER"]
        elif target_type == "GENERATOR":
            alternative_types = ["FUEL"]

        for r in all_resources:
            r_type = str(r.get("resource_type", "")).upper()
            avail = float(r.get("quantity_available", 0.0))
            if r_type in alternative_types and r_type != target_type and avail > 0:
                loc = r.get("location") or {}
                alternatives.append(AlternativeResourceOption(
                    resource_id=r["resource_id"],
                    name=r.get("name", "Alternative Asset"),
                    resource_type=self._safe_resource_type(r_type),
                    quantity_available=avail,
                    unit=r.get("unit", "units"),
                    location_name=loc.get("address") or r.get("location_name") or "Depot",
                    feasibility_notes=f"Usable complementary stockpile item ({avail:g} {r.get('unit', 'units')} available).",
                ))
            if len(alternatives) >= 3:
                break

        return alternatives

    def _safe_resource_type(self, val: Any) -> ResourceType:
        if isinstance(val, ResourceType):
            return val
        try:
            return ResourceType(val)
        except Exception:
            if isinstance(val, str):
                v_lower = val.strip().lower()
                for member in ResourceType:
                    if member.value.lower() == v_lower or member.name.lower() == v_lower:
                        return member
            return ResourceType.OTHER


resource_bottleneck_service = ResourceBottleneckService()
