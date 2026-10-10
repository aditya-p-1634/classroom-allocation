# ClassroomIQ — Semester III Raw Timetable Inputs

## Included files
Upload the five branch-level CSV files together in one Upload & Allocate run:

- `computational_finance_semester_iii.csv`
- `software_systems_semester_iii.csv`
- `theoretical_computer_science_semester_iii.csv`
- `data_science_semester_iii.csv`
- `cyber_security_semester_iii.csv`

`combined_semester_iii_all_five_branches.csv` is a review/QA version with the same canonical input columns and all records from the five files.

## Extraction summary
- Branches/cohorts: 5
- Session occurrences: 140
- Multi-period lab sessions: 30
- Lecture sessions: 100
- Seminar sessions: 5
- Tutor Ward Meetings: 5
- Period slots occupied (multi-period sessions counted once per period): 170
- Cohort time overlaps detected during generated-data validation: 0
- Periods: P1–P8 only
- Academic cycle: `odd` (Semester III mapping; confirm if your institution uses a different cycle label)

## Important transformations
1. **All pre-assigned room IDs were removed.** There is no `assigned_room_id` column in these raw input files. The rooms visible in the original images were not copied into the CSVs.
2. The program identifiers use the current ClassroomIQ canonical program names: Computational Finance, Software Systems, Theoretical Computer Science, Data Science, Cyber Security.
3. Cohort IDs follow the current project convention: `odd_sem3_CF`, `odd_sem3_SS`, `odd_sem3_TCS`, `odd_sem3_DS`, and `odd_sem3_CY`.
4. Time blocks that span two periods in the source images (mostly lab blocks) are represented as `start_period` and `end_period`; no duplicated single-period rows were created for the same block.
5. Room names/room annotations and asterisks next to source room IDs were not carried over.
6. Student counts and required facilities are blank because they are not provided in the images.
7. `session_type` is `lab` for subjects explicitly named as labs, `seminar` for Seminar, `tutor_ward_meeting` for Tutor Ward Meeting, and `lecture` for the remaining subjects.

## Assumptions requiring confirmation before production allocation
- **Room type:** Explicit lab sessions are `laboratory`. All other events (including Seminar and Tutor Ward Meeting) are marked `classroom` for this first standardized input. This is an explicit provisional mapping based on the image legend (“Theory / Seminar / TWM rooms are shown in each cell | Lab room: …”), not verified room-capacity or facility evidence. Confirm or adjust if seminars/TWM require a different room type.
- **Academic cycle:** Semester III is mapped to `odd`, aligned with the current ClassroomIQ convention. Confirm against the academic calendar if necessary.
- **Facilities and enrollment:** No enrollment count or required-facility list was visible in the images, so these fields are blank and should not be treated as zero.
- **Period times:** The file retains period numbers P1–P8. The source grid’s visible time bands are P1 08:30–09:20, P2 09:20–10:10, P3 10:30–11:20, P4 11:20–12:10, P5 13:40–14:30, P6 14:30–15:20, P7 15:30–16:20, P8 16:20–17:10. The standard input schema uses period numbers, not time strings.
- The tool must still perform preflight validation; these CSVs have not yet been uploaded to/processed by the running ClassroomIQ API.

## Schema
program,cohort_id,course,academic_cycle,day,start_period,end_period,required_room_type,semester,session_type,student_count,required_facilities

## Generated-data validation
- computational_finance_semester_iii.csv: 28 sessions; 6 labs; 20 lectures; 1 seminars; 1 TWM; 34 period-slots; cohort overlaps=0; period bounds=PASS.
- software_systems_semester_iii.csv: 28 sessions; 6 labs; 20 lectures; 1 seminars; 1 TWM; 34 period-slots; cohort overlaps=0; period bounds=PASS.
- theoretical_computer_science_semester_iii.csv: 28 sessions; 6 labs; 20 lectures; 1 seminars; 1 TWM; 34 period-slots; cohort overlaps=0; period bounds=PASS.
- data_science_semester_iii.csv: 28 sessions; 6 labs; 20 lectures; 1 seminars; 1 TWM; 34 period-slots; cohort overlaps=0; period bounds=PASS.
- cyber_security_semester_iii.csv: 28 sessions; 6 labs; 20 lectures; 1 seminars; 1 TWM; 34 period-slots; cohort overlaps=0; period bounds=PASS.

## Recommended upload procedure
1. Open ClassroomIQ’s Upload & Allocate page.
2. Upload the five individual CSVs together (not only the combined review file).
3. Choose Synthetic Demo Profile for the demo run, unless you have verified actual capacity and room-availability data.
4. Review preflight mappings and every warning; explicitly confirm the non-lab room-type mapping if prompted.
5. Run joint allocation across all five branches.
6. Inspect the independent validation results before exporting branch-wise and combined allocated timetables.
