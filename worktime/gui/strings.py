"""Every user-visible text of the app, in one place."""

APP_TITLE = "Work Time Sheet"

TAB_DAILY = "Daily entries"

LABEL_YEAR = "Year"
LABEL_MONTH = "Month"
BUTTON_PREVIOUS = "◀"
BUTTON_NEXT = "▶"
BUTTON_TODAY = "Today"
BUTTON_ADD_YEAR = "Add year"
BUTTON_EDIT = "Edit day"
BUTTON_DELETE = "Delete day"
BUTTON_SAVE = "Save"
BUTTON_CANCEL = "Cancel"

BUTTON_SQLITE_EDITOR = "Sqlite Editor"
BUTTON_BACKUP = "Backup DB"
BUTTON_EXPORT_CSV = "Export CSV"
BUTTON_IMPORT_WEEK_CSV = "Import week CSV"

BACKUP_TITLE = "Backup database"
BACKUP_DONE = "Database backed up to:\n{path}"
EXPORT_TITLE = "Export period to CSV"
EXPORT_DONE = "Exported {count} day(s) to:\n{path}"
IMPORT_WEEK_TITLE = "Import week CSV"
IMPORT_WEEK_DONE = "Imported {count} day(s) for week of {monday} to {friday}."
CSV_FILES = "CSV files"

SITE_BADGE_ONSITE = "On-site"
SITE_BADGE_REMOTE = "Remote"
GRID_HINT = "Tip: type HH:MM directly. Tab/Enter moves next, ↑/↓ moves between days, Space toggles On-site, Double-click Date for full form."

EDITOR_TITLE = "Sqlite Editor"
EDITOR_DATABASE = "Database: {path}"
EDITOR_PROGRAM_DB = " (this program)"
EDITOR_BUTTON_OPEN_SQL = "Open SQL file..."
EDITOR_BUTTON_OPEN_DB = "Open database..."
EDITOR_BUTTON_PROGRAM_DB = "Use program database"
EDITOR_BUTTON_RUN = "Run (Ctrl+Enter)"
EDITOR_BUTTON_CLEAR = "Clear"
EDITOR_DEFAULT_SQL = "SELECT * FROM entries ORDER BY work_date;"
EDITOR_HINT = "Runs the selected text, or everything if nothing is selected. All statements run in one transaction."
EDITOR_CONFIRM_TITLE = "Change the database?"
EDITOR_CONFIRM = "This SQL can change the data in:\n{path}\n\nRun it? Changes are saved immediately."
EDITOR_NULL = "NULL"
EDITOR_FILE_ERROR = "Cannot open the file"
EDITOR_SQL_FILES = "SQL files"
EDITOR_DB_FILES = "SQLite databases"
EDITOR_ALL_FILES = "All files"
EDITOR_TABLES_HEADER = "EXPLORER: TABLES"
EDITOR_NO_TABLES = "(no tables)"

COLUMN_DATE = "Date"
COLUMN_DAY = "Day"
COLUMN_ARRIVAL = "Arrival"
COLUMN_LUNCH_OUT = "Lunch out"
COLUMN_LUNCH_IN = "Lunch in"
COLUMN_DEPARTURE = "Departure"
COLUMN_SITE = "On-site"
COLUMN_WORKED = "Worked"
COLUMN_DEBT = "Debt"
COLUMN_EXCEEDING = "Exceeding"
COLUMN_NOTE = "Note"

YES = "yes"
NO = "no"
OPEN_DAY = "open"

FORM_TITLE_NEW = "New day"
FORM_TITLE_EDIT = "Edit day"
FIELD_DATE = "Date (dd/mm/yyyy)"
FIELD_ARRIVAL = "Arrival (HH:MM)"
FIELD_LUNCH_OUT = "Lunch out (HH:MM)"
FIELD_LUNCH_IN = "Lunch in (HH:MM)"
FIELD_DEPARTURE = "Departure (HH:MM)"
FIELD_REQUIRED = "Required hours (HH:MM)"
FIELD_ON_SITE = "Worked on-site (presencial)"
FIELD_EXACT = "Exact times (not approximate)"
FIELD_NOTE = "Note"

PREVIEW_INCOMPLETE = "Incomplete day: not counted in totals yet"
PREVIEW_TEMPLATE = "Worked {worked}   Debt {debt}   Exceeding {exceeding}"

CONFIRM_DELETE_TITLE = "Delete day"
CONFIRM_DELETE = "Delete {date}? This cannot be undone."
ERROR_TITLE = "Cannot save"
NOTHING_SELECTED = "Select a day first."

TOTALS_TEMPLATE = (
    "{month} {year}:  {days} days worked ({onsite} on-site, {remote} remote)   "
    "On-site {percent}   Worked {worked}   Debt {debt}   Exceeding {exceeding}   "
    "Balance {balance}"
)
TARGET_MET = "Target {target}% met (can still add {spare} remote day(s))"
TARGET_NOT_MET = "Target {target}% not met (need {needed} more on-site day(s))"
TARGET_NO_DAYS = "Target {target}%: no completed days yet"

TAB_DASHBOARD = "Dashboard"
DASH_PERIOD = "Period"
DASH_MONTH_CHOICE = "Month"
DASH_SEMESTER_CHOICE = "6 months"
DASH_YEAR_CHOICE = "Year"
DASH_SEMESTER_1 = "Jan-Jun"
DASH_SEMESTER_2 = "Jul-Dec"
DASH_ONSITE_CARD = "On-site"
DASH_HOURS_CARD = "Hours balance"
DASH_BREAKDOWN = "By month"
PIE_ONSITE_TITLE = "On-site vs remote days"
PIE_HOURS_TITLE = "Debt vs exceeding hours"
PIE_ONSITE = "On-site"
PIE_REMOTE = "Remote"
PIE_DEBT = "Debt"
PIE_EXCEEDING = "Exceeding"
PIE_EMPTY = "No data to show"
PIE_LEGEND = "{label}: {value} ({percent:.1f}%)"

STAT_DAYS = "Days worked"
STAT_ONSITE = "On-site days"
STAT_REMOTE = "Remote days"
STAT_PERCENT = "On-site percentage"
STAT_TARGET = "On-site target"
STAT_WORKED = "Worked"
STAT_DEBT = "Debt"
STAT_EXCEEDING = "Exceeding"
STAT_BALANCE = "Net balance"
STAT_CUMULATIVE = "Cumulative balance"

BREAKDOWN_COLUMNS = ("Month", "Days", "On-site / remote", "On-site %", "Worked", "Debt", "Exceeding", "Balance")
DASH_BREAKDOWN_COLUMNS = (*BREAKDOWN_COLUMNS, "Cumulative")
CSV_COLUMNS = (
    "Date", "Arrival", "Lunch out", "Lunch in", "Departure",
    "Required", "On-site", "Exact times", "Worked", "Debt", "Exceeding", "Note",
)

TAB_PROJECTION = "Projection"
PROJ_ONSITE_CARD = "6-Month On-Site Projection"
PROJ_HOURS_CARD = "6-Month Daily Hours Projection"
PROJ_WEEKLY_TABLE = "Remaining Weekly Plan (until end of 6-month period)"
PROJ_WORKED_SO_FAR = "Completed days so far"
PROJ_REMAINING_DAYS = "Remaining workdays (Mon-Fri)"
PROJ_TOTAL_PROJECTED = "Projected semester total"
PROJ_ONSITE_NEEDED = "On-site days still needed"
PROJ_ONSITE_PACE = "Suggested on-site pace"
PROJ_CURRENT_BALANCE = "Current semester balance"
PROJ_EXTRA_PER_DAY = "Extra time needed per day"
PROJ_DAILY_TARGET = "Suggested daily work time"
PROJ_WEEKLY_TARGET = "Suggested weekly work time"
PROJ_SCHEDULE = "Suggested daily schedule"
PROJ_COLUMNS = (
    "Week (Mon-Fri)",
    "Workdays",
    "Suggested On-site / Remote",
    "Daily Work Time",
    "Weekly Hours",
    "Projected On-site %",
    "Projected Balance",
)
