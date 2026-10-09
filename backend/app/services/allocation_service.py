"""Allocation Orchestration Service for ClassroomIQ.

Coordinates data loading, baseline allocation generation, and independent validation.
Maintains strict separation between solver proposals and independent validation findings.
Keeps working snapshots completely separate from immutable source datasets.
"""

import time
from typing import Dict, List, Optional, Any

from backend.app.config import CapacityPolicyMode
from backend.app.schemas.models import DatasetSnapshot, Session
from backend.app.schemas.validation import (
    AllocationCandidate,
    AllocationResult,
    ValidationSummary,
)
from backend.app.services.data_loader import DataLoaderService
from backend.app.core.baseline_allocator import BaselineGreedyAllocator
from backend.app.core.validator import IndependentValidator
from backend.app.core.optimizer import CPSATRoomOptimizer
from backend.app.core.metrics import MetricsCalculator, AllocationMetrics, MetricComparison
from backend.app.core.simulation_engine import SimulationEngine, DisruptionSimulationResult


class AllocationService:
    """Orchestrates candidate room allocation and independent validation."""

    def __init__(self, snapshot: Optional[DatasetSnapshot] = None):
        """Initializes the service with a dataset snapshot.
        
        Args:
            snapshot: Optional pre-loaded DatasetSnapshot. If None, loads fresh snapshot.
        """
        self.snapshot = snapshot or DataLoaderService().load_snapshot()

    def validate_source_timetable(
        self,
        academic_cycle: str = "all",
        allow_computing_lab_exception: bool = False,
        capacity_mode: CapacityPolicyMode = CapacityPolicyMode.FACTUAL,
        synthetic_room_capacities: Optional[Dict[str, int]] = None,
        synthetic_session_demands: Optional[Dict[str, int]] = None,
    ) -> AllocationResult:
        """Evaluates the original source timetable assignments using the Independent Validator.
        
        Args:
            academic_cycle: 'odd', 'even', or 'all'.
            allow_computing_lab_exception: Whether to allow the 10 computing lab sessions.
            capacity_mode: Factual vs Synthetic mode.
            synthetic_room_capacities: Optional synthetic capacities.
            synthetic_session_demands: Optional synthetic demands.
            
        Returns:
            AllocationResult encapsulating source assignments and independent findings.
        """
        start_time = time.perf_counter()

        # Build candidate from source assigned_room_id
        if academic_cycle in ["odd", "even"]:
            target_sessions = [
                s for s in self.snapshot.sessions if s.academic_cycle == academic_cycle
            ]
        else:
            target_sessions = self.snapshot.sessions

        assignments = {s.session_id: s.assigned_room_id for s in target_sessions}

        candidate = AllocationCandidate(
            academic_cycle=academic_cycle,
            assignments=assignments,
            unassigned_sessions={},
            metadata={"source": "source_timetable_pdf_extraction"},
        )

        validator = IndependentValidator(
            snapshot=self.snapshot,
            capacity_mode=capacity_mode,
            allow_computing_lab_exception=allow_computing_lab_exception,
            synthetic_room_capacities=synthetic_room_capacities,
            synthetic_session_demands=synthetic_session_demands,
        )

        validation = validator.validate_candidate(candidate, sessions_to_verify=target_sessions)
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        return AllocationResult(
            candidate=candidate,
            validation=validation,
            allocator_name="SourceTimetableBenchmark",
            capacity_mode=capacity_mode.value,
            execution_time_ms=round(elapsed_ms, 2),
        )

    def run_baseline_allocation(
        self,
        academic_cycle: str = "all",
        allow_computing_lab_exception: bool = False,
        capacity_mode: CapacityPolicyMode = CapacityPolicyMode.FACTUAL,
        synthetic_room_capacities: Optional[Dict[str, int]] = None,
        synthetic_session_demands: Optional[Dict[str, int]] = None,
    ) -> AllocationResult:
        """Executes full baseline greedy allocation and independently validates the output.
        
        Reallocates all sessions in the requested cycle from scratch into a fresh working snapshot.
        """
        start_time = time.perf_counter()

        allocator = BaselineGreedyAllocator(
            snapshot=self.snapshot,
            allow_computing_lab_exception=allow_computing_lab_exception,
        )

        candidate = allocator.allocate(academic_cycle=academic_cycle)

        validator = IndependentValidator(
            snapshot=self.snapshot,
            capacity_mode=capacity_mode,
            allow_computing_lab_exception=allow_computing_lab_exception,
            synthetic_room_capacities=synthetic_room_capacities,
            synthetic_session_demands=synthetic_session_demands,
        )

        validation = validator.validate_candidate(candidate)
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        return AllocationResult(
            candidate=candidate,
            validation=validation,
            allocator_name="BaselineGreedyAllocator",
            capacity_mode=capacity_mode.value,
            execution_time_ms=round(elapsed_ms, 2),
        )

    def reallocate_sessions(
        self,
        session_ids_to_reallocate: List[str],
        academic_cycle: str = "all",
        allow_computing_lab_exception: bool = False,
        capacity_mode: CapacityPolicyMode = CapacityPolicyMode.FACTUAL,
    ) -> AllocationResult:
        """Reallocates a specific subset of sessions while keeping all other sessions reserved.
        
        Demonstrates release of working slots without stale occupancy interference.
        """
        start_time = time.perf_counter()
        realloc_set = set(session_ids_to_reallocate)

        if academic_cycle in ["odd", "even"]:
            target_sessions = [
                s for s in self.snapshot.sessions if s.academic_cycle == academic_cycle
            ]
        else:
            target_sessions = self.snapshot.sessions

        # Separate into reserved sessions and sessions to reallocate
        reserved_assignments: Dict[str, str] = {}
        sessions_to_reallocate: List[Session] = []

        for s in target_sessions:
            if s.session_id in realloc_set:
                sessions_to_reallocate.append(s)
            else:
                reserved_assignments[s.session_id] = s.assigned_room_id

        # Allocate only the released sessions
        allocator = BaselineGreedyAllocator(
            snapshot=self.snapshot,
            allow_computing_lab_exception=allow_computing_lab_exception,
        )

        candidate = allocator.allocate(
            academic_cycle=academic_cycle,
            sessions_to_allocate=sessions_to_reallocate,
            pre_reserved_assignments=reserved_assignments,
        )

        validator = IndependentValidator(
            snapshot=self.snapshot,
            capacity_mode=capacity_mode,
            allow_computing_lab_exception=allow_computing_lab_exception,
        )

        validation = validator.validate_candidate(candidate, sessions_to_verify=target_sessions)
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        return AllocationResult(
            candidate=candidate,
            validation=validation,
            allocator_name="BaselineGreedyAllocator_PartialReallocation",
            capacity_mode=capacity_mode.value,
            execution_time_ms=round(elapsed_ms, 2),
        )

    def run_optimized_allocation(
        self,
        academic_cycle: str = "all",
        allow_computing_lab_exception: bool = False,
        capacity_mode: CapacityPolicyMode = CapacityPolicyMode.FACTUAL,
        synthetic_room_capacities: Optional[Dict[str, int]] = None,
        synthetic_session_demands: Optional[Dict[str, int]] = None,
        time_limit_seconds: float = 10.0,
    ) -> AllocationResult:
        """Executes CP-SAT mathematical optimization and independently validates candidate."""
        optimizer = CPSATRoomOptimizer(
            snapshot=self.snapshot,
            allow_computing_lab_exception=allow_computing_lab_exception,
            capacity_mode=capacity_mode,
            synthetic_room_capacities=synthetic_room_capacities,
            synthetic_session_demands=synthetic_session_demands,
        )

        return optimizer.solve_and_validate(
            academic_cycle=academic_cycle,
            time_limit_seconds=time_limit_seconds,
        )

    def compare_baseline_and_optimizer(
        self,
        academic_cycle: str = "odd",
        allow_computing_lab_exception: bool = False,
        capacity_mode: CapacityPolicyMode = CapacityPolicyMode.FACTUAL,
        synthetic_room_capacities: Optional[Dict[str, int]] = None,
        synthetic_session_demands: Optional[Dict[str, int]] = None,
        time_limit_seconds: float = 10.0,
    ) -> MetricComparison:
        """Runs both baseline and optimizer under identical inputs and returns side-by-side comparison."""
        calc = MetricsCalculator(self.snapshot)

        baseline_res = self.run_baseline_allocation(
            academic_cycle=academic_cycle,
            allow_computing_lab_exception=allow_computing_lab_exception,
            capacity_mode=capacity_mode,
            synthetic_room_capacities=synthetic_room_capacities,
            synthetic_session_demands=synthetic_session_demands,
        )
        baseline_metrics = calc.calculate_metrics(
            candidate=baseline_res.candidate,
            allocator_name="BaselineGreedyAllocator",
            evaluation_mode=capacity_mode.value,
            synthetic_room_capacities=synthetic_room_capacities,
            synthetic_session_demands=synthetic_session_demands,
            execution_time_ms=baseline_res.execution_time_ms,
        )

        opt_res = self.run_optimized_allocation(
            academic_cycle=academic_cycle,
            allow_computing_lab_exception=allow_computing_lab_exception,
            capacity_mode=capacity_mode,
            synthetic_room_capacities=synthetic_room_capacities,
            synthetic_session_demands=synthetic_session_demands,
            time_limit_seconds=time_limit_seconds,
        )
        opt_metrics = calc.calculate_metrics(
            candidate=opt_res.candidate,
            allocator_name="CPSATRoomOptimizer",
            evaluation_mode=capacity_mode.value,
            synthetic_room_capacities=synthetic_room_capacities,
            synthetic_session_demands=synthetic_session_demands,
            execution_time_ms=opt_res.execution_time_ms,
        )

        return calc.compare_allocations(baseline_metrics, opt_metrics)

    def run_disruption_simulation(
        self,
        event_id: str,
        initial_assignments: Optional[Dict[str, str]] = None,
        max_unaffected_reassignments: int = 2,
        time_limit_seconds: float = 5.0,
    ) -> DisruptionSimulationResult:
        """Runs controlled dynamic simulation for a specific event from events catalog."""
        event = next((e for e in self.snapshot.events if e.event_id == event_id), None)
        if not event:
            from backend.app.core.simulation_engine import SimulationStatus
            return DisruptionSimulationResult(
                event_id=event_id,
                event_type="unknown",
                status=SimulationStatus.INVALID_EVENT,
                message=f"Event ID '{event_id}' not found in events catalog.",
                affected_sessions=[],
                diagnosis=f"Event '{event_id}' does not exist.",
            )

        sim_engine = SimulationEngine(
            snapshot=self.snapshot,
            initial_assignments=initial_assignments,
        )

        return sim_engine.simulate_disruption(
            event=event,
            max_unaffected_reassignments=max_unaffected_reassignments,
            time_limit_seconds=time_limit_seconds,
        )
