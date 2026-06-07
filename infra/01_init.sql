CREATE TABLE departments (
    id INTEGER PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(160) NOT NULL UNIQUE,
    department_id INTEGER NOT NULL REFERENCES departments(id),
    role VARCHAR(80) NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE projects (
    id INTEGER PRIMARY KEY,
    name VARCHAR(160) NOT NULL,
    description TEXT,
    status VARCHAR(40) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE project_members (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    member_role VARCHAR(80) NOT NULL,
    joined_at DATE NOT NULL,
    UNIQUE (project_id, user_id)
);

CREATE TABLE tasks (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    assignee_id INTEGER NOT NULL REFERENCES users(id),
    title VARCHAR(240) NOT NULL,
    status VARCHAR(40) NOT NULL,
    priority VARCHAR(40) NOT NULL,
    estimated_hours NUMERIC(8, 2) NOT NULL,
    actual_hours NUMERIC(8, 2) NOT NULL,
    due_date DATE NOT NULL,
    completed_at DATE,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE attendance_records (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    work_date DATE NOT NULL,
    check_in_time TIMESTAMP,
    check_out_time TIMESTAMP,
    work_hours NUMERIC(5, 2) NOT NULL,
    status VARCHAR(40) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    UNIQUE (user_id, work_date)
);

CREATE TABLE devices (
    id INTEGER PRIMARY KEY,
    name VARCHAR(160) NOT NULL,
    device_type VARCHAR(80) NOT NULL,
    location VARCHAR(160) NOT NULL,
    status VARCHAR(40) NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE device_usage_records (
    id INTEGER PRIMARY KEY,
    device_id INTEGER NOT NULL REFERENCES devices(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    project_id INTEGER REFERENCES projects(id),
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    duration_minutes INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE meetings (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    title VARCHAR(240) NOT NULL,
    meeting_date TIMESTAMP NOT NULL,
    duration_minutes INTEGER NOT NULL,
    summary TEXT,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE meeting_participants (
    id INTEGER PRIMARY KEY,
    meeting_id INTEGER NOT NULL REFERENCES meetings(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at TIMESTAMP NOT NULL,
    UNIQUE (meeting_id, user_id)
);

CREATE INDEX idx_users_department_id ON users(department_id);
CREATE INDEX idx_project_members_project_id ON project_members(project_id);
CREATE INDEX idx_project_members_user_id ON project_members(user_id);
CREATE INDEX idx_tasks_project_id ON tasks(project_id);
CREATE INDEX idx_tasks_assignee_id ON tasks(assignee_id);
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_attendance_user_date ON attendance_records(user_id, work_date);
CREATE INDEX idx_attendance_work_date ON attendance_records(work_date);
CREATE INDEX idx_device_usage_device_time ON device_usage_records(device_id, start_time);
CREATE INDEX idx_device_usage_user_time ON device_usage_records(user_id, start_time);
CREATE INDEX idx_meetings_project_date ON meetings(project_id, meeting_date);
CREATE INDEX idx_meeting_participants_meeting_id ON meeting_participants(meeting_id);
CREATE INDEX idx_meeting_participants_user_id ON meeting_participants(user_id);

COMMENT ON TABLE departments IS '部门信息表，记录企业或实验室内部的组织部门。';
COMMENT ON TABLE users IS '用户信息表，记录员工或实验室成员的基础信息及所属部门。';
COMMENT ON TABLE projects IS '项目表，记录科研、平台或业务项目的基本信息和状态。';
COMMENT ON TABLE project_members IS '项目成员关系表，记录用户参与项目的角色和加入时间。';
COMMENT ON TABLE tasks IS '任务表，记录项目任务、负责人、工时、优先级和完成状态。';
COMMENT ON TABLE attendance_records IS '考勤记录表，记录用户每日打卡、工时和出勤状态。';
COMMENT ON TABLE devices IS '设备表，记录实验设备、服务器或工作站等资源信息。';
COMMENT ON TABLE device_usage_records IS '设备使用记录表，记录用户在项目中使用设备的时间段和时长。';
COMMENT ON TABLE meetings IS '会议表，记录项目会议的时间、时长、主题和纪要。';
COMMENT ON TABLE meeting_participants IS '会议参与关系表，记录用户参加会议的情况。';
