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
   * Fetches room inventory (86 rooms).
   */
  async getRooms(roomType = null) {
    const url = roomType ? `${API_BASE}/inventory/rooms?room_type=${encodeURIComponent(roomType)}` : `${API_BASE}/inventory/rooms`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Rooms API error: ${res.statusText}`);
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
   * Fetches sessions.
   */
  async getSessions(cycle = 'odd', program = null, cohortId = null, day = null) {
    const params = new URLSearchParams();
    if (cycle) params.append('academic_cycle', cycle);
    if (program) params.append('program', program);
    if (cohortId) params.append('cohort_id', cohortId);
    if (day) params.append('day', day);
    const res = await fetch(`${API_BASE}/inventory/sessions?${params.toString()}`);
    if (!res.ok) throw new Error(`Sessions API error: ${res.statusText}`);
    return await res.json();
  },

  /**
   * Fetches timetable weekly matrix.
   */
  async getTimetableGrid(cycle = 'odd', cohortId = null, program = null, day = null) {
    const params = new URLSearchParams();
    params.append('academic_cycle', cycle);
    if (cohortId) params.append('cohort_id', cohortId);
    if (program) params.append('program', program);
    if (day) params.append('day', day);
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
   * Runs Independent Validator audit on source timetable or candidate.
   */
  async runAudit(cycle = 'even') {
    const res = await fetch(`${API_BASE}/validation/audit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ academic_cycle: cycle })
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
  }
};
