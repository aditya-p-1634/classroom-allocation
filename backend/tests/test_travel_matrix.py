"""Automated Tests for TravelMatrixService.

Verifies:
1. Symmetric bidirectional lookup: get_travel_time(A, B) == get_travel_time(B, A).
2. Zero travel time for a room travelling to itself: get_travel_time(A, A) == 0.0.
3. Explicit error handling for unknown rooms and missing pairs.
4. Full coverage of all 3,655 canonical pairs in both directions.
"""

import pytest
from backend.app.services.travel_matrix import TravelMatrixService
from backend.app.services.data_loader import DataLoaderService


@pytest.fixture(scope="module")
def travel_service():
    """Provides an initialized TravelMatrixService."""
    loader = DataLoaderService()
    records = loader.load_travel_times()
    return TravelMatrixService(travel_times=records)


def test_stored_pairs_and_room_counts(travel_service):
    """Verifies that 3,655 pairs and all 86 rooms are correctly indexed."""
    assert travel_service.stored_pair_count == 3655
    assert travel_service.known_rooms_count == 86


def test_zero_travel_time_for_same_room(travel_service):
    """Criterion 5: Zero travel time for a room travelling to itself."""
    sample_rooms = ["A105", "M601", "K701", "AA250"]
    for room in sample_rooms:
        assert travel_service.get_travel_time(room, room) == 0.0


def test_symmetric_lookup_forward_and_reverse(travel_service):
    """Criterion 5: Symmetric travel-time lookup in both orientations."""
    # Test known pairs
    t1 = travel_service.get_travel_time("A105", "A106")
    t2 = travel_service.get_travel_time("A106", "A105")
    assert t1 == t2
    assert t1 in [3.0, 8.0]

    t_cross1 = travel_service.get_travel_time("A105", "M601")
    t_cross2 = travel_service.get_travel_time("M601", "A105")
    assert t_cross1 == t_cross2
    assert t_cross1 in [3.0, 8.0]


def test_all_3655_pairs_queryable_bidirectionally(travel_service):
    """Ensures every single stored canonical pair resolves in both directions."""
    loader = DataLoaderService()
    records = loader.load_travel_times()

    for rec in records:
        f = rec.from_room_id
        t = rec.to_room_id
        expected = rec.walking_time_minutes

        forward = travel_service.get_travel_time(f, t)
        reverse = travel_service.get_travel_time(t, f)

        assert forward == expected, f"Mismatch on forward ({f}, {t})"
        assert reverse == expected, f"Mismatch on reverse ({t}, {f})"


def test_missing_or_unknown_room_errors(travel_service):
    """Criterion 6: Missing or invalid room pairs raise explicit exceptions."""
    # Unknown room ID raises KeyError
    with pytest.raises(KeyError) as exc_info:
        travel_service.get_travel_time("A105", "NON_EXISTENT_ROOM_XYZ")
    assert "NON_EXISTENT_ROOM_XYZ" in str(exc_info.value)

    with pytest.raises(KeyError):
        travel_service.get_travel_time("ROOM_FOO", "ROOM_BAR")

    # Invalid empty/None parameters raise ValueError
    with pytest.raises(ValueError):
        travel_service.get_travel_time("", "A105")

    with pytest.raises(ValueError):
        travel_service.get_travel_time("A105", None)  # type: ignore

    with pytest.raises(ValueError):
        travel_service.get_travel_time("   ", "A105")
