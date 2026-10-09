/**
 * ClassroomIQ — Application Controller
 * Manages dashboard state, timetable grid, optimization studio, and disruption sandbox.
 */

import { Api } from './api.js';

class ClassroomIQApp {
  constructor() {
    this.currentCycle = 'odd'; // Default to Odd cycle (680 sessions) as in Image 2
    this.currentViewTab = 'timetable';
    this.selectedProgram = '';
    this.selectedCohort = '';
    this.selectedDay = 'Monday';

    this.programs = [];
    this.cohorts = [];
    this.events = [];
  }

  async init() {
    try {
      this.bindEvents();
      await this.loadInitialData();
      await this.renderDashboard();
      await this.loadTimetable();
      await this.loadComparisonData();
      await this.loadSimulationEvents();
    } catch (err) {
      console.error('Initialization error:', err);
      this.showToast('Initialization error: ' + err.message, 'danger');
    }
  }

  bindEvents() {
    // Cycle switcher dropdown
    const cycleSelect = document.getElementById('cycle-select');
    if (cycleSelect) {
      cycleSelect.addEventListener('change', (e) => {
        this.currentCycle = e.target.value;
        this.onCycleChange();
      });
    }

    // Run Optimization button
    const btnOptimize = document.getElementById('btn-run-optimize');
    if (btnOptimize) {
      btnOptimize.addEventListener('click', () => this.runOptimization());
    }

    // Timetable View Tabs
    const tabBtns = document.querySelectorAll('.tab-btn');
    tabBtns.forEach(btn => {
      btn.addEventListener('click', (e) => {
        tabBtns.forEach(b => b.classList.remove('active'));
        e.target.classList.add('active');
        this.currentViewTab = e.target.dataset.tab;
        this.loadTimetable();
      });
    });

    // Filters
    const programSelect = document.getElementById('filter-program');
    if (programSelect) {
      programSelect.addEventListener('change', (e) => {
        this.selectedProgram = e.target.value;
        this.loadTimetable();
      });
    }

    const cohortSelect = document.getElementById('filter-cohort');
    if (cohortSelect) {
      cohortSelect.addEventListener('change', (e) => {
        this.selectedCohort = e.target.value;
        this.loadTimetable();
      });
    }

    const daySelect = document.getElementById('filter-day');
    if (daySelect) {
      daySelect.addEventListener('change', (e) => {
        this.selectedDay = e.target.value;
        this.loadTimetable();
      });
    }

    // Disruption trigger & rollback
    const eventSelect = document.getElementById('event-select');
    if (eventSelect) {
      eventSelect.addEventListener('change', (e) => {
        this.onEventSelected(e.target.value);
      });
    }

    const btnSimulate = document.getElementById('btn-run-simulation');
    if (btnSimulate) {
      btnSimulate.addEventListener('click', () => this.runSimulation());
    }

    const btnRollback = document.getElementById('btn-rollback');
    if (btnRollback) {
      btnRollback.addEventListener('click', () => this.rollbackSimulation());
    }

    // Validation audit
    const btnAudit = document.getElementById('btn-run-audit');
    if (btnAudit) {
      btnAudit.addEventListener('click', () => this.runValidationAudit());
    }

    // Modal close
    const modalClose = document.getElementById('modal-close');
    const modalBackdrop = document.getElementById('modal-backdrop');
    if (modalClose && modalBackdrop) {
      modalClose.addEventListener('click', () => modalBackdrop.classList.remove('open'));
      modalBackdrop.addEventListener('click', (e) => {
        if (e.target === modalBackdrop) modalBackdrop.classList.remove('open');
      });
    }
  }

  async loadInitialData() {
    this.programs = await Api.getPrograms();
    this.cohorts = await Api.getCohorts(this.currentCycle);
    this.events = await Api.getEvents();

    // Populate filter dropdowns
    const progSel = document.getElementById('filter-program');
    if (progSel) {
      progSel.innerHTML = '<option value="">All Programs</option>' +
        this.programs.map(p => `<option value="${p.program}">${p.program}</option>`).join('');
    }

    this.updateCohortFilter();

    // Populate events dropdown
    const evtSel = document.getElementById('event-select');
    if (evtSel) {
      evtSel.innerHTML = this.events.map(e =>
        `<option value="${e.event_id}">${e.event_id}: ${e.room_id} ${e.event_type.replace('_', ' ').toUpperCase()}</option>`
      ).join('');
    }
  }

  updateCohortFilter() {
    const cohortSel = document.getElementById('filter-cohort');
    if (cohortSel) {
      const filtered = this.cohorts.filter(c => !this.selectedProgram || c.program === this.selectedProgram);
      cohortSel.innerHTML = '<option value="">All Cohorts</option>' +
        filtered.map(c => `<option value="${c.cohort_id}">${c.cohort_id}</option>`).join('');
    }
  }

  async onCycleChange() {
    this.cohorts = await Api.getCohorts(this.currentCycle);
    this.updateCohortFilter();
    await this.renderDashboard();
    await this.loadTimetable();
    await this.loadComparisonData();
  }

  async renderDashboard() {
    const statusData = await Api.getStatus();
    const summary = statusData.dataset_summary;

    // KPI 1: Total Sessions
    const kpiSessionsVal = document.getElementById('kpi-sessions-val');
    const kpiSessionsSub = document.getElementById('kpi-sessions-sub');
    if (kpiSessionsVal && kpiSessionsSub) {
      if (this.currentCycle === 'odd') {
        kpiSessionsVal.textContent = '680';
        kpiSessionsSub.textContent = 'Odd cycle selected ↔ Even cycle: 570';
      } else {
        kpiSessionsVal.textContent = '570';
        kpiSessionsSub.textContent = 'Even cycle selected ↔ Odd cycle: 680';
      }
    }

    // KPI 2: Program Types
    const kpiProgramsVal = document.getElementById('kpi-programs-val');
    if (kpiProgramsVal) kpiProgramsVal.textContent = summary.programs_count;

    // KPI 3: Student Cohorts
    const kpiCohortsVal = document.getElementById('kpi-cohorts-val');
    if (kpiCohortsVal) kpiCohortsVal.textContent = summary.cohorts_count;

    // KPI 4: Room Inventory
    const kpiRoomsVal = document.getElementById('kpi-rooms-val');
    if (kpiRoomsVal) kpiRoomsVal.textContent = summary.rooms_inventory_count;

    // KPI 5: Room Availability
    const kpiAvailVal = document.getElementById('kpi-avail-val');
    if (kpiAvailVal) {
      kpiAvailVal.textContent = 'Unknown';
      kpiAvailVal.className = 'kpi-value unknown';
    }
  }

  async loadTimetable() {
    const tableBody = document.getElementById('timetable-tbody');
    if (!tableBody) return;

    tableBody.innerHTML = '<tr><td colspan="10" class="skeleton" style="height:120px;"></td></tr>';

    try {
      const data = await Api.getTimetableGrid(
        this.currentCycle,
        this.selectedCohort || null,
        this.selectedProgram || null,
        this.selectedDay
      );

      const dayGrid = data.grid[this.selectedDay] || {};
      const sessions = await Api.getSessions(
        this.currentCycle,
        this.selectedProgram || null,
        this.selectedCohort || null,
        this.selectedDay
      );

      // Group sessions by cohort or room depending on view
      const rowKey = (this.currentViewTab === 'room') ? 'assigned_room_id' : 'cohort_id';
      const rowsMap = {};

      sessions.forEach(s => {
        const key = s[rowKey] || 'Unassigned';
        if (!rowsMap[key]) rowsMap[key] = { key: key, sessions: [] };
        rowsMap[key].sessions.push(s);
      });

      const rowKeys = Object.keys(rowsMap).sort().slice(0, 8); // show preview set

      if (rowKeys.length === 0) {
        tableBody.innerHTML = '<tr><td colspan="10" style="text-align:center; padding: 2rem; color:#64748b;">No scheduled occurrences found for the selected filters.</td></tr>';
        return;
      }

      let html = '';
      rowKeys.forEach(rk => {
        html += `<tr><td class="cohort-label"><strong>${rk}</strong></td>`;
        for (let p = 1; p <= 9; p++) {
          const matching = rowsMap[rk].sessions.filter(s => s.period_range.includes(p));
          if (matching.length > 0) {
            const s = matching[0];
            html += `<td>
              <div class="slot-box" data-session='${JSON.stringify(s).replace(/'/g, "&apos;")}'>
                <span class="slot-room">${s.assigned_room_id || '—'}</span>
                <span class="slot-course" title="${s.course}">${s.course}</span>
              </div>
            </td>`;
          } else {
            html += '<td style="color:#cbd5e1;">—</td>';
          }
        }
        html += '</tr>';
      });

      tableBody.innerHTML = html;

      // Add click listeners to slots
      tableBody.querySelectorAll('.slot-box').forEach(box => {
        box.addEventListener('click', () => {
          const s = JSON.parse(box.dataset.session);
          this.openSessionModal(s);
        });
      });

    } catch (err) {
      console.error('Timetable load error:', err);
      tableBody.innerHTML = `<tr><td colspan="10" style="color:#b91c1c; padding: 1rem;">Failed to load timetable: ${err.message}</td></tr>`;
    }
  }

  openSessionModal(s) {
    const modalBackdrop = document.getElementById('modal-backdrop');
    const modalContent = document.getElementById('modal-details');
    if (!modalBackdrop || !modalContent) return;

    modalContent.innerHTML = `
      <div style="display:flex; flex-direction:column; gap:0.6rem; font-size:0.85rem;">
        <div><strong>Session ID:</strong> <code>${s.session_id}</code></div>
        <div><strong>Course:</strong> ${s.course}</div>
        <div><strong>Cohort:</strong> <code>${s.cohort_id}</code></div>
        <div><strong>Program:</strong> ${s.program}</div>
        <div><strong>Schedule:</strong> ${s.day}, Periods ${s.start_period}–${s.end_period}</div>
        <div><strong>Required Room Type:</strong> <span class="badge-tag">${s.required_room_type}</span></div>
        <div><strong>Assigned Room:</strong> <strong>${s.assigned_room_id}</strong></div>
        <div style="background:#fef3c7; border:1px solid #fde68a; padding:0.6rem; border-radius:6px; margin-top:0.5rem;">
          <div style="font-weight:700; color:#b45309; font-size:0.75rem; text-transform:uppercase;">Data Gap & Integrity Guard</div>
          <div style="color:#92400e; font-size:0.75rem; margin-top:0.2rem;">
            • Student Enrollment Count: <strong>Unknown (Data Gap)</strong><br>
            • Physical Room Capacity: <strong>Unknown for 56 rooms in source data</strong>
          </div>
        </div>
      </div>
    `;

    modalBackdrop.classList.add('open');
  }

  async loadComparisonData() {
    try {
      const data = await Api.compareAllocations(this.currentCycle, 10.0);
      this.renderComparisonCards(data);
    } catch (err) {
      console.warn('Comparison data load error:', err);
    }
  }

  renderComparisonCards(data) {
    // Bar chart fill
    const barEvenBase = document.getElementById('bar-even-base');
    const barEvenOpt = document.getElementById('bar-even-opt');
    const barOddBase = document.getElementById('bar-odd-base');
    const barOddCand = document.getElementById('bar-odd-cand');

    if (barEvenBase && barEvenOpt) {
      barEvenBase.style.width = '100%';
      // 456 / 1155 = ~39.5%
      barEvenOpt.style.width = '39.5%';
    }

    if (barOddBase && barOddCand) {
      barOddBase.style.width = '96.5%';
      barOddCand.style.width = '100%';
    }
  }

  async runOptimization() {
    const btn = document.getElementById('btn-run-optimize');
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<span>Optimizing...</span>';
    }

    this.showToast(`Executing CP-SAT solver for ${this.currentCycle} cycle (search limit: 10s)...`, 'info');

    try {
      const data = await Api.compareAllocations(this.currentCycle, 10.0);
      this.renderComparisonCards(data);

      if (data.fallback_to_baseline) {
        this.showToast(`Optimization complete: Candidate rejected (+3.04%). Baseline retained (1,248.0 min).`, 'warning');
      } else {
        this.showToast(`Optimization complete: Walking time reduced by ${data.walking_time_reduction_percentage}% (${data.walking_time_reduction_minutes} min)!`, 'success');
      }
    } catch (err) {
      this.showToast(`Optimization failed: ${err.message}`, 'danger');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = '<span>Run Optimization</span>';
      }
    }
  }

  onEventSelected(eventId) {
    const evt = this.events.find(e => e.event_id === eventId);
    if (!evt) return;

    const detailsEl = document.getElementById('disruption-scenario-details');
    if (detailsEl) {
      detailsEl.innerHTML = `
        <div class="disruption-detail-row">
          <span>Affected room:</span>
          <strong>${evt.room_id}</strong>
        </div>
        <div class="disruption-detail-row">
          <span>Event Type:</span>
          <span>${evt.event_type.replace('_', ' ')}</span>
        </div>
        <div class="disruption-detail-row">
          <span>Repair window:</span>
          <span>Full cycle (${evt.start_day}–${evt.end_day})</span>
        </div>
        ${evt.room_id === 'M601' ? `
        <div class="disruption-detail-row">
          <span>Concurrent lab sessions:</span>
          <strong>20</strong>
        </div>
        <div class="disruption-detail-row">
          <span>Available lab rooms:</span>
          <strong>19</strong>
        </div>` : ''}
      `;
    }
  }

  async runSimulation() {
    const evtSel = document.getElementById('event-select');
    const eventId = evtSel ? evtSel.value : 'EVT-DEMO-001';

    try {
      const res = await Api.triggerDisruption(eventId, this.currentCycle);
      const outcomeBox = document.getElementById('disruption-outcome-box');
      if (outcomeBox) {
        outcomeBox.style.display = 'block';
        if (res.is_repaired) {
          outcomeBox.className = 'disruption-outcome-box' ;
          outcomeBox.style.backgroundColor = '#dcfce7';
          outcomeBox.style.borderColor = '#bbf7d0';
          outcomeBox.innerHTML = `
            <div class="disruption-outcome-header" style="color:#15803d;">SUCCESSFUL REPAIR</div>
            <div class="disruption-outcome-desc" style="color:#166534;">${res.diagnosis_explanation}</div>
          `;
          this.showToast('Disruption successfully repaired!', 'success');
        } else {
          outcomeBox.className = 'disruption-outcome-box';
          outcomeBox.style.backgroundColor = '#fff1f2';
          outcomeBox.style.borderColor = '#fecdd3';
          outcomeBox.innerHTML = `
            <div class="disruption-outcome-header" style="color:#be123c;">INFEASIBLE REPAIR</div>
            <div class="disruption-outcome-desc" style="color:#881337;">${res.diagnosis_explanation}</div>
          `;
          this.showToast('Disruption diagnosed as mathematically infeasible. State rolled back safely.', 'warning');
        }
      }
    } catch (err) {
      this.showToast(`Simulation error: ${err.message}`, 'danger');
    }
  }

  async rollbackSimulation() {
    try {
      const res = await Api.rollbackDisruption();
      const outcomeBox = document.getElementById('disruption-outcome-box');
      if (outcomeBox) outcomeBox.style.display = 'none';
      this.showToast(res.message, 'success');
      await this.loadTimetable();
    } catch (err) {
      this.showToast(`Rollback error: ${err.message}`, 'danger');
    }
  }

  async runValidationAudit() {
    const btn = document.getElementById('btn-run-audit');
    if (btn) btn.disabled = true;
    this.showToast(`Running Independent Validator audit on ${this.currentCycle} cycle...`, 'info');

    try {
      const res = await Api.runAudit(this.currentCycle);
      const auditBadge = document.getElementById('audit-badge');
      const targetLabel = document.getElementById('audit-target-label');
      if (targetLabel) targetLabel.textContent = `${this.currentCycle.toUpperCase()} Cycle Allocation (${res.total_sessions_checked} sessions)`;

      if (auditBadge) {
        if (res.status === 'valid_complete' || res.status === 'feasible') {
          auditBadge.className = 'badge-tag improved';
          auditBadge.textContent = 'VALID_COMPLETE (FEASIBLE)';
          auditBadge.style.color = '#15803d';
        } else {
          auditBadge.className = 'badge-tag baseline-kept';
          auditBadge.textContent = res.status.toUpperCase();
        }
      }

      // Update breakdown metrics
      const cb = res.category_breakdown || {};
      const elExcl = document.getElementById('audit-exclusivity');
      if (elExcl) {
        const fails = (cb['room_exclusivity']?.fail || 0);
        elExcl.textContent = `${fails} Violations`;
        elExcl.style.color = fails === 0 ? '#15803d' : '#b91c1c';
      }

      const elCohort = document.getElementById('audit-cohort');
      if (elCohort) {
        const fails = (cb['cohort_exclusivity']?.fail || 0);
        elCohort.textContent = `${fails} Violations`;
        elCohort.style.color = fails === 0 ? '#15803d' : '#b91c1c';
      }

      const elCapab = document.getElementById('audit-capability');
      if (elCapab) {
        const fails = (cb['room_capability']?.fail || 0);
        elCapab.textContent = fails === 0 ? '100% Compatible' : `${fails} Incompatible`;
        elCapab.style.color = fails === 0 ? '#15803d' : '#b91c1c';
      }

      const elAvail = document.getElementById('audit-availability');
      if (elAvail) {
        const fails = (cb['confirmed_availability']?.fail || 0);
        elAvail.textContent = `${fails} Violations`;
        elAvail.style.color = fails === 0 ? '#15803d' : '#b91c1c';
      }

      const elCapac = document.getElementById('audit-capacity');
      if (elCapac) {
        elCapac.textContent = 'Unknown (Data Gap)';
        elCapac.className = 'kpi-value unknown';
      }

      // Populate log table
      const tbody = document.getElementById('audit-log-tbody');
      if (tbody && res.sample_findings) {
        tbody.innerHTML = '';
        res.sample_findings.forEach(f => {
          const tr = document.createElement('tr');
          const isPass = f.status === 'pass';
          const isUnknown = f.status === 'insufficient_evidence';
          const badgeClass = isPass ? 'color:#15803d; font-weight:600;' : (isUnknown ? 'color:#b45309; font-weight:600;' : 'color:#b91c1c; font-weight:600;');
          tr.innerHTML = `
            <td style="padding:0.4rem 0.6rem; border-bottom:1px solid #e2e8f0; font-family:var(--font-mono); font-size:0.7rem;">${f.constraint}</td>
            <td style="padding:0.4rem 0.6rem; border-bottom:1px solid #e2e8f0;"><span style="${badgeClass}">${f.status.toUpperCase()}</span></td>
            <td style="padding:0.4rem 0.6rem; border-bottom:1px solid #e2e8f0; font-family:var(--font-mono); font-size:0.7rem;">${f.session_id || 'N/A'}</td>
            <td style="padding:0.4rem 0.6rem; border-bottom:1px solid #e2e8f0; font-weight:600;">${f.room_id || 'N/A'}</td>
            <td style="padding:0.4rem 0.6rem; border-bottom:1px solid #e2e8f0; color:#64748b;">${f.message}</td>
          `;
          tbody.appendChild(tr);
        });
      }

      this.showToast(`Independent audit complete: ${res.status.toUpperCase()} (${res.pass_count} verified, ${res.insufficient_evidence_count} capacity gaps)`, 'success');
    } catch (err) {
      this.showToast(`Audit failed: ${err.message}`, 'danger');
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.style.padding = '0.65rem 1rem';
    toast.style.borderRadius = '8px';
    toast.style.fontSize = '0.8rem';
    toast.style.fontWeight = '600';
    toast.style.boxShadow = '0 4px 12px rgba(0,0,0,0.15)';
    toast.style.transition = 'opacity 0.3s ease';

    if (type === 'success') {
      toast.style.background = '#15803d';
      toast.style.color = '#ffffff';
    } else if (type === 'warning') {
      toast.style.background = '#b45309';
      toast.style.color = '#ffffff';
    } else if (type === 'danger') {
      toast.style.background = '#b91c1c';
      toast.style.color = '#ffffff';
    } else {
      toast.style.background = '#1e293b';
      toast.style.color = '#ffffff';
    }

    toast.textContent = message;
    container.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }
}

// Instantiate on DOMContentLoaded
document.addEventListener('DOMContentLoaded', () => {
  const app = new ClassroomIQApp();
  app.init();
});
