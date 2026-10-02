"""School-wide reference data that is not per-school configuration.

These lists are fallbacks used when a school has not configured its own values.
They live here rather than in `views.py` so services (timetable, academics) and
views share one definition instead of importing presentation code.
"""

# Subjects offered when a school has not set its own list. Subjects are stored
# as plain strings throughout the codebase (`School.subjects` is a JSON list and
# `ResultSheet.subject` is a CharField), so this stays a list of names.
DEFAULT_SUBJECTS = [
    'Mathematics',
    'English Language',
    'Basic Science',
    'Social Studies',
    'Civic Education',
    'Computer Studies',
    'Agricultural Science',
    'Business Studies',
]

# A first period that does not exist yet. A school defines its own bell schedule
# (name, start, end) in the timetable module; these are the starting points so a
# newly provisioned school has a usable day rather than an empty grid.
# (name, start_time, end_time, is_break)
DEFAULT_PERIODS = [
    ('P1', '08:00', '08:40', False),
    ('P2', '08:40', '09:20', False),
    ('P3', '09:20', '10:00', False),
    ('Break', '10:00', '10:30', True),
    ('P4', '10:30', '11:10', False),
    ('P5', '11:10', '11:50', False),
    ('P6', '11:50', '12:30', False),
    ('Lunch', '12:30', '13:10', True),
    ('P7', '13:10', '13:50', False),
    ('P8', '13:50', '14:30', False),
]

# Rooms offered when a school has not booked any. Rooms are free text on a
# lesson (matching the subject convention), so this is a suggestion list.
DEFAULT_ROOMS = [
    'Room 1',
    'Room 2',
    'Room 3',
    'Lab 1',
    'Lab 2',
    'Field',
]
