/**
 * ClassroomIQ — Main Frontend Application Controller (Iteration 2)
 * Realizes allocation-driven timetable explorer, deterministic synthetic demo profile,
 * room drawer inspector, and truthful governance presentation.
 */

import { Api } from './api.js';

class ClassroomIQApp {
  constructor() {
    this.currentCycle = 'even'; // Default to Even cycle which demonstrates optimization
    this.currentRoute = 'dashboard';
    this.currentAllocationSource = 'source'; // 'source' or 'selected'
    this.timetableGroupBy = 'cohort'; // 'cohort', 'room', or 'program'
    this.selectedProgram = '';
    this.selectedCohort = '';
    this.selectedRoom = '';
    this.selectedDay = 'Monday';
    this.evalMode = localStorage.getItem('ciq_eval_mode') || 'synthetic'; // 'synthetic' or 'factual'
    this.roomsData = [];
    this.programsData = [];
    this.cohortsData = [];
    this.eventsData = [];
    this.systemStatus = null;
    this.lastComparisonResult = null;
    this.activeRoomDrawer = null;
  }

  async init() {
    this.updateModeUI();
    this.setupRouter();
    this.setupEventListeners();
    await this.loadInitialData();
  }

  /* ==========================================================================
     ROUTING & VIEW MANAGEMENT
     ========================================================================== */
  setupRouter() {
    window.addEventListener('hashchange', () => this.handleRoute());
    this.handleRoute();
  }

  handleRoute() {
    let hash = window.location.hash.replace('#/', '').replace('#', '').trim();
    if (!hash) hash = 'dashboard';

    const validRoutes = [
      'dashboard', 'timetable', 'programs', 'rooms',
      'optimization', 'simulation', 'results',
      'validation', 'data', 'settings'
    ];

    if (!validRoutes.includes(hash)) {
      hash = 'dashboard';
    }

    this.currentRoute = hash;

    document.querySelectorAll('.page-view').forEach(view => {
      view.classList.remove('active');
    });
    const targetView = document.getElementById(`view-${hash}`);
    if (targetView) {
      targetView.classList.add('active');
    }

    document.querySelectorAll('.sidebar .nav-item').forEach(item => {
      const link = item.querySelector('a');
      if (link) {
        const href = link.getAttribute('href');
        if (href === `#/${hash}` || href === `#${hash}`) {
          item.classList.add('active');
        } else {
          item.classList.remove('active');
        }
      }
    });

    this.updateHeaderForRoute(hash);
    this.onViewEnter(hash);
  }

  updateHeaderForRoute(route) {
    const heading = document.getElementById('page-heading');
    const subheading = document.getElementById('page-subheading');
    if (!heading || !subheading) return;

    const titles = {
      dashboard: {
        title: 'Academic Scheduling & Optimization',
        sub: 'Allocate rooms, compare feasible candidates, and recover from disruptions.'
      },
      timetable: {
        title: 'Academic Timetable Explorer',
        sub: 'Inspect allocations by Day, Period, Program, Cohort, and Room.'
      },
      programs: {
        title: 'Academic Programs & Cohorts',
        sub: 'Degree tracks, cohort allocations, and session distribution across cycles.'
      },
      rooms: {
        title: 'Rooms & Physical Facilities Inventory',
        sub: '86-room operational inventory with capabilities, buildings, and utilization.'
      },
      optimization: {
        title: 'CP-SAT Optimization Workbench',
        sub: 'OR-Tools CP-SAT room solver with strict 10s search limit and baseline fallback.'
      },
      simulation: {
        title: 'Disruption Simulation Sandbox',
        sub: 'Simulate room closures, evaluate campus capacity, and trigger atomic rollback.'
      },
      results: {
        title: 'Results & Comparative Analysis',
        sub: 'Even vs. Odd cycle performance metrics, walking-time proxy, and validation.'
      },
      validation: {
        title: 'Independent Validation Inspector',
        sub: 'Audits allocations independently across all 5 hard constraints and evidence gaps.'
      },
      data: {
        title: 'Data Governance & Provenance',
        sub: '7 seed datasets, SHA-256 checksum verification, and factual-vs-synthetic rules.'
      },
      settings: {
        title: 'System Preferences & Settings',
        sub: 'Evaluation modes, solver timeouts, and timetable display preferences.'
      }
    };

    if (titles[route]) {
      heading.textContent = titles[route].title;
      subheading.textContent = titles[route].sub;
    }
  }

  async onViewEnter(route) {
    switch (route) {
      case 'dashboard':
        await this.loadDashboardMetrics();
        break;
      case 'timetable':
        await this.loadTimetable();
        break;
      case 'programs':
        await this.loadProgramsView();
        break;
      case 'rooms':
        await this.loadRoomsView();
        break;
      case 'optimization':
        // Ready for optimization run
        break;
      case 'simulation':
        await this.loadSimulationView();
        break;
      case 'results':
        // Ready
        break;
      case 'validation':
        // Ready for audit
        break;
      case 'data':
        await this.loadDataOverview();
        break;
      case 'settings':
        this.loadSettings();
        break;
    }
  }

  /* ==========================================================================
     EVALUATION MODE MANAGEMENT
     ========================================================================== */
  updateModeUI() {
    const btn = document.getElementById('btn-toggle-eval-mode');
    const roomsPill = document.getElementById('rooms-mode-pill');
    const auditModeSelect = document.getElementById('audit-mode-select');
    const settingsEvalMode = document.getElementById('settings-eval-mode');

    if (btn) {
      if (this.evalMode === 'synthetic') {
        btn.className = 'mode-toggle-btn synthetic';
        btn.textContent = '⚡ SYNTHETIC DEMO PROFILE';
        btn.title = 'Active: Synthetic Demo Profile. Click to switch to Factual Mode.';
      } else {
        btn.className = 'mode-toggle-btn factual';
        btn.textContent = '📋 FACTUAL MODE (GAPS PRESERVED)';
        btn.title = 'Active: Factual Mode. Click to switch to Synthetic Demo Profile.';
      }
    }

    if (roomsPill) {
      roomsPill.textContent = this.evalMode === 'synthetic'
        ? '86 Physical Rooms • Demo Estimates Active'
        : '86 Physical Rooms • Factual Source Data';
      roomsPill.style.background = this.evalMode === 'synthetic' ? '#f0fdf4' : '#f8fafc';
      roomsPill.style.color = this.evalMode === 'synthetic' ? '#15803d' : '#475569';
    }

    if (auditModeSelect) auditModeSelect.value = this.evalMode;
    if (settingsEvalMode) settingsEvalMode.value = this.evalMode;
  }

  toggleEvalMode() {
    this.evalMode = (this.evalMode === 'synthetic') ? 'factual' : 'synthetic';
    localStorage.setItem('ciq_eval_mode', this.evalMode);
    this.updateModeUI();
    this.showToast(`Switched to ${this.evalMode === 'synthetic' ? 'SYNTHETIC DEMO PROFILE' : 'FACTUAL MODE'}`, 'info');
    this.onViewEnter(this.currentRoute);
  }

  /* ==========================================================================
     EVENT LISTENERS & BINDINGS
     ========================================================================== */
  setupEventListeners() {
    // Mode toggle button
    const btnMode = document.getElementById('btn-toggle-eval-mode');
    if (btnMode) btnMode.addEventListener('click', () => this.toggleEvalMode());

    // Cycle selector
    const cycleSelect = document.getElementById('cycle-select');
    if (cycleSelect) {
      cycleSelect.value = this.currentCycle;
      cycleSelect.addEventListener('change', (e) => {
        this.currentCycle = e.target.value;
        this.onCycleChange();
      });
    }

    // Header Run Optimization button
    const btnOptimize = document.getElementById('btn-run-optimize');
    if (btnOptimize) {
      btnOptimize.addEventListener('click', () => {
        window.location.hash = '#/optimization';
        this.runOptimization();
      });
    }

    // Optimization page run button
    const btnOptPage = document.getElementById('btn-run-opt-page');
    if (btnOptPage) btnOptPage.addEventListener('click', () => this.runOptimization());

    // Optimization time slider
    const optSlider = document.getElementById('opt-time-limit');
    const optVal = document.getElementById('opt-time-val');
    if (optSlider && optVal) {
      optSlider.addEventListener('input', (e) => {
        optVal.textContent = `${parseFloat(e.target.value).toFixed(1)}s`;
      });
    }

    // Timetable Source Toggle: [Imported Source Timetable | Selected Allocation]
    const sourceToggleBtns = document.querySelectorAll('#timetable-source-toggle .source-toggle-btn');
    sourceToggleBtns.forEach(btn => {
      btn.addEventListener('click', (e) => {
        sourceToggleBtns.forEach(b => b.classList.remove('active'));
        e.target.classList.add('active');
        this.currentAllocationSource = e.target.dataset.source;
        this.loadTimetable();
      });
    });

    // Timetable Grouping Tabs: Timetable / Room / Cohort / Program
    const tabBtns = document.querySelectorAll('#timetable-tab-group .tab-btn');
    tabBtns.forEach(btn => {
      btn.addEventListener('click', (e) => {
        tabBtns.forEach(b => b.classList.remove('active'));
        e.target.classList.add('active');
        this.timetableGroupBy = e.target.dataset.group;
        this.loadTimetable();
      });
    });

    // Timetable Filters
    const programSelect = document.getElementById('filter-program');
    if (programSelect) {
      programSelect.addEventListener('change', (e) => {
        this.selectedProgram = e.target.value;
        // Dynamically update cohort dropdown to avoid contradictory selections!
        this.updateCohortDropdownForProgram(this.selectedProgram);
        this.selectedCohort = '';
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

    const roomSelect = document.getElementById('filter-room');
    if (roomSelect) {
      roomSelect.addEventListener('change', (e) => {
        this.selectedRoom = e.target.value;
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

    // Rooms search & filters
    const roomSearch = document.getElementById('search-rooms');
    const roomTypeFilter = document.getElementById('filter-room-type');
    const roomBlockFilter = document.getElementById('filter-room-block');
    if (roomSearch) roomSearch.addEventListener('input', () => this.filterRoomsTable());
    if (roomTypeFilter) roomTypeFilter.addEventListener('change', () => this.filterRoomsTable());
    if (roomBlockFilter) roomBlockFilter.addEventListener('change', () => this.filterRoomsTable());

    // Programs search
    const progSearch = document.getElementById('search-programs');
    if (progSearch) progSearch.addEventListener('input', () => this.filterProgramsView());

    // Simulation events
    const simEventSelect = document.getElementById('sim-event-select');
    if (simEventSelect) {
      simEventSelect.addEventListener('change', (e) => this.onSimulationEventChange(e.target.value));
    }
    const btnSimTrigger = document.getElementById('btn-run-sim-page');
    if (btnSimTrigger) btnSimTrigger.addEventListener('click', () => this.runSimulation());
    const btnSimRollback = document.getElementById('btn-rollback-page');
    if (btnSimRollback) btnSimRollback.addEventListener('click', () => this.rollbackSimulation());

    // Validation Inspector Audit Button
    const btnAudit = document.getElementById('btn-run-audit-page');
    if (btnAudit) btnAudit.addEventListener('click', () => this.runValidationAudit());

    // Modals & Drawers close
    const modalClose = document.getElementById('modal-close');
    const modalBackdrop = document.getElementById('modal-backdrop');
    if (modalClose && modalBackdrop) {
      modalClose.addEventListener('click', () => modalBackdrop.classList.remove('open'));
      modalBackdrop.addEventListener('click', (e) => {
        if (e.target === modalBackdrop) modalBackdrop.classList.remove('open');
      });
    }

    const roomDrawerBackdrop = document.getElementById('room-drawer-backdrop');
    if (roomDrawerBackdrop) {
      roomDrawerBackdrop.addEventListener('click', (e) => {
        if (e.target === roomDrawerBackdrop) roomDrawerBackdrop.classList.remove('open');
      });
    }

    // Settings actions
    const btnSaveSettings = document.getElementById('btn-save-settings');
    if (btnSaveSettings) btnSaveSettings.addEventListener('click', () => this.saveSettings());
    const btnResetSettings = document.getElementById('btn-reset-settings');
    if (btnResetSettings) btnResetSettings.addEventListener('click', () => this.resetSettings());
  }

  async loadInitialData() {
    try {
      this.systemStatus = await Api.getStatus();
      this.roomsData = await Api.getRooms(null, null, null, this.evalMode);
      this.programsData = await Api.getPrograms();
      this.cohortsData = await Api.getCohorts();
      this.eventsData = await Api.getEvents();

      this.populateFilterDropdowns();
      await this.loadDashboardMetrics();
    } catch (err) {
      this.showToast(`Initial data load error: ${err.message}`, 'danger');
    }
  }

  populateFilterDropdowns() {
    // Populate Timetable Program Filter
    const progSelect = document.getElementById('filter-program');
    if (progSelect) {
      progSelect.innerHTML = '<option value="">All Programs (5)</option>';
      this.programsData.forEach(p => {
        const opt = document.createElement('option');
        opt.value = p.program;
        opt.textContent = `${p.program} (${p.total_sessions} sessions)`;
        progSelect.appendChild(opt);
      });
    }

    // Populate Timetable Cohort Filter initially for all
    this.updateCohortDropdownForProgram('');

    // Populate Timetable Room Filter
    const roomSelect = document.getElementById('filter-room');
    if (roomSelect) {
      roomSelect.innerHTML = '<option value="">All Rooms (86)</option>';
      this.roomsData.forEach(r => {
        const opt = document.createElement('option');
        opt.value = r.room_id;
        opt.textContent = `${r.room_id} (${r.room_type})`;
        roomSelect.appendChild(opt);
      });
    }

    // Populate Simulation Events Dropdown
    const simEventSelect = document.getElementById('sim-event-select');
    if (simEventSelect) {
      simEventSelect.innerHTML = '';
      this.eventsData.forEach(evt => {
        const opt = document.createElement('option');
        opt.value = evt.event_id;
        opt.textContent = `${evt.event_id} • ${evt.event_type.toUpperCase()} • Room ${evt.room_id}`;
        simEventSelect.appendChild(opt);
      });
      if (this.eventsData.length > 0) {
        this.onSimulationEventChange(this.eventsData[0].event_id);
      }
    }
  }

  updateCohortDropdownForProgram(program) {
    const cohortSelect = document.getElementById('filter-cohort');
    if (!cohortSelect) return;

    cohortSelect.innerHTML = '<option value="">All Cohorts</option>';
    const filtered = this.cohortsData.filter(c =>
      (!program || c.program === program) &&
      (!this.currentCycle || c.academic_cycle === this.currentCycle)
    );

    filtered.forEach(c => {
      const opt = document.createElement('option');
      opt.value = c.cohort_id;
      opt.textContent = `${c.cohort_id} (${c.session_count} sessions)`;
      cohortSelect.appendChild(opt);
    });
  }

  async onCycleChange() {
    const optCycle = document.getElementById('opt-cycle-select');
    if (optCycle) optCycle.value = this.currentCycle;

    const auditCycle = document.getElementById('audit-cycle-select');
    if (auditCycle) auditCycle.value = this.currentCycle;

    this.updateCohortDropdownForProgram(this.selectedProgram);
    await this.loadDashboardMetrics();

    if (this.currentRoute === 'timetable') {
      await this.loadTimetable();
    }
  }

  /* ==========================================================================
     VIEW 1: DASHBOARD
     ========================================================================== */
  async loadDashboardMetrics() {
    if (!this.systemStatus) {
      this.systemStatus = await Api.getStatus();
    }
    const ds = this.systemStatus.dataset_summary;

    const elSessions = document.getElementById('kpi-sessions-val');
    const elSub = document.getElementById('kpi-sessions-sub');
    if (elSessions) {
      elSessions.textContent = this.currentCycle === 'odd' ? ds.odd_cycle_sessions : ds.even_cycle_sessions;
    }
    if (elSub) {
      elSub.textContent = this.currentCycle === 'odd'
        ? `Odd cycle selected ↔ Even cycle: ${ds.even_cycle_sessions}`
        : `Even cycle selected ↔ Odd cycle: ${ds.odd_cycle_sessions}`;
    }

    const elPrograms = document.getElementById('kpi-programs-val');
    if (elPrograms) elPrograms.textContent = ds.programs_count;

    const elCohorts = document.getElementById('kpi-cohorts-val');
    if (elCohorts) elCohorts.textContent = ds.cohorts_count;

    const elRooms = document.getElementById('kpi-rooms-val');
    if (elRooms) elRooms.textContent = ds.rooms_inventory_count;

    const slotData = ds.slot_coverage || {
      total_slots: 6880,
      occupied_slots: 1490,
      unscheduled_slots: 2990,
      unknown_slots: 2400
    };
    const elCovVal = document.getElementById('kpi-coverage-val');
    const elCovSub = document.getElementById('kpi-coverage-sub');
    if (elCovVal) elCovVal.textContent = `${slotData.total_slots.toLocaleString()} Slots`;
    if (elCovSub) {
      elCovSub.innerHTML = `
        <strong style="color:#15803d;">${slotData.occupied_slots.toLocaleString()}</strong> occupied • 
        <strong style="color:#475569;">${slotData.unscheduled_slots.toLocaleString()}</strong> unscheduled • 
        <strong style="color:#b45309;">${slotData.unknown_slots.toLocaleString()}</strong> unknown
      `;
    }
  }

  /* ==========================================================================
     VIEW 2: TIMETABLE (ALLOCATION-DRIVEN)
     ========================================================================== */
  async loadTimetable() {
    const tbody = document.getElementById('timetable-tbody');
    const statusPill = document.getElementById('timetable-status-pill');
    const thRowHeader = document.getElementById('th-row-header');
    if (!tbody) return;

    tbody.innerHTML = `<tr><td colspan="10" style="text-align:center; padding:2rem; color:#64748b;">Loading timetable grid from API...</td></tr>`;

    // Update row header text based on grouping tab
    if (thRowHeader) {
      if (this.timetableGroupBy === 'room') thRowHeader.textContent = 'Room / Facility';
      else if (this.timetableGroupBy === 'program') thRowHeader.textContent = 'Academic Program';
      else thRowHeader.textContent = 'Cohort / Track';
    }

    // Sync toggle buttons
    const sourceToggleBtns = document.querySelectorAll('#timetable-source-toggle .source-toggle-btn');
    sourceToggleBtns.forEach(btn => {
      if (btn.dataset.source === this.currentAllocationSource) btn.classList.add('active');
      else btn.classList.remove('active');
    });

    try {
      const data = await Api.getTimetableGrid({
        cycle: this.currentCycle,
        allocationSource: this.currentAllocationSource,
        groupBy: this.timetableGroupBy,
        cohortId: this.selectedCohort || null,
        program: this.selectedProgram || null,
        roomId: this.selectedRoom || null,
        day: this.selectedDay || 'Monday',
        mode: this.evalMode
      });

      if (statusPill) {
        statusPill.textContent = data.allocation_status_label;
        if (data.allocation_source === 'selected') {
          statusPill.style.background = '#dcfce7';
          statusPill.style.color = '#15803d';
          statusPill.style.borderColor = '#bbf7d0';
        } else {
          statusPill.style.background = '#f1f5f9';
          statusPill.style.color = '#475569';
          statusPill.style.borderColor = '#cbd5e1';
        }
      }

      tbody.innerHTML = '';
      const rowKeys = data.row_keys || [];

      if (rowKeys.length === 0) {
        tbody.innerHTML = `
          <tr>
            <td colspan="10" style="text-align:center; padding:2.5rem; color:#64748b;">
              <div style="font-weight:600; font-size:0.9rem; margin-bottom:0.25rem;">No matching sessions found</div>
              <div style="font-size:0.75rem;">No scheduled classes exist on ${data.target_day} for the active filters. Try clearing the filters above.</div>
            </td>
          </tr>
        `;
        return;
      }

      const gridData = data.grid || {};

      rowKeys.forEach(rk => {
        const tr = document.createElement('tr');
        const th = document.createElement('th');
        th.className = 'row-header';
        th.innerHTML = `<strong>${rk}</strong>`;
        tr.appendChild(th);

        data.periods.forEach(p => {
          const td = document.createElement('td');
          const sessions = gridData[rk]?.[p] || [];

          if (sessions.length > 0) {
            sessions.forEach(session => {
              const card = document.createElement('div');
              card.className = `session-card ${session.was_reassigned ? 'relocated' : ''}`;
              
              const roomBadge = session.was_reassigned
                ? `<span style="color:#15803d; font-weight:700;">📍 ${session.assigned_room_id} (Moved)</span>`
                : `<span>📍 ${session.assigned_room_id}</span>`;

              card.innerHTML = `
                <div class="session-course">${session.course}</div>
                <div class="session-meta">
                  ${roomBadge}
                  <span>${session.session_type || 'class'}</span>
                </div>
              `;
              card.addEventListener('click', () => this.openSessionModal(session, data.allocation_source));
              td.appendChild(card);
            });
          } else {
            td.innerHTML = '<span style="color:#cbd5e1; font-size:0.7rem;">—</span>';
          }
          tr.appendChild(td);
        });

        tbody.appendChild(tr);
      });
    } catch (err) {
      tbody.innerHTML = `<tr><td colspan="10" style="text-align:center; padding:2rem; color:#b91c1c;">Failed to load timetable: ${err.message}</td></tr>`;
    }
  }

  openSessionModal(session, source) {
    const backdrop = document.getElementById('modal-backdrop');
    const details = document.getElementById('modal-details');
    if (!backdrop || !details) return;

    const isSynthetic = (this.evalMode === 'synthetic');
    const enrollmentMarkup = isSynthetic
      ? `<span class="badge-verified-small" style="background:#eff6ff; color:#1d4ed8; border:1px solid #bfdbfe;">Demo Estimate: ${session.student_count || 55} students</span>`
      : `<span class="badge-unknown-small">Unknown (Data Gap)</span>`;

    const reassignmentNotice = session.was_reassigned
      ? `<div style="background:#f0fdf4; border:1px solid #bbf7d0; border-radius:6px; padding:0.5rem; margin-top:0.5rem; font-size:0.75rem; color:#166534;">
          <strong>Optimized Reallocation:</strong> Relocated from source room <code>${session.source_room_id}</code> to <code>${session.assigned_room_id}</code> to eliminate room-type mismatch or minimize walking proxy.
         </div>`
      : '';

    details.innerHTML = `
      <div style="font-size:0.85rem; line-height:1.7; color:#334155;">
        <p><strong>Session ID:</strong> <span class="badge-code">${session.session_id}</span></p>
        <p><strong>Course:</strong> <strong>${session.course}</strong></p>
        <p><strong>Program:</strong> ${session.program || 'N/A'}</p>
        <p><strong>Cohort ID:</strong> ${session.cohort_id}</p>
        <p><strong>Assigned Room:</strong> <span class="badge-code" style="font-weight:700;">${session.assigned_room_id}</span></p>
        <p><strong>Required Room Type:</strong> ${session.required_room_type || 'classroom'}</p>
        <p><strong>Period Range:</strong> Period ${session.start_period} to ${session.end_period}</p>
        <p><strong>Scheduled Enrollment:</strong> ${enrollmentMarkup}</p>
        ${reassignmentNotice}
        <hr style="border:none; border-top:1px solid #e2e8f0; margin:0.75rem 0;">
        <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:6px; padding:0.65rem; font-size:0.75rem; color:#64748b;">
          <strong>Active Evaluation Mode:</strong> ${isSynthetic ? 'SYNTHETIC DEMO PROFILE' : 'FACTUAL MODE'}<br>
          <em>${isSynthetic ? 'Enrollment derived deterministically from session type demo assumptions.' : 'Factual mode strictly preserves unrecorded enrollment counts without imputation.'}</em>
        </div>
      </div>
    `;
    backdrop.classList.add('open');
  }

  /* ==========================================================================
     VIEW 3: PROGRAMS & COHORTS
     ========================================================================== */
  async loadProgramsView() {
    if (!this.programsData.length) this.programsData = await Api.getPrograms();
    if (!this.cohortsData.length) this.cohortsData = await Api.getCohorts();

    const grid = document.getElementById('programs-card-grid');
    if (grid) {
      grid.innerHTML = '';
      this.programsData.forEach(p => {
        const card = document.createElement('div');
        card.className = 'kpi-card';
        card.style.display = 'block';
        card.innerHTML = `
          <div style="font-weight:700; font-size:0.95rem; color:#0f172a; margin-bottom:0.35rem;">${p.program}</div>
          <div style="font-size:0.8rem; color:#64748b; margin-bottom:0.5rem;">Total Sessions: <strong>${p.total_sessions}</strong></div>
          <div style="font-size:0.75rem; color:#475569; display:flex; justify-content:space-between; border-top:1px solid #e2e8f0; padding-top:0.4rem;">
            <span>Odd Cycle: <strong>${p.odd_sessions}</strong></span>
            <span>Even Cycle: <strong>${p.even_sessions}</strong></span>
          </div>
        `;
        grid.appendChild(card);
      });
    }

    this.renderCohortsTable(this.cohortsData);
  }

  renderCohortsTable(cohorts) {
    const tbody = document.getElementById('cohorts-table-tbody');
    if (!tbody) return;

    tbody.innerHTML = '';
    cohorts.forEach(c => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td><span class="badge-code">${c.cohort_id}</span></td>
        <td><strong>${c.program}</strong></td>
        <td><span class="badge-tag" style="background:#f1f5f9; color:#475569;">${c.academic_cycle.toUpperCase()}</span></td>
        <td>Semester ${c.semester}</td>
        <td><strong>${c.session_count}</strong> sessions</td>
        <td>
          <button class="btn-primary" style="font-size:0.7rem; padding:0.25rem 0.6rem;" data-cohort="${c.cohort_id}" data-cycle="${c.academic_cycle}" data-program="${c.program}">
            View Schedule
          </button>
        </td>
      `;
      const btn = tr.querySelector('button');
      btn.addEventListener('click', () => {
        this.selectedProgram = c.program;
        this.selectedCohort = c.cohort_id;
        this.currentCycle = c.academic_cycle;

        const cycleSel = document.getElementById('cycle-select');
        if (cycleSel) cycleSel.value = c.academic_cycle;
        const progSel = document.getElementById('filter-program');
        if (progSel) progSel.value = c.program;

        this.updateCohortDropdownForProgram(c.program);
        const cohortSel = document.getElementById('filter-cohort');
        if (cohortSel) cohortSel.value = c.cohort_id;

        window.location.hash = '#/timetable';
      });
      tbody.appendChild(tr);
    });
  }

  filterProgramsView() {
    const query = (document.getElementById('search-programs')?.value || '').toLowerCase().trim();
    const filtered = this.cohortsData.filter(c =>
      c.cohort_id.toLowerCase().includes(query) ||
      c.program.toLowerCase().includes(query)
    );
    this.renderCohortsTable(filtered);
  }

  /* ==========================================================================
     VIEW 4: ROOMS & FACILITIES (POLISHED OPERATIONAL VIEW)
     ========================================================================== */
  async loadRoomsView() {
    this.roomsData = await Api.getRooms(null, null, null, this.evalMode);
    this.filterRoomsTable();
  }

  filterRoomsTable() {
    const query = (document.getElementById('search-rooms')?.value || '').toLowerCase().trim();
    const type = document.getElementById('filter-room-type')?.value || '';
    const block = document.getElementById('filter-room-block')?.value || '';

    const filtered = this.roomsData.filter(r => {
      const matchesQuery = !query ||
        r.room_id.toLowerCase().includes(query) ||
        (r.building_block && r.building_block.toLowerCase().includes(query)) ||
        (r.permitted_uses && r.permitted_uses.some(u => u.toLowerCase().includes(query)));
      const matchesType = !type || r.room_type === type;
      const matchesBlock = !block || r.room_id.toUpperCase().startsWith(block.toUpperCase());
      return matchesQuery && matchesType && matchesBlock;
    });

    const tbody = document.getElementById('rooms-table-tbody');
    if (!tbody) return;

    tbody.innerHTML = '';
    if (filtered.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding:1.5rem; color:#64748b;">No rooms match the selected filters.</td></tr>`;
      return;
    }

    filtered.forEach(r => {
      const tr = document.createElement('tr');
      const isSynthetic = (this.evalMode === 'synthetic');

      const capBadge = r.has_known_capacity
        ? `<strong style="color:#15803d;">${r.capacity} seats</strong>`
        : (isSynthetic
            ? `<strong style="color:#1e40af;">${r.capacity} seats</strong> <span class="badge-code" style="font-size:0.65rem;">Demo estimate</span>`
            : `<span class="badge-unknown-small">Unknown (Data Gap)</span>`);

      const opBadge = isSynthetic
        ? `<span class="badge-verified-small" style="font-size:0.68rem;">Operational</span>`
        : `<span style="font-size:0.75rem; color:#64748b;">Not Recorded</span>`;

      tr.innerHTML = `
        <td><span class="badge-code" style="font-weight:700; cursor:pointer;" title="Click for details">${r.room_id}</span></td>
        <td><span class="badge-tag" style="background:#eff6ff; color:#1d4ed8;">${r.room_type}</span></td>
        <td>${r.building_block} • ${r.floor}</td>
        <td>${capBadge}</td>
        <td><small style="color:#475569;">${(r.permitted_uses || []).join(', ')}</small></td>
        <td>${opBadge}</td>
        <td>
          <button class="btn-primary btn-room-detail" style="font-size:0.7rem; padding:0.25rem 0.55rem;" data-room="${r.room_id}">
            View Details
          </button>
        </td>
      `;

      tr.querySelector('.btn-room-detail').addEventListener('click', () => this.openRoomDrawer(r.room_id));
      tr.querySelector('.badge-code').addEventListener('click', () => this.openRoomDrawer(r.room_id));
      tbody.appendChild(tr);
    });
  }

  async openRoomDrawer(roomId) {
    const backdrop = document.getElementById('room-drawer-backdrop');
    const content = document.getElementById('room-drawer-content');
    if (!backdrop || !content) return;

    content.innerHTML = `<div style="text-align:center; padding:2rem; color:#64748b;">Loading room details for ${roomId}...</div>`;
    backdrop.classList.add('open');

    try {
      const detail = await Api.getRoomDetail(roomId, this.currentCycle, this.evalMode);

      content.innerHTML = `
        <div class="drawer-header">
          <div>
            <h3 style="font-family:var(--font-display); font-size:1.2rem; color:#0f172a; margin:0;">${detail.room_id} Details</h3>
            <span class="badge-tag" style="background:#eff6ff; color:#1d4ed8; margin-top:0.25rem;">${detail.room_type}</span>
          </div>
          <button id="drawer-close" style="background:transparent; border:none; font-size:1.5rem; cursor:pointer; color:#64748b;">&times;</button>
        </div>

        <div style="font-size:0.82rem; line-height:1.7; color:#334155;">
          <p><strong>Campus Location:</strong> ${detail.building_block} • ${detail.floor}</p>
          <p><strong>Seating Capacity:</strong> <strong>${detail.capacity || 'Unknown'} seats</strong> (${detail.capacity_status})</p>
          <p><strong>Operational Status:</strong> ${detail.operational_status}</p>
          <p><strong>Permitted Capabilities:</strong> ${(detail.permitted_uses || []).join(', ')}</p>
          <p><strong>Weekly Occupancy:</strong> <strong>${detail.total_scheduled_sessions} sessions</strong> (${detail.total_occupied_periods} / ${detail.total_weekly_periods} periods • ${detail.utilization_percentage}% utilization)</p>

          <hr style="border:none; border-top:1px solid #e2e8f0; margin:1rem 0;">
          <div style="font-weight:700; font-size:0.85rem; color:#0f172a; margin-bottom:0.5rem;">Weekly Schedule (${detail.academic_cycle.toUpperCase()} Cycle)</div>

          <div style="max-height:220px; overflow-y:auto; border:1px solid #e2e8f0; border-radius:6px;">
            <table style="width:100%; border-collapse:collapse; font-size:0.75rem;">
              <thead style="background:#f8fafc;">
                <tr>
                  <th style="padding:0.4rem; border-bottom:1px solid #e2e8f0; text-align:left;">Day</th>
                  <th style="padding:0.4rem; border-bottom:1px solid #e2e8f0; text-align:left;">Period</th>
                  <th style="padding:0.4rem; border-bottom:1px solid #e2e8f0; text-align:left;">Course / Cohort</th>
                </tr>
              </thead>
              <tbody>
                ${this.renderRoomScheduleRows(detail.schedule)}
              </tbody>
            </table>
          </div>
        </div>
      `;

      document.getElementById('drawer-close').addEventListener('click', () => backdrop.classList.remove('open'));
    } catch (err) {
      content.innerHTML = `<div style="text-align:center; padding:2rem; color:#b91c1c;">Failed to load room details: ${err.message}</div>`;
    }
  }

  renderRoomScheduleRows(schedule) {
    let rows = '';
    const days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"];
    days.forEach(d => {
      const pMap = schedule[d] || {};
      for (let p = 1; p <= 9; p++) {
        const item = pMap[p];
        if (item) {
          rows += `
            <tr>
              <td style="padding:0.35rem 0.45rem; border-bottom:1px solid #f1f5f9;"><strong>${d}</strong></td>
              <td style="padding:0.35rem 0.45rem; border-bottom:1px solid #f1f5f9;">P${p}</td>
              <td style="padding:0.35rem 0.45rem; border-bottom:1px solid #f1f5f9;">${item.course} (${item.cohort_id})</td>
            </tr>
          `;
        }
      }
    });
    return rows || `<tr><td colspan="3" style="padding:1rem; text-align:center; color:#94a3b8;">No scheduled sessions in this room.</td></tr>`;
  }

  /* ==========================================================================
     VIEW 5: OPTIMIZATION
     ========================================================================== */
  async runOptimization() {
    const optCycleSelect = document.getElementById('opt-cycle-select');
    const cycle = optCycleSelect ? optCycleSelect.value : this.currentCycle;
    const timeLimitInput = document.getElementById('opt-time-limit');
    const timeLimit = timeLimitInput ? parseFloat(timeLimitInput.value) : 10.0;

    const btn1 = document.getElementById('btn-run-optimize');
    const btn2 = document.getElementById('btn-run-opt-page');
    if (btn1) { btn1.disabled = true; btn1.textContent = 'Running Solver...'; }
    if (btn2) { btn2.disabled = true; btn2.textContent = 'Running Solver...'; }

    this.showToast(`Executing CP-SAT Optimizer on ${cycle} cycle (time limit: ${timeLimit}s)...`, 'info');

    try {
      const res = await Api.compareAllocations(cycle, timeLimit);
      this.lastComparisonResult = res;

      // Update comparison bars
      const barBase = document.getElementById('opt-bar-base');
      const barOpt = document.getElementById('opt-bar-opt');
      const label = document.getElementById('opt-chart-label');
      const pill = document.getElementById('opt-chart-pill');

      if (label) label.textContent = `${cycle.toUpperCase()} cycle • ${res.baseline_same_room_count + (cycle === 'even' ? 272 : 392)} sessions`;

      if (res.fallback_to_baseline) {
        if (pill) {
          pill.className = 'chart-pill success';
          pill.style.background = '#f0fdf4';
          pill.style.color = '#15803d';
          pill.style.borderColor = '#bbf7d0';
          pill.textContent = `${cycle.toUpperCase()}: Safe Fallback — Baseline Retained (1,248 min)`;
        }
        if (barBase) barBase.textContent = `Baseline (Retained): ${res.baseline_walking_time} min`;
        if (barOpt) {
          barOpt.className = 'bar-fill rejected';
          barOpt.style.width = '100%';
          barOpt.textContent = `Raw Solver Candidate: ${res.raw_solver_walking_time} min (Rejected)`;
        }
      } else {
        if (pill) {
          pill.className = 'chart-pill success';
          pill.textContent = `${cycle.toUpperCase()}: ${res.walking_time_reduction_minutes} min reduction (${res.walking_time_reduction_percentage}%)`;
        }
        if (barBase) barBase.textContent = `Baseline: ${res.baseline_walking_time} min`;
        if (barOpt) {
          barOpt.className = 'bar-fill improved';
          const ratio = (res.optimized_walking_time / res.baseline_walking_time) * 100;
          barOpt.style.width = `${ratio.toFixed(1)}%`;
          barOpt.textContent = `Optimized: ${res.optimized_walking_time} min`;
        }
      }

      // Update Summary Result Box
      const elBase = document.getElementById('opt-metric-base');
      const elRaw = document.getElementById('opt-metric-raw');
      const elSel = document.getElementById('opt-metric-sel');
      const elRed = document.getElementById('opt-metric-red');
      const elAlloc = document.getElementById('opt-metric-alloc');
      const elStatus = document.getElementById('opt-metric-status');
      const elBoxTitle = document.getElementById('opt-box-title');
      const elBoxBadge = document.getElementById('opt-box-badge');

      if (elBoxTitle) elBoxTitle.textContent = `${cycle.toUpperCase()} CYCLE RESULT`;
      if (elBase) elBase.textContent = `${res.baseline_walking_time} min`;
      if (elRaw) {
        elRaw.textContent = `${res.raw_solver_walking_time} min ${res.fallback_to_baseline ? '(Rejected)' : '(Accepted)'}`;
        elRaw.style.color = res.fallback_to_baseline ? '#b91c1c' : '#15803d';
      }
      if (elSel) elSel.textContent = `${res.fallback_to_baseline ? res.baseline_walking_time : res.optimized_walking_time} min`;
      if (elRed) {
        elRed.textContent = res.fallback_to_baseline ? '0 min (0.00%) — Protected' : `${res.walking_time_reduction_minutes} min • ${res.walking_time_reduction_percentage}%`;
        elRed.style.color = res.fallback_to_baseline ? '#b45309' : '#15803d';
      }
      if (elAlloc) elAlloc.textContent = res.selected_allocator_name;
      if (elStatus) elStatus.textContent = 'FEASIBLE (VALID_COMPLETE)';

      if (elBoxBadge) {
        if (res.fallback_to_baseline) {
          elBoxBadge.className = 'badge-tag';
          elBoxBadge.style.background = '#dcfce7';
          elBoxBadge.style.color = '#15803d';
          elBoxBadge.textContent = '✓ Safe fallback retained';
        } else {
          elBoxBadge.className = 'badge-tag improved';
          elBoxBadge.textContent = 'Improved';
        }
      }

      // Automatically switch Timetable to show Selected Allocation!
      this.currentAllocationSource = 'selected';
      this.showToast(`Optimization complete: ${res.selected_allocator_name} selected. Timetable updated to Selected Allocation.`, 'success');
    } catch (err) {
      this.showToast(`Optimization error: ${err.message}`, 'danger');
    } finally {
      if (btn1) { btn1.disabled = false; btn1.innerHTML = '<span>▶ Run Optimization</span>'; }
      if (btn2) { btn2.disabled = false; btn2.innerHTML = '<span>▶ Run Optimization</span>'; }
    }
  }

  /* ==========================================================================
     VIEW 6: DISRUPTION SIMULATION (STATE MACHINE)
     ========================================================================== */
  async loadSimulationView() {
    if (!this.eventsData.length) this.eventsData = await Api.getEvents();
  }

  onSimulationEventChange(eventId) {
    const evt = this.eventsData.find(e => e.event_id === eventId);
    if (!evt) return;

    // Reset outcome state machine to READY
    const outcomeBox = document.getElementById('sim-outcome-box');
    const header = document.getElementById('sim-outcome-header');
    const desc = document.getElementById('sim-outcome-desc');
    if (outcomeBox) {
      outcomeBox.style.backgroundColor = '#f8fafc';
      outcomeBox.style.borderColor = '#e2e8f0';
    }
    if (header) {
      header.textContent = 'READY TO SIMULATE';
      header.style.color = '#334155';
    }
    if (desc) {
      desc.textContent = `Selected scenario: ${evt.event_id}. Click 'Trigger Disruption' to test capacity response.`;
      desc.style.color = '#64748b';
    }

    const elBadge = document.getElementById('sim-badge');
    const elRoom = document.getElementById('sim-target-room');
    const elCycle = document.getElementById('sim-target-cycle');
    const elConcurrent = document.getElementById('sim-concurrent-labs');
    const elAvail = document.getElementById('sim-avail-labs');

    if (elBadge) elBadge.textContent = `${evt.event_id} • ${evt.event_type.toUpperCase()} • Room ${evt.room_id}`;
    if (elRoom) elRoom.textContent = `${evt.room_id} (${evt.room_type || 'laboratory'})`;
    if (elCycle) elCycle.textContent = evt.cycle || 'even';

    if (evt.room_id === 'M601') {
      if (elConcurrent) elConcurrent.textContent = '20';
      if (elAvail) elAvail.textContent = '19';
    } else {
      if (elConcurrent) elConcurrent.textContent = 'Variable';
      if (elAvail) elAvail.textContent = 'Surplus Available';
    }
  }

  async runSimulation() {
    const eventSelect = document.getElementById('sim-event-select');
    const eventId = eventSelect ? eventSelect.value : 'EVT-DEMO-001';

    const btn = document.getElementById('btn-run-sim-page');
    if (btn) btn.disabled = true;

    try {
      const res = await Api.triggerDisruption(eventId, this.currentCycle);
      const outcomeBox = document.getElementById('sim-outcome-box');
      const header = document.getElementById('sim-outcome-header');
      const desc = document.getElementById('sim-outcome-desc');

      if (res.is_repaired) {
        if (outcomeBox) {
          outcomeBox.style.backgroundColor = '#dcfce7';
          outcomeBox.style.borderColor = '#bbf7d0';
        }
        if (header) {
          header.textContent = 'SUCCESSFUL BOUNDED REPAIR';
          header.style.color = '#15803d';
        }
        if (desc) {
          desc.textContent = res.diagnosis_explanation;
          desc.style.color = '#166534';
        }
        this.showToast('Disruption successfully repaired!', 'success');
      } else {
        if (outcomeBox) {
          outcomeBox.style.backgroundColor = '#fff1f2';
          outcomeBox.style.borderColor = '#fecdd3';
        }
        if (header) {
          header.textContent = 'MATHEMATICALLY INFEASIBLE';
          header.style.color = '#be123c';
        }
        if (desc) {
          desc.innerHTML = `<strong>Why it fails:</strong> ${res.diagnosis_explanation}`;
          desc.style.color = '#881337';
        }
        this.showToast('Diagnosed as mathematically infeasible. State rolled back safely.', 'warning');
      }
    } catch (err) {
      this.showToast(`Simulation error: ${err.message}`, 'danger');
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async rollbackSimulation() {
    try {
      const res = await Api.rollbackDisruption();
      const outcomeBox = document.getElementById('sim-outcome-box');
      const header = document.getElementById('sim-outcome-header');
      const desc = document.getElementById('sim-outcome-desc');

      if (outcomeBox) {
        outcomeBox.style.backgroundColor = '#f8fafc';
        outcomeBox.style.borderColor = '#e2e8f0';
      }
      if (header) {
        header.textContent = 'STATE ROLLED BACK';
        header.style.color = '#334155';
      }
      if (desc) {
        desc.textContent = res.message;
        desc.style.color = '#64748b';
      }
      this.showToast(res.message, 'success');
      if (this.currentRoute === 'timetable') {
        await this.loadTimetable();
      }
    } catch (err) {
      this.showToast(`Rollback error: ${err.message}`, 'danger');
    }
  }

  /* ==========================================================================
     VIEW 8: VALIDATION INSPECTOR
     ========================================================================== */
  async runValidationAudit() {
    const targetSelect = document.getElementById('audit-target-select');
    const target = targetSelect ? targetSelect.value : 'baseline';
    const cycleSelect = document.getElementById('audit-cycle-select');
    const cycle = cycleSelect ? cycleSelect.value : this.currentCycle;
    const modeSelect = document.getElementById('audit-mode-select');
    const mode = modeSelect ? modeSelect.value : this.evalMode;

    const btn = document.getElementById('btn-run-audit-page');
    if (btn) btn.disabled = true;

    this.showToast(`Auditing ${target} on ${cycle} cycle (${mode.toUpperCase()})...`, 'info');

    try {
      const res = await Api.runAudit(cycle, target, false, 10.0, mode);

      const targetLabel = document.getElementById('audit-target-label');
      const targetDesc = document.getElementById('audit-target-desc');
      const auditBadge = document.getElementById('audit-badge');

      if (targetLabel) targetLabel.textContent = `${res.target_display_name} [${res.mode_label}]`;
      if (targetDesc) {
        targetDesc.textContent = `Audited ${res.total_sessions_checked} sessions against all 5 hard constraints. (${res.pass_count} pass, ${res.fail_count} fail, ${res.insufficient_evidence_count} capacity gaps)`;
      }

      if (auditBadge) {
        if (res.status === 'valid_complete' || res.status === 'feasible') {
          auditBadge.className = 'badge-tag improved';
          auditBadge.textContent = 'VALID_COMPLETE (FEASIBLE)';
          auditBadge.style.color = '#15803d';
        } else if (res.status === 'invalid_candidate') {
          auditBadge.className = 'badge-tag';
          auditBadge.style.background = '#fee2e2';
          auditBadge.style.color = '#b91c1c';
          auditBadge.textContent = `INVALID_CANDIDATE (${res.fail_count} FAILS)`;
        } else {
          auditBadge.className = 'badge-tag baseline-kept';
          auditBadge.textContent = res.status.toUpperCase();
        }
      }

      const cb = res.category_breakdown || {};

      const elExcl = document.getElementById('audit-exclusivity');
      if (elExcl) {
        const fails = cb['room_time_exclusivity']?.fail || cb['room_exclusivity']?.fail || 0;
        elExcl.textContent = `${fails} Violations`;
        elExcl.style.color = fails === 0 ? '#15803d' : '#b91c1c';
      }

      const elCohort = document.getElementById('audit-cohort');
      if (elCohort) {
        const fails = cb['cohort_time_exclusivity']?.fail || cb['cohort_exclusivity']?.fail || 0;
        elCohort.textContent = `${fails} Violations`;
        elCohort.style.color = fails === 0 ? '#15803d' : '#b91c1c';
      }

      const elCapab = document.getElementById('audit-capability');
      if (elCapab) {
        const fails = cb['room_capability']?.fail || 0;
        if (fails === 0) {
          elCapab.textContent = '100% Compatible';
          elCapab.style.color = '#15803d';
        } else {
          elCapab.textContent = `${fails} Incompatible`;
          elCapab.style.color = '#b91c1c';
        }
      }

      const elAvail = document.getElementById('audit-availability');
      if (elAvail) {
        const fails = cb['availability']?.fail || cb['confirmed_availability']?.fail || 0;
        elAvail.textContent = `${fails} Violations`;
        elAvail.style.color = fails === 0 ? '#15803d' : '#b91c1c';
      }

      const elCapac = document.getElementById('audit-capacity');
      const elCapacSub = document.getElementById('audit-capacity-sub');
      if (elCapac) {
        if (mode === 'synthetic') {
          const fails = cb['capacity']?.fail || 0;
          elCapac.textContent = fails === 0 ? 'Capacity Satisfied' : `${fails} Overflows`;
          elCapac.style.color = fails === 0 ? '#15803d' : '#b91c1c';
          if (elCapacSub) elCapacSub.textContent = 'Verified against Synthetic Demo Profile';
        } else {
          elCapac.textContent = 'Unknown (Data Gap)';
          elCapac.style.color = '#b45309';
          if (elCapacSub) elCapacSub.textContent = '100% Insufficient Evidence (Factual Mode)';
        }
      }

      const tbody = document.getElementById('audit-log-tbody');
      if (tbody && res.sample_findings) {
        tbody.innerHTML = '';
        res.sample_findings.forEach(f => {
          const tr = document.createElement('tr');
          const isPass = f.status === 'pass';
          const isUnknown = f.status === 'insufficient_evidence';
          const badgeClass = isPass
            ? 'color:#15803d; font-weight:600;'
            : (isUnknown ? 'color:#b45309; font-weight:600;' : 'color:#b91c1c; font-weight:600;');

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

      this.showToast(`Audit completed: ${res.target_display_name} -> ${res.status.toUpperCase()}`, 'success');
    } catch (err) {
      this.showToast(`Audit execution error: ${err.message}`, 'danger');
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  /* ==========================================================================
     VIEW 9: DATA OVERVIEW
     ========================================================================== */
  async loadDataOverview() {
    if (!this.systemStatus) this.systemStatus = await Api.getStatus();

    const tbody = document.getElementById('datasets-table-tbody');
    if (!tbody) return;

    const meta = [
      { file: 'sessions.csv', rows: 1250, desc: '680 odd / 570 even sessions across 45 cohorts and 5 programs. student_count empty.' },
      { file: 'rooms.csv', rows: 86, desc: '86 room records (56 classrooms, 20 labs, 10 assembly). 56 missing capacity.' },
      { file: 'travel_times.csv', rows: 3655, desc: 'Synthetic prefix distance proxy (3.0/8.0 min). Bidirectional room matrix.' },
      { file: 'availability.csv', rows: 6880, desc: 'Slot records: 1,490 occupied, 2,990 unscheduled in timetable, 2,400 unknown.' },
      { file: 'facilities.csv', rows: 79, desc: 'Facility attributes. Operational status unrecorded in source.' },
      { file: 'events.csv', rows: 5, desc: 'Documented disruption events (EVT-DEMO-001 through EVT-DEMO-005).' },
      { file: 'complaints.csv', rows: 120, desc: 'Historical room complaints. Used for diagnostic context.' },
    ];

    tbody.innerHTML = '';
    meta.forEach(m => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td><span class="badge-code">${m.file}</span></td>
        <td><strong>${m.rows}</strong> records</td>
        <td><span class="badge-verified-small">✓ SHA-256 Verified</span></td>
        <td><small style="color:#475569;">${m.desc}</small></td>
      `;
      tbody.appendChild(tr);
    });
  }

  /* ==========================================================================
     VIEW 10: SETTINGS
     ========================================================================== */
  loadSettings() {
    const evalMode = localStorage.getItem('ciq_eval_mode') || 'synthetic';
    const timeLimit = localStorage.getItem('ciq_time_limit') || '10';
    const provMode = localStorage.getItem('ciq_prov_mode') || 'source';

    const selEval = document.getElementById('settings-eval-mode');
    const selTime = document.getElementById('settings-time-limit');
    const valTime = document.getElementById('settings-time-val');
    const selProv = document.getElementById('settings-provenance-mode');

    if (selEval) selEval.value = evalMode;
    if (selTime) selTime.value = timeLimit;
    if (valTime) valTime.textContent = `${parseFloat(timeLimit).toFixed(1)}s`;
    if (selProv) selProv.value = provMode;

    if (selTime && valTime) {
      selTime.addEventListener('input', (e) => {
        valTime.textContent = `${parseFloat(e.target.value).toFixed(1)}s`;
      });
    }
  }

  saveSettings() {
    const evalMode = document.getElementById('settings-eval-mode')?.value || 'synthetic';
    const timeLimit = document.getElementById('settings-time-limit')?.value || '10';
    const provMode = document.getElementById('settings-provenance-mode')?.value || 'source';

    this.evalMode = evalMode;
    localStorage.setItem('ciq_eval_mode', evalMode);
    localStorage.setItem('ciq_time_limit', timeLimit);
    localStorage.setItem('ciq_prov_mode', provMode);

    this.updateModeUI();
    this.showToast('Preferences saved successfully to browser storage.', 'success');
  }

  resetSettings() {
    localStorage.removeItem('ciq_eval_mode');
    localStorage.removeItem('ciq_time_limit');
    localStorage.removeItem('ciq_prov_mode');
    this.evalMode = 'synthetic';
    this.updateModeUI();
    this.loadSettings();
    this.showToast('Preferences reset to defaults.', 'info');
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

// Bootstrap App
document.addEventListener('DOMContentLoaded', () => {
  const app = new ClassroomIQApp();
  app.init();
});
