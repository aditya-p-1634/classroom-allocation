"""ClassroomIQ — Synthetic Demo Profile Definition.

Governed by Document 05 Phase P7 specification.
Provides deterministic, repeatable, and documented demo assumptions for capacity,
enrollment, and facility operational status in memory without altering source CSVs.
"""

from typing import Dict, Any, Optional
from backend.app.schemas.models import DatasetSnapshot, Room, Session


# Documented Building Name mappings based on Document 05 Section 11 prefix rules
BUILDING_BLOCK_MAPPINGS: Dict[str, str] = {
    "M": "Block M (Main Technology Complex)",
    "A": "Block A (Academic Wing A)",
    "K": "Block K (Computing Sciences)",
    "S": "Block S (Science & Research)",
    "L": "Block L (Lecture Hall Complex)",
    "H": "Block H (Humanities & Admin)",
    "C": "Block C (Central Campus Block)",
    "D": "Block D (Data Systems Wing)",
    "E": "Block E (Engineering Annex)",
    "G": "Block G (Graduate Center)",
    "B": "Block B (Business & Finance)",
}

# Deterministic Demo Capacities
DEFAULT_CLASSROOM_CAPACITY = 65
DEFAULT_LABORATORY_CAPACITY = 40
DEFAULT_ASSEMBLY_CAPACITY = 120

# Deterministic Demo Enrollments by Session Type
DEFAULT_LECTURE_DEMAND = 55
DEFAULT_LAB_DEMAND = 30
DEFAULT_SEMINAR_DEMAND = 25


class SyntheticProfileService:
    """Provides deterministic synthetic profile parameters for prototype review."""

    @staticmethod
    def get_room_building_and_floor(room_id: str) -> Dict[str, str]:
        """Derives building block and floor deterministically from room ID prefix and digits."""
        if not room_id:
            return {"building_block": "Main Campus", "floor": "Ground Floor"}
        
        prefix = room_id[0].upper()
        block_name = BUILDING_BLOCK_MAPPINGS.get(prefix, f"Block {prefix}")
        
        # Determine floor from first numeric character if available
        digits = [c for c in room_id[1:] if c.isdigit()]
        if digits:
            floor_num = int(digits[0])
            floor_name = f"Floor {floor_num}" if floor_num > 0 else "Ground Floor"
        else:
            floor_name = "Floor 1"
            
        return {
            "building_block": block_name,
            "floor": floor_name,
            "campus_zone": "Academic Core Zone",
        }

    @staticmethod
    def get_synthetic_room_capacity(room: Room) -> int:
        """Returns verified capacity if present, otherwise returns deterministic synthetic capacity."""
        if room.has_known_capacity and room.capacity:
            return room.capacity
        if room.room_type == "laboratory":
            return DEFAULT_LABORATORY_CAPACITY
        if room.room_type == "assembly_hall":
            return DEFAULT_ASSEMBLY_CAPACITY
        return DEFAULT_CLASSROOM_CAPACITY

    @staticmethod
    def get_synthetic_session_demand(session: Session) -> int:
        """Returns verified student count if present, otherwise returns deterministic synthetic demand."""
        if session.student_count is not None and session.student_count > 0:
            return session.student_count
        if session.required_room_type == "laboratory" or session.session_type == "lab":
            return DEFAULT_LAB_DEMAND
        if session.required_room_type == "assembly_hall" or session.session_type == "seminar":
            return DEFAULT_SEMINAR_DEMAND
        return DEFAULT_LECTURE_DEMAND

    @classmethod
    def build_synthetic_room_capacities_map(cls, snapshot: DatasetSnapshot) -> Dict[str, int]:
        """Builds complete room ID -> capacity mapping for IndependentValidator."""
        return {r.room_id: cls.get_synthetic_room_capacity(r) for r in snapshot.rooms}

    @classmethod
    def build_synthetic_session_demands_map(cls, snapshot: DatasetSnapshot) -> Dict[str, int]:
        """Builds complete session ID -> student count mapping for IndependentValidator."""
        return {s.session_id: cls.get_synthetic_session_demand(s) for s in snapshot.sessions}
