SET datestyle = 'ISO, YMD';

COPY departments (id, name, description, created_at)
FROM '/seed_data/departments.csv'
WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');

COPY users (id, name, email, department_id, role, created_at)
FROM '/seed_data/users.csv'
WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');

COPY projects (id, name, description, status, start_date, end_date, created_at)
FROM '/seed_data/projects.csv'
WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');

COPY project_members (id, project_id, user_id, member_role, joined_at)
FROM '/seed_data/project_members.csv'
WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');

COPY tasks (id, project_id, assignee_id, title, status, priority, estimated_hours, actual_hours, due_date, completed_at, created_at)
FROM '/seed_data/tasks.csv'
WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');

COPY attendance_records (id, user_id, work_date, check_in_time, check_out_time, work_hours, status, created_at)
FROM '/seed_data/attendance_records.csv'
WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');

COPY devices (id, name, device_type, location, status, created_at)
FROM '/seed_data/devices.csv'
WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');

COPY device_usage_records (id, device_id, user_id, project_id, start_time, end_time, duration_minutes, created_at)
FROM '/seed_data/device_usage_records.csv'
WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');

COPY meetings (id, project_id, title, meeting_date, duration_minutes, summary, created_at)
FROM '/seed_data/meetings.csv'
WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');

COPY meeting_participants (id, meeting_id, user_id, created_at)
FROM '/seed_data/meeting_participants.csv'
WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');

