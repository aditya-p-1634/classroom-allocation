"""Symmetric Travel-Time Lookup Service for ClassroomIQ.

Provides bidirectional query capabilities over the unidirectional canonical
pairs stored in travel_times.csv without modifying the underlying dataset.
"""

from typing import Dict, Tuple, Set, Optional, List
from backend.app.schemas.models import TravelTime
from backend.app.services.data_loader import DataLoaderService


class TravelMatrixService:
    """Reusable service providing symmetric walking time queries between room pairs."""

    def __init__(self, travel_times: Optional[List[TravelTime]] = None):
        """Initializes the travel matrix lookup table.
        
        Args:
            travel_times: Optional pre-loaded list of TravelTime models.
                         If None, loads dynamically using DataLoaderService.
        """
        if travel_times is None:
            travel_times = DataLoaderService().load_travel_times()

        self._matrix: Dict[Tuple[str, str], float] = {}
        self._known_rooms: Set[str] = set()

        for rec in travel_times:
            r1, r2 = rec.from_room_id.strip(), rec.to_room_id.strip()
            self._known_rooms.add(r1)
            self._known_rooms.add(r2)
            # Store in canonical order: (min, max)
            key = (min(r1, r2), max(r1, r2))
            self._matrix[key] = rec.walking_time_minutes

    @property
    def known_rooms_count(self) -> int:
        """Returns the count of distinct rooms present in travel records."""
        return len(self._known_rooms)

    @property
    def stored_pair_count(self) -> int:
        """Returns the number of canonical stored pairs."""
        return len(self._matrix)

    def is_known_room(self, room_id: str) -> bool:
        """Checks if a room ID is recognized in the travel network."""
        return room_id in self._known_rooms

    def has_pair(self, room_a: str, room_b: str) -> bool:
        """Checks if travel time is defined between room_a and room_b."""
        if not room_a or not room_b:
            return False
        if room_a == room_b:
            return True
        key = (min(room_a, room_b), max(room_a, room_b))
        return key in self._matrix

    def get_travel_time(self, room_a: str, room_b: str) -> float:
        """Returns the walking time in minutes between room_a and room_b.
        
        Rules:
        - If room_a == room_b: returns 0.0 minutes (same room).
        - If (room_a, room_b) exists in either orientation: returns the symmetric duration.
        - If either room is empty, unknown, or the pair is missing: raises KeyError.
        
        Args:
            room_a: Origin room ID (e.g. 'A105')
            room_b: Destination room ID (e.g. 'M601')
            
        Returns:
            Walking time in minutes (float).
            
        Raises:
            ValueError: If either room_a or room_b is None or empty.
            KeyError: If room pair is missing from the travel network.
        """
        if not room_a or not isinstance(room_a, str) or not room_a.strip():
            raise ValueError(f"Invalid room_a parameter: {room_a!r}")
        if not room_b or not isinstance(room_b, str) or not room_b.strip():
            raise ValueError(f"Invalid room_b parameter: {room_b!r}")

        ra = room_a.strip()
        rb = room_b.strip()

        # Zero travel time for a room travelling to itself
        if ra == rb:
            return 0.0

        canonical_key = (min(ra, rb), max(ra, rb))
        if canonical_key in self._matrix:
            return self._matrix[canonical_key]

        raise KeyError(
            f"Travel time not defined between '{room_a}' and '{room_b}' "
            f"(canonical key {canonical_key} not found)."
        )
