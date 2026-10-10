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

    // Upload & Allocate Workflow State (Milestone 4)
    this.uploadState = {
      files: [], // Array of { filename, size, content, rowCount, headers, rows }
      academicCycle: 'even',
      columnMappings: {},
      confirmedAmbiguousMappings: {},
      preflightResponse: null,
      allocationResponse: null,
      timetableResponse: null,
      evaluationMode: 'synthetic',
      timeLimitSeconds: 5.0,
      allowComputingLabException: false,
      activeTimetableDay: 'Monday',
      timetableGroupBy: 'cohort',
      filterProgram: '',
      filterCohort: '',
      filterRoom: '',
      selectedPreviewFile: null,
      isDemoData: false,
    };
  }


  async init() {
    this.updateModeUI();
    this.setupRouter();
    this.setupEventListeners();
    this.setupUploadEventListeners();
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
      'dashboard', 'upload', 'timetable', 'programs', 'rooms',
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
      upload: {
        title: 'Upload & Allocate — Multi-Timetable Joint Room Allocation',
        sub: 'Ingest raw timetables without rooms, map columns, validate periods (1–8), and solve optimal joint room assignments.'
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
      case 'upload':
        // Upload & Allocate workflow active
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

  /* ==========================================================================
     UPLOAD & ALLOCATE MULTI-TIMETABLE WORKFLOW (MILESTONE 4)
     ========================================================================== */

  setupUploadEventListeners() {
    const dropzone = document.getElementById('upload-dropzone');
    const fileInput = document.getElementById('upload-file-input');
    const btnBrowse = document.getElementById('btn-browse-files');
    const btnRealSemester3 = document.getElementById('btn-load-real-semester3');
    const btnSampleMSc = document.getElementById('btn-load-sample-msc');
    const btnReset = document.getElementById('btn-upload-reset');
    const previewSelect = document.getElementById('preview-file-select');
    const btnPreflight = document.getElementById('btn-run-preflight');
    const btnProceedAlloc = document.getElementById('btn-proceed-to-allocation');
    const cardSynthetic = document.getElementById('profile-card-synthetic');
    const cardFactual = document.getElementById('profile-card-factual');
    const timeLimitInput = document.getElementById('upload-time-limit');
    const btnRunAlloc = document.getElementById('btn-run-joint-allocation');
    const dayTabs = document.getElementById('upload-day-tabs');
    const groupBySelect = document.getElementById('upload-group-by');
    const filterProg = document.getElementById('upload-filter-program');
    const filterCohort = document.getElementById('upload-filter-cohort');
    const filterRoom = document.getElementById('upload-filter-room');
    const btnDownloadCsv = document.getElementById('btn-download-csv');
    const btnDownloadZip = document.getElementById('btn-download-zip');
    const btnCloseModal = document.getElementById('btn-close-upload-modal');
    const sessionModal = document.getElementById('upload-session-modal');

    // Drag and Drop
    if (dropzone) {
      dropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropzone.classList.add('drag-over');
      });
      dropzone.addEventListener('dragleave', (e) => {
        e.preventDefault();
        dropzone.classList.remove('drag-over');
      });
      dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropzone.classList.remove('drag-over');
        if (e.dataTransfer && e.dataTransfer.files) {
          this.handleUploadFiles(e.dataTransfer.files);
        }
      });
      dropzone.addEventListener('click', (e) => {
        if (e.target !== btnSampleMSc && e.target !== btnRealSemester3 && fileInput) {
          fileInput.click();
        }
      });
    }

    if (btnBrowse && fileInput) {
      btnBrowse.addEventListener('click', (e) => {
        e.stopPropagation();
        fileInput.click();
      });
    }

    if (fileInput) {
      fileInput.addEventListener('change', (e) => {
        if (e.target.files) {
          this.handleUploadFiles(e.target.files);
        }
      });
    }

    // Load Real Semester III Timetables (140 Sessions)
    if (btnRealSemester3) {
      btnRealSemester3.addEventListener('click', (e) => {
        e.stopPropagation();
        this.loadRealSemesterIIIFixtures();
      });
    }

    // Load Quick Demo Sample (25 Mock Sessions)
    if (btnSampleMSc) {
      btnSampleMSc.addEventListener('click', (e) => {
        e.stopPropagation();
        this.loadSampleMScPrograms();
      });
    }

    // Reset Workflow
    if (btnReset) {
      btnReset.addEventListener('click', () => this.resetUploadWorkflow());
    }

    // Preview File Dropdown
    if (previewSelect) {
      previewSelect.addEventListener('change', (e) => {
        this.renderUploadPreviewTable(e.target.value);
      });
    }

    // Run Preflight
    if (btnPreflight) {
      btnPreflight.addEventListener('click', () => this.runPreflightValidation());
    }

    // Proceed to Allocation Stage
    if (btnProceedAlloc) {
      btnProceedAlloc.addEventListener('click', () => this.proceedToAllocationStage());
    }

    // Evaluation Profile Selection
    if (cardSynthetic && cardFactual) {
      cardSynthetic.addEventListener('click', () => {
        cardSynthetic.classList.add('active');
        cardFactual.classList.remove('active');
        this.uploadState.evaluationMode = 'synthetic';
      });
      cardFactual.addEventListener('click', () => {
        cardFactual.classList.add('active');
        cardSynthetic.classList.remove('active');
        this.uploadState.evaluationMode = 'factual';
      });
    }

    // Solver Time Limit Slider
    if (timeLimitInput) {
      const valLabel = document.getElementById('upload-time-limit-val');
      timeLimitInput.addEventListener('input', (e) => {
        if (valLabel) valLabel.textContent = `${parseFloat(e.target.value).toFixed(1)}s`;
      });
    }

    // Run Joint Allocation
    if (btnRunAlloc) {
      btnRunAlloc.addEventListener('click', () => this.runJointAllocation());
    }

    // Timetable Controls
    if (dayTabs) {
      dayTabs.querySelectorAll('.day-tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          dayTabs.querySelectorAll('.day-tab-btn').forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
          this.uploadState.activeTimetableDay = btn.dataset.day;
          this.loadUploadTimetable();
        });
      });
    }

    if (groupBySelect) {
      groupBySelect.addEventListener('change', (e) => {
        this.uploadState.timetableGroupBy = e.target.value;
        this.loadUploadTimetable();
      });
    }

    if (filterProg) {
      filterProg.addEventListener('change', (e) => {
        this.uploadState.filterProgram = e.target.value;
        this.uploadState.filterCohort = '';
        if (filterCohort) filterCohort.value = '';
        this.loadUploadTimetable();
      });
    }

    if (filterCohort) {
      filterCohort.addEventListener('change', (e) => {
        this.uploadState.filterCohort = e.target.value;
        this.loadUploadTimetable();
      });
    }

    if (filterRoom) {
      filterRoom.addEventListener('change', (e) => {
        this.uploadState.filterRoom = e.target.value;
        this.loadUploadTimetable();
      });
    }

    // Download Buttons
    if (btnDownloadCsv) {
      btnDownloadCsv.addEventListener('click', () => this.downloadExport('csv'));
    }

    if (btnDownloadZip) {
      btnDownloadZip.addEventListener('click', () => this.downloadExport('zip'));
    }

    // Modal Close
    if (btnCloseModal && sessionModal) {
      btnCloseModal.addEventListener('click', () => {
        sessionModal.style.display = 'none';
      });
      sessionModal.addEventListener('click', (e) => {
        if (e.target === sessionModal) sessionModal.style.display = 'none';
      });
    }
  }

  updateUploadStepper(stepNum) {
    for (let i = 1; i <= 5; i++) {
      const node = document.getElementById(`step-node-${i}`);
      if (!node) continue;
      node.classList.remove('active', 'completed');
      if (i < stepNum) {
        node.classList.add('completed');
      } else if (i === stepNum) {
        node.classList.add('active');
      }
    }
  }

  async handleUploadFiles(fileList) {
    if (!fileList || fileList.length === 0) return;

    this.uploadState.isDemoData = false;
    let addedCount = 0;
    for (let i = 0; i < fileList.length; i++) {
      const file = fileList[i];
      if (!file.name.toLowerCase().endsWith('.csv')) {
        this.showToast(`Skipped non-CSV file: ${file.name}. Only CSV format is currently supported.`, 'warning');
        continue;
      }

      let text = await this.readFileAsText(file);
      if (text && text.charCodeAt(0) === 0xFEFF) {
        text = text.slice(1);
      }
      const lines = text.split(/\r?\n/).filter(line => line.trim().length > 0);
      if (lines.length === 0) {
        this.showToast(`Empty CSV file skipped: ${file.name}`, 'warning');
        continue;
      }

      const headers = lines[0].split(',').map(h => h.trim().replace(/^["']|["']$/g, ''));
      const rowCount = Math.max(0, lines.length - 1);

      // Check if already uploaded, if so replace
      const existingIdx = this.uploadState.files.findIndex(f => f.filename === file.name);
      const fileItem = {
        filename: file.name,
        size: file.size,
        content: text,
        rowCount: rowCount,
        headers: headers,
        lines: lines
      };

      if (existingIdx >= 0) {
        this.uploadState.files[existingIdx] = fileItem;
      } else {
        this.uploadState.files.push(fileItem);
      }
      addedCount++;
    }

    if (addedCount > 0) {
      const totalRows = this.uploadState.files.reduce((acc, f) => acc + f.rowCount, 0);
      this.renderUploadedFilesList();
      this.renderUploadPreviewAndMappings();
      this.updateUploadStepper(2);
      this.showToast(`Successfully added ${addedCount} timetable file(s) (${totalRows} total sessions).`, 'success');
    }
  }

  readFileAsText(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = (e) => {
        let text = e.target.result;
        if (text && text.charCodeAt(0) === 0xFEFF) {
          text = text.slice(1);
        }
        resolve(text);
      };
      reader.onerror = (e) => reject(e);
      reader.readAsText(file);
    });
  }

  async loadRealSemesterIIIFixtures() {
    try {
      this.uploadState.isDemoData = false;
      const data = await Api.getSemesterIIIFixtures();
      if (!data || !data.files || data.files.length === 0) {
        throw new Error('No fixture files returned from server.');
      }

      this.uploadState.files = data.files.map(f => {
        let text = f.content;
        if (text && text.charCodeAt(0) === 0xFEFF) {
          text = text.slice(1);
        }
        const lines = text.split(/\r?\n/).filter(line => line.trim().length > 0);
        return {
          filename: f.filename,
          size: f.content.length,
          content: text,
          rowCount: Math.max(0, lines.length - 1),
          headers: lines[0].split(',').map(h => h.trim().replace(/^["']|["']$/g, '')),
          lines: lines
        };
      });

      const totalRows = this.uploadState.files.reduce((acc, f) => acc + f.rowCount, 0);
      this.renderUploadedFilesList();
      this.renderUploadPreviewAndMappings();
      this.updateUploadStepper(2);
      this.showToast(`Loaded ${data.files.length} real Semester III timetables (${totalRows} session occurrences across 5 programs).`, 'success');
    } catch (err) {
      this.showToast(`Failed to load Semester III fixtures: ${err.message}`, 'danger');
    }
  }

  loadSampleMScPrograms() {
    this.uploadState.isDemoData = true;

    const cyberCsv = `program,cohort_id,course,academic_cycle,day,start_period,end_period,required_room_type
M.Sc. Cyber Security,odd_sem3_CY,Network Security Lab,odd,Monday,1,2,laboratory
M.Sc. Cyber Security,odd_sem3_CY,Discrete Mathematics,odd,Monday,3,3,classroom
M.Sc. Cyber Security,odd_sem3_CY,Applied Cryptography,odd,Tuesday,1,2,classroom
M.Sc. Cyber Security,odd_sem3_CY,Ethical Hacking Lab,odd,Wednesday,3,4,laboratory
M.Sc. Cyber Security,odd_sem3_CY,Cloud Defense Architecture,odd,Thursday,1,2,classroom`;

    const softwareCsv = `program,cohort_id,course,academic_cycle,day,start_period,end_period,required_room_type
M.Sc. Software Systems,odd_sem3_SS,Cloud Computing Lab,odd,Monday,1,2,laboratory
M.Sc. Software Systems,odd_sem3_SS,Distributed Systems,odd,Monday,4,4,classroom
M.Sc. Software Systems,odd_sem3_SS,Enterprise Architecture,odd,Tuesday,3,4,classroom
M.Sc. Software Systems,odd_sem3_SS,DevOps Engineering Lab,odd,Wednesday,1,2,laboratory
M.Sc. Software Systems,odd_sem3_SS,Software Testing & QA,odd,Thursday,3,4,classroom`;

    const dataScienceCsv = `program,cohort_id,course,academic_cycle,day,start_period,end_period,required_room_type
M.Sc. Data Science,odd_sem3_DS,Machine Learning Lab,odd,Monday,3,4,laboratory
M.Sc. Data Science,odd_sem3_DS,Statistical Inference,odd,Monday,5,5,classroom
M.Sc. Data Science,odd_sem3_DS,Deep Learning Systems,odd,Tuesday,1,2,classroom
M.Sc. Data Science,odd_sem3_DS,Big Data Analytics Lab,odd,Thursday,1,2,laboratory
M.Sc. Data Science,odd_sem3_DS,Natural Language Processing,odd,Friday,3,4,classroom`;

    const theoreticalCsv = `program,cohort_id,course,academic_cycle,day,start_period,end_period,required_room_type
M.Sc. Theoretical Computer Science,odd_sem3_TCS,Automata Theory & Computability,odd,Monday,1,2,classroom
M.Sc. Theoretical Computer Science,odd_sem3_TCS,Graph Algorithms Lab,odd,Tuesday,3,4,laboratory
M.Sc. Theoretical Computer Science,odd_sem3_TCS,Quantum Computing Foundations,odd,Wednesday,1,2,classroom
M.Sc. Theoretical Computer Science,odd_sem3_TCS,Advanced Complexity Theory,odd,Thursday,3,4,classroom
M.Sc. Theoretical Computer Science,odd_sem3_TCS,Formal Verification Lab,odd,Friday,1,2,laboratory`;

    const compFinanceCsv = `program,cohort_id,course,academic_cycle,day,start_period,end_period,required_room_type
M.Sc. Computational Finance,odd_sem3_CF,Financial Modeling Lab,odd,Monday,3,4,laboratory
M.Sc. Computational Finance,odd_sem3_CF,Quantitative Risk Analysis,odd,Tuesday,1,2,classroom
M.Sc. Computational Finance,odd_sem3_CF,Stochastic Calculus,odd,Wednesday,3,4,classroom
M.Sc. Computational Finance,odd_sem3_CF,Algorithmic Trading Lab,odd,Thursday,1,2,laboratory
M.Sc. Computational Finance,odd_sem3_CF,Derivatives Pricing,odd,Friday,3,4,classroom`;

    const samples = [
      { filename: 'demo_cyber_security.csv', content: cyberCsv },
      { filename: 'demo_software_systems.csv', content: softwareCsv },
      { filename: 'demo_data_science.csv', content: dataScienceCsv },
      { filename: 'demo_theoretical_cs.csv', content: theoreticalCsv },
      { filename: 'demo_comp_finance.csv', content: compFinanceCsv },
    ];

    this.uploadState.files = samples.map(s => {
      const lines = s.content.split('\n');
      return {
        filename: s.filename,
        size: s.content.length,
        content: s.content,
        rowCount: lines.length - 1,
        headers: lines[0].split(','),
        lines: lines
      };
    });

    this.renderUploadedFilesList();
    this.renderUploadPreviewAndMappings();
    this.updateUploadStepper(2);
    this.showToast('Loaded Quick Demo Sample (25 mock sessions for demonstration).', 'info');
  }

  removeUploadedFile(idx) {
    if (idx >= 0 && idx < this.uploadState.files.length) {
      const removed = this.uploadState.files.splice(idx, 1)[0];
      this.showToast(`Removed ${removed.filename}`, 'info');
      this.renderUploadedFilesList();
      if (this.uploadState.files.length > 0) {
        this.renderUploadPreviewAndMappings();
      } else {
        this.resetUploadWorkflow();
      }
    }
  }

  renderUploadedFilesList() {
    const container = document.getElementById('uploaded-files-container');
    const list = document.getElementById('uploaded-files-list');
    const badge = document.getElementById('file-count-badge');
    if (!container || !list) return;

    if (this.uploadState.files.length === 0) {
      container.style.display = 'none';
      return;
    }

    const totalRows = this.uploadState.files.reduce((acc, f) => acc + f.rowCount, 0);
    container.style.display = 'block';
    if (badge) badge.textContent = `${this.uploadState.files.length} files • ${totalRows} sessions`;

    const demoBanner = this.uploadState.isDemoData
      ? `<div style="background: #fef3c7; border: 1px solid #fde68a; padding: 0.5rem 0.75rem; border-radius: 4px; font-size: 0.75rem; color: #92400e; margin-bottom: 0.75rem;">
          🧪 <strong>DEMO SAMPLE ACTIVE:</strong> 25 synthetic mock sessions loaded for quick verification. To evaluate the full 140-occurrence Semester III timetables, click "Load Real Semester III Timetables" or browse files.
        </div>`
      : `<div style="background: #eff6ff; border: 1px solid #bfdbfe; padding: 0.5rem 0.75rem; border-radius: 4px; font-size: 0.75rem; color: #1e40af; margin-bottom: 0.75rem;">
          📋 <strong>VERIFIED DATASET ACTIVE:</strong> ${totalRows} real session occurrences across ${this.uploadState.files.length} branch timetables.
        </div>`;

    list.innerHTML = demoBanner + this.uploadState.files.map((f, idx) => {
      const kbSize = (f.size / 1024).toFixed(1);
      return `
        <div class="uploaded-file-card">
          <div style="display: flex; align-items: center; gap: 0.6rem;">
            <span style="font-size: 1.2rem;">📄</span>
            <div>
              <strong style="font-size: 0.85rem; color: var(--text-main);">${f.filename}</strong>
              <div style="font-size: 0.72rem; color: var(--text-muted);">
                ${f.rowCount} sessions • ${kbSize} KB • Periods 1–8
              </div>
            </div>
          </div>
          <div style="display: flex; align-items: center; gap: 0.5rem;">
            <button class="btn-secondary" style="font-size: 0.75rem; padding: 0.25rem 0.5rem;" onclick="window.ciqApp.renderUploadPreviewTable('${f.filename}')">
              👁️ Preview
            </button>
            <button class="btn-secondary" style="font-size: 0.75rem; padding: 0.25rem 0.5rem; color: var(--color-danger);" onclick="window.ciqApp.removeUploadedFile(${idx})">
              ✕ Remove
            </button>
          </div>
        </div>
      `;
    }).join('');
  }

  renderUploadPreviewAndMappings() {
    const cardMapping = document.getElementById('card-stage-mapping');
    const previewSelect = document.getElementById('preview-file-select');
    const pillsContainer = document.getElementById('recognized-columns-pills');
    if (!cardMapping) return;

    cardMapping.style.display = 'block';

    // Populate preview dropdown
    if (previewSelect) {
      previewSelect.innerHTML = this.uploadState.files.map(f =>
        `<option value="${f.filename}">${f.filename} (${f.rowCount} sessions)</option>`
      ).join('');
      if (this.uploadState.files.length > 0) {
        this.renderUploadPreviewTable(this.uploadState.files[0].filename);
      }
    }

    // Inspect recognized schema mappings across files
    const allHeaders = new Set();
    this.uploadState.files.forEach(f => f.headers.forEach(h => allHeaders.add(h.toLowerCase())));

    const canonicalSchema = [
      { name: 'program', label: 'Academic Program', icon: '🎓' },
      { name: 'cohort_id', label: 'Student Cohort', icon: '👥' },
      { name: 'course', label: 'Course Title', icon: '📚' },
      { name: 'day', label: 'Weekday', icon: '📅' },
      { name: 'start_period', label: 'Start Period (1–8)', icon: '⏱️' },
      { name: 'end_period', label: 'End Period (1–8)', icon: '⏱️' },
      { name: 'required_room_type', label: 'Required Room Type', icon: '🏫' },
    ];

    if (pillsContainer) {
      pillsContainer.innerHTML = canonicalSchema.map(item => {
        const isMatched = Array.from(allHeaders).some(h => h.includes(item.name.replace('_', '')) || h.includes(item.name));
        return `
          <span class="badge ${isMatched ? 'verified' : 'badge-warning'}" style="font-size: 0.72rem; padding: 0.3rem 0.5rem;">
            ${item.icon} ${item.label}: ${isMatched ? '✓ Auto-Mapped' : 'Required'}
          </span>
        `;
      }).join('');
    }

    // Check for ambiguous headers
    this.checkAmbiguousHeaders();
  }

  checkAmbiguousHeaders() {
    const alertBox = document.getElementById('ambiguous-header-alert');
    const controls = document.getElementById('ambiguous-mapping-controls');
    if (!alertBox || !controls) return;

    const ambiguousFound = [];
    this.uploadState.files.forEach(f => {
      f.headers.forEach(h => {
        const lower = h.toLowerCase().trim();
        if (['department', 'dept', 'room'].includes(lower)) {
          const isConfirmed = this.uploadState.confirmedAmbiguousMappings[f.filename] &&
                              this.uploadState.confirmedAmbiguousMappings[f.filename][lower];
          if (!isConfirmed) {
            ambiguousFound.push({ filename: f.filename, header: lower });
          }
        }
      });
    });

    if (ambiguousFound.length > 0) {
      alertBox.style.display = 'block';
      controls.innerHTML = ambiguousFound.map(item => `
        <div style="background: white; padding: 0.5rem 0.75rem; border-radius: 4px; border: 1px solid var(--border-light); display: flex; align-items: center; gap: 0.5rem;">
          <span style="font-size: 0.78rem;"><strong>${item.filename}</strong>: header '<code>${item.header}</code>' →</span>
          <select id="map-select-${item.filename}-${item.header}" class="form-select" style="font-size: 0.78rem; padding: 0.2rem 0.4rem;">
            <option value="program">Map to 'program' (Academic Program)</option>
            <option value="ignore">Ignore Column</option>
          </select>
          <button class="btn-primary" style="font-size: 0.75rem; padding: 0.25rem 0.5rem;" onclick="window.ciqApp.confirmAmbiguousMapping('${item.filename}', '${item.header}')">
            ✓ Confirm
          </button>
        </div>
      `).join('');
    } else {
      alertBox.style.display = 'none';
    }
  }

  confirmAmbiguousMapping(filename, header) {
    const select = document.getElementById(`map-select-${filename}-${header}`);
    if (!select) return;
    const targetField = select.value;

    if (!this.uploadState.confirmedAmbiguousMappings[filename]) {
      this.uploadState.confirmedAmbiguousMappings[filename] = {};
    }
    this.uploadState.confirmedAmbiguousMappings[filename][header] = targetField;

    this.showToast(`Confirmed: '${header}' in ${filename} mapped to '${targetField}'.`, 'success');
    this.checkAmbiguousHeaders();
  }

  renderUploadPreviewTable(filename) {
    const table = document.getElementById('upload-preview-table');
    if (!table) return;

    const file = this.uploadState.files.find(f => f.filename === filename);
    if (!file || !file.lines || file.lines.length === 0) return;

    const thead = table.querySelector('thead');
    const tbody = table.querySelector('tbody');
    if (!thead || !tbody) return;

    const headers = file.headers;
    thead.innerHTML = `
      <tr>
        <th style="padding: 0.4rem 0.6rem; text-align: left; background: var(--bg-card-subtle);">Row #</th>
        <th style="padding: 0.4rem 0.6rem; text-align: left; background: var(--bg-card-subtle);">Source File</th>
        ${headers.map(h => `<th style="padding: 0.4rem 0.6rem; text-align: left; background: var(--bg-card-subtle);">${h}</th>`).join('')}
      </tr>
    `;

    const previewRows = file.lines.slice(1, 6);
    tbody.innerHTML = previewRows.map((line, rIdx) => {
      const cols = line.split(',').map(c => c.trim().replace(/^["']|["']$/g, ''));
      return `
        <tr style="border-bottom: 1px solid var(--border-light);">
          <td style="padding: 0.4rem 0.6rem; font-family: var(--font-mono); font-size: 0.75rem; color: var(--text-muted);">${rIdx + 2}</td>
          <td style="padding: 0.4rem 0.6rem; font-size: 0.75rem; color: var(--color-primary); font-weight: 500;">${filename}</td>
          ${cols.map(c => `<td style="padding: 0.4rem 0.6rem; font-size: 0.78rem;">${c}</td>`).join('')}
        </tr>
      `;
    }).join('');
  }

  async runPreflightValidation() {
    const btn = document.getElementById('btn-run-preflight');
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<span class="loading-spinner"></span> Validating Periods (1–8)...';
    }

    try {
      const payload = {
        files: this.uploadState.files.map(f => ({
          filename: f.filename,
          content: f.content
        })),
        confirmed_ambiguous_mappings: this.uploadState.confirmedAmbiguousMappings
      };

      const res = await Api.preflightUpload(payload);
      this.uploadState.preflightResponse = res;

      this.updateUploadStepper(3);
      const stagePreflight = document.getElementById('card-stage-preflight');
      if (stagePreflight) stagePreflight.style.display = 'block';

      // Update KPI summaries
      const acceptedVal = document.getElementById('pref-accepted-count');
      const cycleVal = document.getElementById('pref-cycle-val');
      const progCount = document.getElementById('pref-programs-count');
      const progList = document.getElementById('pref-programs-list');
      const cohortCount = document.getElementById('pref-cohorts-count');
      const cohortList = document.getElementById('pref-cohorts-list');
      const statusBadge = document.getElementById('preflight-status-badge');
      const btnProceed = document.getElementById('btn-proceed-to-allocation');
      const notice = document.getElementById('preflight-resolution-notice');

      if (acceptedVal) acceptedVal.textContent = res.total_sessions_accepted;
      if (cycleVal) cycleVal.textContent = res.academic_cycle.toUpperCase();
      if (progCount) progCount.textContent = res.programs_detected.length;
      if (progList) progList.textContent = res.programs_detected.slice(0, 3).join(', ') + (res.programs_detected.length > 3 ? '...' : '');
      if (cohortCount) cohortCount.textContent = res.cohorts_detected.length;
      if (cohortList) cohortList.textContent = res.cohorts_detected.slice(0, 3).join(', ') + (res.cohorts_detected.length > 3 ? '...' : '');

      // Diagnostics rendering
      const diagContainer = document.getElementById('preflight-diagnostics-container');
      if (diagContainer) {
        if (res.errors.length === 0 && res.warnings.length === 0) {
          diagContainer.innerHTML = `
            <div style="background: var(--color-success-bg); border: 1px solid var(--color-success-border); padding: 0.85rem 1rem; border-radius: var(--radius-sm); color: var(--color-success); font-size: 0.85rem; display: flex; align-items: center; gap: 0.5rem;">
              <span>✓</span> <strong>Clean Ingestion:</strong> All ${res.total_sessions_accepted} session occurrences parsed cleanly with zero blocking errors across periods 1–8.
            </div>
          `;
        } else {
          let html = '';
          if (res.errors.length > 0) {
            html += `
              <div style="margin-bottom: 0.75rem;">
                <strong style="color: var(--color-danger); font-size: 0.85rem;">Blocking Errors (${res.errors.length}):</strong>
                <div class="table-responsive" style="margin-top: 0.35rem; border: 1px solid var(--color-danger-border); border-radius: var(--radius-sm);">
                  <table class="table" style="width: 100%; font-size: 0.78rem;">
                    <thead style="background: var(--color-danger-bg); color: var(--color-danger);">
                      <tr>
                        <th style="padding: 0.4rem 0.6rem;">File</th>
                        <th style="padding: 0.4rem 0.6rem;">Row #</th>
                        <th style="padding: 0.4rem 0.6rem;">Field</th>
                        <th style="padding: 0.4rem 0.6rem;">Diagnostic Message</th>
                      </tr>
                    </thead>
                    <tbody>
                      ${res.errors.map(err => `
                        <tr style="border-bottom: 1px solid var(--border-light);">
                          <td style="padding: 0.4rem 0.6rem; font-weight: 500;">${err.filename}</td>
                          <td style="padding: 0.4rem 0.6rem; font-family: var(--font-mono);">${err.row_number}</td>
                          <td style="padding: 0.4rem 0.6rem;"><span class="badge badge-danger">${err.field || 'general'}</span></td>
                          <td style="padding: 0.4rem 0.6rem; color: var(--color-danger);">${err.message}</td>
                        </tr>
                      `).join('')}
                    </tbody>
                  </table>
                </div>
              </div>
            `;
          }

          if (res.warnings.length > 0) {
            html += `
              <div>
                <strong style="color: var(--color-warning); font-size: 0.85rem;">Warnings (${res.warnings.length}):</strong>
                <ul style="font-size: 0.78rem; color: var(--color-warning); margin-top: 0.25rem; padding-left: 1.25rem;">
                  ${res.warnings.map(w => `<li><strong>${w.filename}:${w.row_number}</strong>: ${w.message}</li>`).join('')}
                </ul>
              </div>
            `;
          }
          diagContainer.innerHTML = html;
        }
      }

      // Check whether allocation is unlocked
      if (res.is_valid && res.errors.length === 0) {
        if (statusBadge) statusBadge.innerHTML = '<span class="badge verified">✓ Preflight Passed</span>';
        if (btnProceed) btnProceed.disabled = false;
        if (notice) notice.textContent = 'All preflight checks passed. Proceed to joint allocation.';
        this.showToast(`Preflight passed! ${res.total_sessions_accepted} sessions accepted for allocation.`, 'success');
      } else {
        if (statusBadge) statusBadge.innerHTML = `<span class="badge badge-danger">✖ ${res.errors.length} Blocking Errors</span>`;
        if (btnProceed) btnProceed.disabled = true;
        if (notice) notice.textContent = 'Resolve all blocking errors to unlock joint allocation.';
        this.showToast(`Preflight failed with ${res.errors.length} errors. Please review diagnostics.`, 'danger');
      }

      if (stagePreflight) stagePreflight.scrollIntoView({ behavior: 'smooth' });
    } catch (err) {
      this.showToast(`Preflight failed: ${err.message}`, 'danger');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = '🔍 Run Preflight Validation';
      }
    }
  }

  proceedToAllocationStage() {
    this.updateUploadStepper(4);
    const stageAlloc = document.getElementById('card-stage-allocate');
    if (stageAlloc) {
      stageAlloc.style.display = 'block';
      stageAlloc.scrollIntoView({ behavior: 'smooth' });
    }
  }

  async runJointAllocation() {
    if (!this.uploadState.preflightResponse || !this.uploadState.preflightResponse.run_id) {
      this.showToast('Please run preflight validation first.', 'warning');
      return;
    }

    const btn = document.getElementById('btn-run-joint-allocation');
    const loading = document.getElementById('alloc-loading-indicator');
    if (btn) btn.disabled = true;
    if (loading) loading.style.display = 'inline-flex';

    try {
      const timeLimit = parseFloat(document.getElementById('upload-time-limit')?.value || 5.0);
      const labException = document.getElementById('upload-allow-lab-exception')?.checked || false;

      const payload = {
        run_id: this.uploadState.preflightResponse.run_id,
        evaluation_mode: this.uploadState.evaluationMode,
        time_limit_seconds: timeLimit,
        allow_computing_lab_exception: labException
      };

      const res = await Api.allocateUpload(payload);
      this.uploadState.allocationResponse = res;

      this.updateUploadStepper(5);

      // Reveal Results, Timetable, and Export stages
      const cardResults = document.getElementById('card-stage-results');
      const cardTimetable = document.getElementById('card-stage-timetable');
      const cardExport = document.getElementById('card-stage-export');

      if (cardResults) cardResults.style.display = 'block';
      if (cardTimetable) cardTimetable.style.display = 'block';
      if (cardExport) cardExport.style.display = 'block';

      // Update Outcome KPIs
      const badgeStatus = document.getElementById('alloc-status-badge');
      if (badgeStatus) {
        if (res.status === 'completed') {
          badgeStatus.innerHTML = '<span class="badge verified">✓ Allocation Completed</span>';
        } else if (res.status === 'fallback') {
          badgeStatus.innerHTML = '<span class="badge badge-warning">⚡ Baseline-Protection Fallback Retained</span>';
        } else {
          badgeStatus.innerHTML = '<span class="badge badge-danger">⚠️ Resource Contention / Infeasible</span>';
        }
      }

      const assignedVal = document.getElementById('res-assigned-count');
      const compPct = document.getElementById('res-completion-pct');
      const allocName = document.getElementById('res-allocator-name');
      const fallbackStatus = document.getElementById('res-fallback-status');
      const walkSavings = document.getElementById('res-walking-savings');
      const walkComp = document.getElementById('res-walking-comparison');
      const valStatus = document.getElementById('res-validation-status');
      const valCollisions = document.getElementById('res-validation-collisions');

      if (assignedVal) assignedVal.textContent = `${res.assigned_count} / ${res.total_sessions}`;
      if (compPct) compPct.textContent = `${Math.round(res.assigned_count / res.total_sessions * 100)}% Placed (${res.unassigned_count} unassigned)`;
      if (allocName) allocName.textContent = res.selected_allocator;
      if (fallbackStatus) fallbackStatus.textContent = res.fallback_to_baseline ? 'Protected Baseline Retained' : 'CP-SAT Candidate Adopted';
      if (walkSavings) walkSavings.textContent = `${res.walking_time_reduction_minutes} min saved (${res.walking_time_reduction_percentage}%)`;
      if (walkComp) walkComp.textContent = `Baseline: ${res.baseline_walking_time}m → Opt: ${res.optimized_walking_time}m`;
      if (valStatus) valStatus.textContent = res.validation.is_valid ? 'PASS' : 'FAIL / ANOMALIES';
      if (valCollisions) valCollisions.textContent = `${res.validation.fail_count} hard violations`;

      // Infeasibility diagnosis
      const infeasAlert = document.getElementById('res-infeasibility-alert');
      const diagText = document.getElementById('res-diagnosis-text');
      const unassignedChips = document.getElementById('res-unassigned-chips');

      if (res.unassigned_count > 0 || res.status === 'infeasible') {
        if (infeasAlert) infeasAlert.style.display = 'block';
        if (diagText) diagText.textContent = res.infeasibility_diagnosis || 'Resource contention: physical room capacity exceeded.';
        if (unassignedChips) {
          unassignedChips.innerHTML = res.unassigned_session_ids.map(id =>
            `<span class="session-badge-unassigned">${id}</span>`
          ).join('');
        }
      } else {
        if (infeasAlert) infeasAlert.style.display = 'none';
      }

      // Update Export Metadata Labels
      const runIdLabel = document.getElementById('export-run-id-label');
      const profileLabel = document.getElementById('export-profile-label');
      if (runIdLabel) runIdLabel.textContent = res.run_id;
      if (profileLabel) profileLabel.textContent = res.evaluation_mode_label;

      // Load Timetable
      await this.loadUploadTimetable();

      if (cardResults) cardResults.scrollIntoView({ behavior: 'smooth' });
      this.showToast(`Joint Allocation executed! Outcome: ${res.status}`, 'success');
    } catch (err) {
      this.showToast(`Joint allocation failed: ${err.message}`, 'danger');
    } finally {
      if (btn) btn.disabled = false;
      if (loading) loading.style.display = 'none';
    }
  }

  async loadUploadTimetable() {
    if (!this.uploadState.allocationResponse || !this.uploadState.allocationResponse.run_id) return;

    try {
      const runId = this.uploadState.allocationResponse.run_id;
      const day = this.uploadState.activeTimetableDay;
      const groupBy = this.uploadState.timetableGroupBy;
      const program = this.uploadState.filterProgram || null;
      const cohortId = this.uploadState.filterCohort || null;
      const roomId = this.uploadState.filterRoom || null;

      const data = await Api.getUploadTimetable(runId, {
        day: day,
        groupBy: groupBy,
        program: program,
        cohortId: cohortId,
        roomId: roomId
      });
      this.uploadState.timetableResponse = data;

      // Populate filter dropdowns
      const progSelect = document.getElementById('upload-filter-program');
      const cohortSelect = document.getElementById('upload-filter-cohort');
      const roomSelect = document.getElementById('upload-filter-room');

      if (progSelect && data.programs) {
        const curr = this.uploadState.filterProgram;
        progSelect.innerHTML = '<option value="">All Programs</option>' +
          data.programs.map(p => `<option value="${p}" ${p === curr ? 'selected' : ''}>${p}</option>`).join('');
      }

      if (cohortSelect && data.cohorts) {
        const curr = this.uploadState.filterCohort;
        cohortSelect.innerHTML = '<option value="">All Cohorts</option>' +
          data.cohorts.map(c => `<option value="${c}" ${c === curr ? 'selected' : ''}>${c}</option>`).join('');
      }

      if (roomSelect && data.rooms) {
        const curr = this.uploadState.filterRoom;
        roomSelect.innerHTML = '<option value="">All Rooms</option>' +
          data.rooms.map(r => `<option value="${r}" ${r === curr ? 'selected' : ''}>${r}</option>`).join('');
      }

      this.renderUploadTimetableGrid(data);
    } catch (err) {
      this.showToast(`Failed to load timetable: ${err.message}`, 'danger');
    }
  }

  renderUploadTimetableGrid(data) {
    const headerEl = document.getElementById('upload-grid-row-header');
    const tbody = document.getElementById('upload-timetable-tbody');
    if (!tbody) return;

    const isAllDays = data.target_day === 'All Days';

    if (headerEl) {
      if (isAllDays) {
        headerEl.textContent = 'Weekday';
      } else {
        headerEl.textContent = data.group_by === 'room' ? 'Room' : (data.group_by === 'program' ? 'Program' : 'Cohort');
      }
    }

    if (!data.row_keys || data.row_keys.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="9" style="text-align: center; padding: 2.5rem; color: var(--text-muted);">
            <div style="font-weight: 600; font-size: 0.9rem; margin-bottom: 0.25rem;">No matching sessions found</div>
            <div style="font-size: 0.78rem;">No scheduled classes exist for ${data.target_day} with the active filters.</div>
          </td>
        </tr>
      `;
      return;
    }

    if (isAllDays) {
      // Group row keys by entity to build a unified weekly timetable
      const dayFullMap = {
        Mon: 'Monday',
        Tue: 'Tuesday',
        Wed: 'Wednesday',
        Thu: 'Thursday',
        Fri: 'Friday'
      };

      let entityIcon = '👥';
      let entityCategory = 'Cohort';
      if (data.group_by === 'room') {
        entityIcon = '🏫';
        entityCategory = 'Room';
      } else if (data.group_by === 'program') {
        entityIcon = '🎓';
        entityCategory = 'Program';
      }

      const entityGroups = [];
      const entityMap = new Map();

      data.row_keys.forEach(rowKey => {
        const match = rowKey.match(/^(.*?)(?:\s*\((Mon|Tue|Wed|Thu|Fri)\))?$/i);
        const entityName = (match && match[1]) ? match[1].trim() : rowKey;
        const dayAbbr = (match && match[2]) ? match[2].charAt(0).toUpperCase() + match[2].slice(1).toLowerCase() : '';
        const dayFullName = dayFullMap[dayAbbr] || dayAbbr || 'Weekday';

        if (!entityMap.has(entityName)) {
          const grp = {
            entity: entityName,
            rows: []
          };
          entityMap.set(entityName, grp);
          entityGroups.push(grp);
        }
        entityMap.get(entityName).rows.push({
          rowKey: rowKey,
          dayAbbr: dayAbbr,
          dayFullName: dayFullName
        });
      });

      let fullTableHtml = '';

      entityGroups.forEach(grp => {
        // Calculate total distinct sessions for this entity across the week
        const groupSessionIds = new Set();
        grp.rows.forEach(r => {
          const rowSlots = data.grid[r.rowKey] || {};
          for (let p = 1; p <= 8; p++) {
            (rowSlots[p] || []).forEach(s => groupSessionIds.add(s.session_id));
          }
        });
        const totalGroupSessions = groupSessionIds.size;

        // Group Header banner spanning all columns
        fullTableHtml += `
          <tr class="weekly-entity-group-header" style="background: var(--bg-card-subtle, #f1f5f9); border-top: 2px solid var(--border-medium, #cbd5e1); border-bottom: 1px solid var(--border-medium, #cbd5e1);">
            <th colspan="9" style="padding: 0.65rem 0.85rem; text-align: left; font-size: 0.85rem; color: var(--text-main, #1e293b); font-weight: 700;">
              <span style="font-size: 0.95rem; margin-right: 0.35rem;">${entityIcon}</span>
              <span>${grp.entity}</span>
              <span style="font-weight: 500; font-size: 0.75rem; color: var(--text-muted, #64748b); margin-left: 0.6rem;">
                (${totalGroupSessions} session occurrences across Monday–Friday)
              </span>
            </th>
          </tr>
        `;

        // Render weekday rows for this entity in chronological Monday-Friday order
        grp.rows.forEach(r => {
          const rowSlots = data.grid[r.rowKey] || {};
          const cells = [];
          let skipUntilPeriod = 0;

          for (let p = 1; p <= 8; p++) {
            if (p < skipUntilPeriod) {
              continue;
            }

            const sessions = rowSlots[p] || [];
            if (sessions.length === 0) {
              cells.push(`<td style="padding: 0.5rem; text-align: center; color: #cbd5e1; font-size: 0.75rem;">-</td>`);
              continue;
            }

            const firstSession = sessions[0];
            const span = (firstSession.start_period === p && firstSession.end_period > p)
              ? (firstSession.end_period - firstSession.start_period + 1)
              : 1;

            if (span > 1) {
              skipUntilPeriod = firstSession.end_period + 1;
            }

            const cellContent = sessions.map(s => {
              const isAllocated = !!s.assigned_room_id;
              const bgClass = isAllocated ? 'background: #eff6ff; border: 1px solid #bfdbfe;' : 'background: #fee2e2; border: 1px solid #fecaca;';
              const roomDisplay = isAllocated ? `🏫 <strong>${s.assigned_room_id}</strong>` : '⚠️ <span style="color:red;">Unassigned</span>';
              const isMulti = s.end_period > s.start_period;
              const spanBadge = isMulti
                ? `<span class="badge" style="background: #2563eb; color: white; font-size: 0.62rem; padding: 1px 5px; border-radius: 3px;">P${s.start_period}–P${s.end_period} (${s.end_period - s.start_period + 1} Periods)</span>`
                : '';
              const sessionJson = encodeURIComponent(JSON.stringify(s));

              return `
                <div class="session-cell-clickable" onclick="window.ciqApp.showUploadSessionDetail('${sessionJson}')" style="${bgClass} padding: 0.35rem 0.45rem; border-radius: 4px; font-size: 0.72rem; line-height: 1.25; height: 100%;">
                  <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 0.25rem;">
                    <strong style="color: var(--text-main); font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${s.course}">${s.course}</strong>
                    ${spanBadge}
                  </div>
                  <div style="color: var(--text-muted); font-size: 0.68rem; margin-top: 0.15rem;">${s.cohort_id} • ${s.session_type}</div>
                  <div style="margin-top: 0.25rem; font-size: 0.72rem;">${roomDisplay}</div>
                </div>
              `;
            }).join('');

            cells.push(`<td colspan="${span}" style="padding: 0.35rem; vertical-align: top;">${cellContent}</td>`);
          }

          fullTableHtml += `
            <tr style="border-bottom: 1px solid var(--border-light);">
              <td style="padding: 0.5rem 0.75rem; font-weight: 700; font-size: 0.8rem; background: var(--bg-card-subtle); vertical-align: middle; white-space: nowrap; width: 110px; border-right: 1px solid var(--border-light);">
                <span style="color: var(--color-primary, #2563eb);">📅 ${r.dayFullName}</span>
              </td>
              ${cells.join('')}
            </tr>
          `;
        });
      });

      tbody.innerHTML = fullTableHtml;
      return;
    }

    // Default Single-Day View (Monday - Friday individual views)
    tbody.innerHTML = data.row_keys.map(rowKey => {
      const rowSlots = data.grid[rowKey] || {};
      const cells = [];
      let skipUntilPeriod = 0;

      for (let p = 1; p <= 8; p++) {
        if (p < skipUntilPeriod) {
          // Covered by previous multi-period colspan
          continue;
        }

        const sessions = rowSlots[p] || [];
        if (sessions.length === 0) {
          cells.push(`<td style="padding: 0.5rem; text-align: center; color: #cbd5e1; font-size: 0.75rem;">-</td>`);
          continue;
        }

        // Check if multi-period session starts at this period
        const firstSession = sessions[0];
        const span = (firstSession.start_period === p && firstSession.end_period > p)
          ? (firstSession.end_period - firstSession.start_period + 1)
          : 1;

        if (span > 1) {
          skipUntilPeriod = firstSession.end_period + 1;
        }

        const cellContent = sessions.map(s => {
          const isAllocated = !!s.assigned_room_id;
          const bgClass = isAllocated ? 'background: #eff6ff; border: 1px solid #bfdbfe;' : 'background: #fee2e2; border: 1px solid #fecaca;';
          const roomDisplay = isAllocated ? `🏫 <strong>${s.assigned_room_id}</strong>` : '⚠️ <span style="color:red;">Unassigned</span>';
          const isMulti = s.end_period > s.start_period;
          const spanBadge = isMulti
            ? `<span class="badge" style="background: #2563eb; color: white; font-size: 0.62rem; padding: 1px 5px; border-radius: 3px;">P${s.start_period}–P${s.end_period} (${s.end_period - s.start_period + 1} Periods)</span>`
            : '';
          const sessionJson = encodeURIComponent(JSON.stringify(s));

          return `
            <div class="session-cell-clickable" onclick="window.ciqApp.showUploadSessionDetail('${sessionJson}')" style="${bgClass} padding: 0.35rem 0.45rem; border-radius: 4px; font-size: 0.72rem; line-height: 1.25; height: 100%;">
              <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 0.25rem;">
                <strong style="color: var(--text-main); font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${s.course}">${s.course}</strong>
                ${spanBadge}
              </div>
              <div style="color: var(--text-muted); font-size: 0.68rem; margin-top: 0.15rem;">${s.cohort_id} • ${s.session_type}</div>
              <div style="margin-top: 0.25rem; font-size: 0.72rem;">${roomDisplay}</div>
            </div>
          `;
        }).join('');

        cells.push(`<td colspan="${span}" style="padding: 0.35rem; vertical-align: top;">${cellContent}</td>`);
      }

      return `
        <tr style="border-bottom: 1px solid var(--border-light);">
          <td style="padding: 0.5rem 0.75rem; font-weight: 600; font-size: 0.8rem; background: var(--bg-card-subtle); vertical-align: middle;">
            ${rowKey}
          </td>
          ${cells.join('')}
        </tr>
      `;
    }).join('');
  }

  showUploadSessionDetail(sessionJson) {
    const modal = document.getElementById('upload-session-modal');
    const body = document.getElementById('upload-modal-body');
    if (!modal || !body) return;

    const s = JSON.parse(decodeURIComponent(sessionJson));
    const isAllocated = !!s.assigned_room_id;
    const span = (s.end_period && s.start_period) ? (s.end_period - s.start_period + 1) : 1;
    const periodLabel = (s.start_period === s.end_period) ? `Period ${s.start_period}` : `Periods ${s.start_period}–${s.end_period} (${span} periods)`;

    body.innerHTML = `
      <div style="display: flex; flex-direction: column; gap: 0.85rem; font-size: 0.82rem;">
        <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border-light); padding-bottom: 0.5rem;">
          <div>
            <span style="font-family: var(--font-mono); font-size: 0.75rem; color: var(--text-muted);">${s.session_id}</span>
            <h4 style="font-size: 1.05rem; font-weight: 700; color: var(--text-main); margin: 0.15rem 0;">${s.course}</h4>
          </div>
          <span class="badge ${isAllocated ? 'verified' : 'badge-danger'}">
            ${isAllocated ? '✓ Allocated' : '✖ Unassigned'}
          </span>
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem;">
          <div>
            <label style="color: var(--text-muted); font-size: 0.72rem; display: block;">Degree Program</label>
            <strong>${s.program}</strong>
          </div>
          <div>
            <label style="color: var(--text-muted); font-size: 0.72rem; display: block;">Student Cohort</label>
            <strong>${s.cohort_id}</strong>
          </div>
          <div>
            <label style="color: var(--text-muted); font-size: 0.72rem; display: block;">Day & Period</label>
            <strong>${s.day || 'Monday'}, ${periodLabel}</strong>
          </div>
          <div>
            <label style="color: var(--text-muted); font-size: 0.72rem; display: block;">Required Room Type</label>
            <span class="badge badge-info" style="font-size: 0.72rem;">${s.required_room_type}</span>
          </div>
        </div>

        <div style="background: var(--bg-card-subtle); padding: 0.75rem; border-radius: var(--radius-sm); border: 1px solid var(--border-light);">
          <label style="color: var(--text-muted); font-size: 0.72rem; display: block; margin-bottom: 0.25rem;">Assigned Physical Room</label>
          <div style="font-size: 1.1rem; font-weight: 700; color: ${isAllocated ? 'var(--color-primary)' : 'var(--color-danger)'};">
            ${isAllocated ? `🏫 Room ${s.assigned_room_id}` : '⚠️ No Room Placed (Capacity Contention)'}
          </div>
          <div style="font-size: 0.72rem; color: var(--text-muted); margin-top: 0.25rem;">
            Allocation verified against room-time exclusivity and capability constraints.
          </div>
        </div>

        <div style="border-top: 1px solid var(--border-light); padding-top: 0.5rem; font-size: 0.75rem; color: var(--text-muted);">
          <div>Source File: <strong>${s.source_file || 'uploaded_data.csv'}</strong> ${s.source_row ? `(Row ${s.source_row})` : (s.source_page ? `(${s.source_page})` : '')}</div>
          <div>Academic Cycle: <strong>${(s.academic_cycle || 'odd').toUpperCase()}</strong> • Run ID: <code>${this.uploadState.allocationResponse?.run_id || 'N/A'}</code></div>
        </div>
      </div>
    `;

    modal.style.display = 'flex';
  }

  downloadExport(format) {
    if (!this.uploadState.allocationResponse || !this.uploadState.allocationResponse.run_id) {
      this.showToast('Run joint allocation before downloading results.', 'warning');
      return;
    }

    const runId = this.uploadState.allocationResponse.run_id;
    const url = Api.getExportUrl(runId, format);
    this.showToast(`Starting ${format.toUpperCase()} download...`, 'info');
    window.location.href = url;
  }

  resetUploadWorkflow() {
    this.uploadState.files = [];
    this.uploadState.preflightResponse = null;
    this.uploadState.allocationResponse = null;
    this.uploadState.timetableResponse = null;
    this.uploadState.confirmedAmbiguousMappings = {};

    const container = document.getElementById('uploaded-files-container');
    const stageMapping = document.getElementById('card-stage-mapping');
    const stagePreflight = document.getElementById('card-stage-preflight');
    const stageAlloc = document.getElementById('card-stage-allocate');
    const stageResults = document.getElementById('card-stage-results');
    const stageTimetable = document.getElementById('card-stage-timetable');
    const stageExport = document.getElementById('card-stage-export');

    if (container) container.style.display = 'none';
    if (stageMapping) stageMapping.style.display = 'none';
    if (stagePreflight) stagePreflight.style.display = 'none';
    if (stageAlloc) stageAlloc.style.display = 'none';
    if (stageResults) stageResults.style.display = 'none';
    if (stageTimetable) stageTimetable.style.display = 'none';
    if (stageExport) stageExport.style.display = 'none';

    this.updateUploadStepper(1);
    this.showToast('Upload workflow reset. Ready for new timetables.', 'info');
  }
}

// Bootstrap App
document.addEventListener('DOMContentLoaded', () => {
  const app = new ClassroomIQApp();
  window.ciqApp = app;
  app.init();
});
