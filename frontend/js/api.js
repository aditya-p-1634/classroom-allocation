/**
 * ClassroomIQ — REST API Client Module
 * Interfaces with FastAPI backend bridge endpoints with error handling.
 */

const API_BASE = '/api';

export const Api = {
  /**
   * Fetches system operational status, dataset checksums, and phase checklist.
   */
  async getStatus() {
    const res = await fetch(`${API_BASE}/status`);
    if (!res.ok) throw new Error(`Status API error: ${res.statusText}`);
    return await res.json();
  },

  /**
   * Fetches Synthetic Demo Profile documentation and parameters.
   */
  async getProfile() {
    const res = await fetch(`${API_BASE}/inventory/profile`);
    if (!res.ok) throw new Error(`Profile API error: ${res.statusText}`);
    return await res.json();
  },

  /**
   * Fetches room inventory (86 rooms) with active mode support.
   */
  async getRooms(roomType = null, capability = null, buildingBlock = null, mode = 'synthetic') {
    const params = new URLSearchParams();
    if (roomType) params.append('room_type', roomType);
    if (capability) params.append('capability', capability);
    if (buildingBlock) params.append('building_block', buildingBlock);
    if (mode) params.append('mode', mode);

    const res = await fetch(`${API_BASE}/inventory/rooms?${params.toString()}`);
    if (!res.ok) throw new Error(`Rooms API error: ${res.statusText}`);
    return await res.json();
  },

  /**
   * Fetches detailed profile and occupancy schedule for a specific room.
   */
  async getRoomDetail(roomId, cycle = 'even', mode = 'synthetic') {
    const params = new URLSearchParams();
    params.append('academic_cycle', cycle);
    params.append('mode', mode);

    const res = await fetch(`${API_BASE}/inventory/room-detail/${encodeURIComponent(roomId)}?${params.toString()}`);
    if (!res.ok) throw new Error(`Room detail error: ${res.statusText}`);
    return await res.json();
  },

  /**
   * Fetches the 5 programs.
   */
  async getPrograms() {
    const res = await fetch(`${API_BASE}/inventory/programs`);
    if (!res.ok) throw new Error(`Programs API error: ${res.statusText}`);
    return await res.json();
  },

  /**
   * Fetches the 45 cohorts.
   */
  async getCohorts(cycle = null, program = null) {
    const params = new URLSearchParams();
    if (cycle) params.append('academic_cycle', cycle);
    if (program) params.append('program', program);
    const res = await fetch(`${API_BASE}/inventory/cohorts?${params.toString()}`);
    if (!res.ok) throw new Error(`Cohorts API error: ${res.statusText}`);
    return await res.json();
  },

  /**
   * Fetches sessions occurrences.
   */
  async getSessions(cycle = 'odd', program = null, cohortId = null, day = null, roomId = null, mode = 'synthetic') {
    const params = new URLSearchParams();
    if (cycle) params.append('academic_cycle', cycle);
    if (program) params.append('program', program);
    if (cohortId) params.append('cohort_id', cohortId);
    if (day) params.append('day', day);
    if (roomId) params.append('room_id', roomId);
    if (mode) params.append('mode', mode);
    const res = await fetch(`${API_BASE}/inventory/sessions?${params.toString()}`);
    if (!res.ok) throw new Error(`Sessions API error: ${res.statusText}`);
    return await res.json();
  },

  /**
   * Fetches timetable weekly matrix rendered from selected allocation source.
   */
  async getTimetableGrid({
    cycle = 'even',
    allocationSource = 'source',
    groupBy = 'cohort',
    cohortId = null,
    program = null,
    roomId = null,
    day = 'Monday',
    mode = 'synthetic'
  } = {}) {
    const params = new URLSearchParams();
    params.append('academic_cycle', cycle);
    params.append('allocation_source', allocationSource);
    params.append('group_by', groupBy);
    if (cohortId) params.append('cohort_id', cohortId);
    if (program) params.append('program', program);
    if (roomId) params.append('room_id', roomId);
    if (day) params.append('day', day);
    if (mode) params.append('mode', mode);

    const res = await fetch(`${API_BASE}/inventory/timetables?${params.toString()}`);
    if (!res.ok) throw new Error(`Timetable API error: ${res.statusText}`);
    return await res.json();
  },

  /**
   * Executes baseline vs optimizer comparison.
   */
  async compareAllocations(cycle = 'even', timeLimit = 10.0) {
    const res = await fetch(`${API_BASE}/allocation/compare`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ academic_cycle: cycle, time_limit_seconds: timeLimit })
    });
    if (!res.ok) throw new Error(`Comparison API error: ${res.statusText}`);
    return await res.json();
  },

  /**
   * Runs Independent Validator audit on source timetable, baseline, or optimizer candidate.
   */
  async runAudit(cycle = 'even', target = 'baseline', allowException = false, timeLimit = 10.0, mode = 'synthetic') {
    const res = await fetch(`${API_BASE}/validation/audit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        academic_cycle: cycle,
        target: target,
        allow_computing_lab_exception: allowException,
        time_limit_seconds: timeLimit,
        mode: mode
      })
    });
    if (!res.ok) throw new Error(`Validation API error: ${res.statusText}`);
    return await res.json();
  },

  /**
   * Fetches disruption simulation events catalog.
   */
  async getEvents() {
    const res = await fetch(`${API_BASE}/simulation/events`);
    if (!res.ok) throw new Error(`Simulation events error: ${res.statusText}`);
    return await res.json();
  },

  /**
   * Triggers a disruption event simulation.
   */
  async triggerDisruption(eventId = 'EVT-DEMO-001', cycle = 'even') {
    const res = await fetch(`${API_BASE}/simulation/trigger`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ event_id: eventId, academic_cycle: cycle })
    });
    if (!res.ok) throw new Error(`Trigger disruption error: ${res.statusText}`);
    return await res.json();
  },

  /**
   * Executes atomic state rollback.
   */
  async rollbackDisruption() {
    const res = await fetch(`${API_BASE}/simulation/rollback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
    if (!res.ok) throw new Error(`Rollback error: ${res.statusText}`);
    return await res.json();
  },

  /**
   * Preflights uploaded raw timetable CSV files.
   */
  async preflightUpload(payload) {
    const res = await fetch(`${API_BASE}/upload/preflight`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `Preflight error: ${res.statusText}`);
    }
    return await res.json();
  },

  /**
   * Triggers joint CP-SAT multi-program allocation across shared room inventory.
   */
  async allocateUpload(payload) {
    const res = await fetch(`${API_BASE}/upload/allocate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `Allocation error: ${res.statusText}`);
    }
    return await res.json();
  },

  /**
   * Fetches allocated weekly timetable grid for a specific upload run.
   */
  async getUploadTimetable(runId, { day = 'Monday', groupBy = 'cohort', program = null, cohortId = null, roomId = null } = {}) {
    const params = new URLSearchParams();
    if (day) params.append('day', day);
    if (groupBy) params.append('group_by', groupBy);
    if (program) params.append('program', program);
    if (cohortId) params.append('cohort_id', cohortId);
    if (roomId) params.append('room_id', roomId);

    const res = await fetch(`${API_BASE}/upload/timetable/${encodeURIComponent(runId)}?${params.toString()}`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `Upload timetable error: ${res.statusText}`);
    }
    return await res.json();
  },

  /**
   * Returns download URL for combined CSV or ZIP export package.
   */
  getExportUrl(runId, format = 'csv') {
    return `${API_BASE}/upload/export/${encodeURIComponent(runId)}?format=${encodeURIComponent(format)}`;
  }
};
