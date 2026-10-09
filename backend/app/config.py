"""ClassroomIQ System Configuration and Path Definitions.

Governed by ClassroomIQ_Document_05_Implementation_Roadmap_and_Build_Authorization_v0.2.0.docx.
Phase P4: Build Preparation & Scaffolding.
"""

from pathlib import Path
from enum import Enum


class CapacityPolicyMode(str, Enum):
    """Capacity policy operational modes per Phase P4 authorization.
    
    - FACTUAL: Uses strictly verified source data without imputing missing student
      counts or room capacities. Capacity feasibility is not claimed when values are absent.
    - SYNTHETIC_EVALUATION: Explicitly labeled synthetic assumptions reserved for future
      evaluation capability. Never alters source datasets or presents estimates as facts.
    """
    FACTUAL = "factual"
    SYNTHETIC_EVALUATION = "synthetic_evaluation"


# Base directory references
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"

# Dataset filenames
ROOMS_FILENAME = "rooms.csv"
FACILITIES_FILENAME = "facilities.csv"
SESSIONS_FILENAME = "sessions.csv"
AVAILABILITY_FILENAME = "availability.csv"
TRAVEL_TIMES_FILENAME = "travel_times.csv"
EVENTS_FILENAME = "events.csv"
COMPLAINTS_FILENAME = "complaints.csv"

# Current baseline dataset snapshot expected row counts
EXPECTED_ROW_COUNTS = {
    ROOMS_FILENAME: 86,
    FACILITIES_FILENAME: 86,
    SESSIONS_FILENAME: 1250,
    AVAILABILITY_FILENAME: 6880,
    TRAVEL_TIMES_FILENAME: 3655,
    EVENTS_FILENAME: 5,
    COMPLAINTS_FILENAME: 5,
}

# Default capacity profile parameters (for future evaluation mode only, NOT factual)
DEFAULT_SYNTHETIC_SECTION_SIZE = 60
DEFAULT_SYNTHETIC_LAB_SIZE = 35
DEFAULT_SYNTHETIC_CLASSROOM_CAPACITY = 65
DEFAULT_SYNTHETIC_LAB_CAPACITY = 40
