import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Workbook, SpreadsheetFile } from "@oai/artifact-tool";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const rootDir = path.resolve(__dirname, "..");
const dataDir = path.join(rootDir, "data");

const baseCreatedAt = "2026-01-01 09:00:00";

function createRng(seed) {
  let state = seed >>> 0;
  return () => {
    state = (state * 1664525 + 1013904223) >>> 0;
    return state / 0x100000000;
  };
}

const rng = createRng(20260605);

function pick(items) {
  return items[Math.floor(rng() * items.length)];
}

function pad(num) {
  return String(num).padStart(2, "0");
}

function toDateString(date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function toDateTimeString(date) {
  return `${toDateString(date)} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

function addDays(date, days) {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

function addMinutes(date, minutes) {
  const next = new Date(date);
  next.setMinutes(next.getMinutes() + minutes);
  return next;
}

function csvEscape(value) {
  if (value === null || value === undefined) return "";
  const text = String(value);
  if (/[",\n\r]/.test(text)) {
    return `"${text.replaceAll('"', '""')}"`;
  }
  return text;
}

async function writeCsv(name, columns, rows) {
  const lines = [
    columns.join(","),
    ...rows.map((row) => columns.map((col) => csvEscape(row[col])).join(",")),
  ];
  await fs.writeFile(path.join(dataDir, `${name}.csv`), `${lines.join("\n")}\n`, "utf8");
}

function number(value, digits = 2) {
  return Number(value.toFixed(digits));
}

const departments = [
  { id: 1, name: "研发部", description: "负责后端、前端、平台和业务系统研发", created_at: baseCreatedAt },
  { id: 2, name: "算法组", description: "负责模型训练、算法评估和智能应用落地", created_at: baseCreatedAt },
  { id: 3, name: "数据平台组", description: "负责数据采集、清洗、仓库和分析平台建设", created_at: baseCreatedAt },
  { id: 4, name: "产品组", description: "负责需求分析、产品设计和项目协调", created_at: baseCreatedAt },
  { id: 5, name: "测试组", description: "负责功能测试、自动化测试和质量保障", created_at: baseCreatedAt },
  { id: 6, name: "运维组", description: "负责部署、监控、网络和基础设施维护", created_at: baseCreatedAt },
];

const surnames = ["王", "李", "张", "刘", "陈", "杨", "赵", "黄", "周", "吴", "徐", "孙", "胡", "朱", "高", "林", "何", "郭", "马", "罗"];
const givenNames = ["子轩", "宇航", "浩然", "梓涵", "一诺", "思远", "明哲", "佳怡", "雨桐", "欣然", "文博", "俊杰", "嘉豪", "若曦", "诗涵", "天佑", "晨曦", "睿泽", "雅婷", "亦辰"];
const roles = ["后端工程师", "前端工程师", "算法工程师", "数据工程师", "产品经理", "测试工程师", "运维工程师", "研究助理"];

const users = Array.from({ length: 60 }, (_, index) => {
  const id = index + 1;
  const department_id = ((id - 1) % departments.length) + 1;
  const name = `${surnames[index % surnames.length]}${givenNames[(index * 7) % givenNames.length]}`;
  return {
    id,
    name,
    email: `user${pad(id)}@example.com`,
    department_id,
    role: roles[(id + department_id) % roles.length],
    created_at: baseCreatedAt,
  };
});

const projectNames = [
  "科研工效分析平台",
  "设备使用监控系统",
  "智能考勤分析系统",
  "项目进度管理平台",
  "会议纪要结构化系统",
  "数据质量监控平台",
  "实验室资源调度系统",
  "任务协同分析平台",
  "知识库问答系统",
  "实时消息推送平台",
  "用户行为分析系统",
  "数据查询 Agent 平台",
];

const projectStatuses = ["planning", "active", "active", "active", "completed", "paused"];
const projects = projectNames.map((name, index) => {
  const startDate = addDays(new Date("2025-11-01T00:00:00"), index * 12);
  const status = projectStatuses[index % projectStatuses.length];
  const endDate = status === "completed" ? addDays(startDate, 90) : null;
  return {
    id: index + 1,
    name,
    description: `${name}用于支持实验室数字化管理和数据分析。`,
    status,
    start_date: toDateString(startDate),
    end_date: endDate ? toDateString(endDate) : "",
    created_at: `${toDateString(startDate)} 09:00:00`,
  };
});

const projectMembers = [];
let projectMemberId = 1;
for (const project of projects) {
  const memberCount = 8 + Math.floor(rng() * 8);
  const selected = new Set();
  while (selected.size < memberCount) {
    selected.add(1 + Math.floor(rng() * users.length));
  }
  for (const userId of selected) {
    projectMembers.push({
      id: projectMemberId++,
      project_id: project.id,
      user_id: userId,
      member_role: pick(["负责人", "后端开发", "前端开发", "算法支持", "数据开发", "测试支持", "产品协调"]),
      joined_at: project.start_date,
    });
  }
}

const taskStatus = ["todo", "in_progress", "review", "done", "blocked"];
const priorities = ["low", "medium", "high", "urgent"];
const taskTopics = ["接口开发", "数据同步", "页面联调", "模型评估", "需求梳理", "测试用例", "部署配置", "指标看板", "权限控制", "日志分析"];

const tasks = Array.from({ length: 420 }, (_, index) => {
  const id = index + 1;
  const project = pick(projects);
  const members = projectMembers.filter((member) => member.project_id === project.id);
  const member = pick(members);
  const created = addDays(new Date(`${project.start_date}T09:00:00`), Math.floor(rng() * 130));
  const due = addDays(created, 3 + Math.floor(rng() * 25));
  const status = pick(taskStatus);
  const estimated = 2 + rng() * 30;
  const actual = status === "done" ? estimated * (0.7 + rng() * 0.8) : estimated * rng();
  const completed = status === "done" ? addDays(due, -Math.floor(rng() * 5)) : null;
  return {
    id,
    project_id: project.id,
    assignee_id: member.user_id,
    title: `${project.name}-${pick(taskTopics)}-${id}`,
    status,
    priority: pick(priorities),
    estimated_hours: number(estimated),
    actual_hours: number(actual),
    due_date: toDateString(due),
    completed_at: completed ? toDateString(completed) : "",
    created_at: toDateTimeString(created),
  };
});

const attendanceRecords = [];
let attendanceId = 1;
const startDate = new Date("2026-01-01T00:00:00");
const endDate = new Date("2026-06-04T00:00:00");
for (let date = startDate; date <= endDate; date = addDays(date, 1)) {
  const day = date.getDay();
  if (day === 0 || day === 6) continue;
  for (const user of users) {
    const absenceChance = rng();
    let status = "normal";
    let workHours = 7 + rng() * 2;
    if (absenceChance < 0.035) {
      status = "absent";
      workHours = 0;
    } else if (absenceChance < 0.12) {
      status = "late";
      workHours = 5.5 + rng() * 2;
    } else if (absenceChance > 0.92) {
      status = "overtime";
      workHours = 9 + rng() * 2.5;
    }
    const checkIn = new Date(`${toDateString(date)}T09:00:00`);
    checkIn.setMinutes(Math.floor(rng() * 45));
    const checkOut = addMinutes(checkIn, Math.round(workHours * 60));
    attendanceRecords.push({
      id: attendanceId++,
      user_id: user.id,
      work_date: toDateString(date),
      check_in_time: workHours === 0 ? "" : toDateTimeString(checkIn),
      check_out_time: workHours === 0 ? "" : toDateTimeString(checkOut),
      work_hours: number(workHours),
      status,
      created_at: `${toDateString(date)} 20:00:00`,
    });
  }
}

const deviceTypes = ["GPU服务器", "高性能工作站", "传感器", "实验设备", "存储节点", "边缘计算盒"];
const locations = ["A栋101", "A栋203", "B栋305", "实验室一", "实验室二", "机房"];
const devices = Array.from({ length: 25 }, (_, index) => ({
  id: index + 1,
  name: `${pick(deviceTypes)}-${pad(index + 1)}`,
  device_type: deviceTypes[index % deviceTypes.length],
  location: locations[index % locations.length],
  status: index % 13 === 0 ? "maintenance" : "available",
  created_at: baseCreatedAt,
}));

const deviceUsageRecords = Array.from({ length: 1200 }, (_, index) => {
  const id = index + 1;
  const date = addDays(startDate, Math.floor(rng() * 155));
  const hour = 8 + Math.floor(rng() * 10);
  const start = new Date(`${toDateString(date)}T${pad(hour)}:${pad(Math.floor(rng() * 60))}:00`);
  const duration = 30 + Math.floor(rng() * 260);
  const end = addMinutes(start, duration);
  return {
    id,
    device_id: pick(devices).id,
    user_id: pick(users).id,
    project_id: pick(projects).id,
    start_time: toDateTimeString(start),
    end_time: toDateTimeString(end),
    duration_minutes: duration,
    created_at: toDateTimeString(end),
  };
});

const meetings = Array.from({ length: 180 }, (_, index) => {
  const id = index + 1;
  const project = pick(projects);
  const date = addDays(new Date(`${project.start_date}T10:00:00`), Math.floor(rng() * 150));
  date.setHours(9 + Math.floor(rng() * 8), [0, 15, 30, 45][Math.floor(rng() * 4)], 0, 0);
  return {
    id,
    project_id: project.id,
    title: `${project.name}第${id}次项目会议`,
    meeting_date: toDateTimeString(date),
    duration_minutes: [30, 45, 60, 90, 120][Math.floor(rng() * 5)],
    summary: `讨论${project.name}当前进展、风险和下一步任务安排。`,
    created_at: toDateTimeString(date),
  };
});

const meetingParticipants = [];
let participantId = 1;
for (const meeting of meetings) {
  const members = projectMembers.filter((member) => member.project_id === meeting.project_id);
  const selected = new Set();
  const count = Math.min(members.length, 4 + Math.floor(rng() * 7));
  while (selected.size < count) {
    selected.add(pick(members).user_id);
  }
  for (const userId of selected) {
    meetingParticipants.push({
      id: participantId++,
      meeting_id: meeting.id,
      user_id: userId,
      created_at: meeting.meeting_date,
    });
  }
}

const tables = [
  { name: "departments", columns: ["id", "name", "description", "created_at"], rows: departments },
  { name: "users", columns: ["id", "name", "email", "department_id", "role", "created_at"], rows: users },
  { name: "projects", columns: ["id", "name", "description", "status", "start_date", "end_date", "created_at"], rows: projects },
  { name: "project_members", columns: ["id", "project_id", "user_id", "member_role", "joined_at"], rows: projectMembers },
  { name: "tasks", columns: ["id", "project_id", "assignee_id", "title", "status", "priority", "estimated_hours", "actual_hours", "due_date", "completed_at", "created_at"], rows: tasks },
  { name: "attendance_records", columns: ["id", "user_id", "work_date", "check_in_time", "check_out_time", "work_hours", "status", "created_at"], rows: attendanceRecords },
  { name: "devices", columns: ["id", "name", "device_type", "location", "status", "created_at"], rows: devices },
  { name: "device_usage_records", columns: ["id", "device_id", "user_id", "project_id", "start_time", "end_time", "duration_minutes", "created_at"], rows: deviceUsageRecords },
  { name: "meetings", columns: ["id", "project_id", "title", "meeting_date", "duration_minutes", "summary", "created_at"], rows: meetings },
  { name: "meeting_participants", columns: ["id", "meeting_id", "user_id", "created_at"], rows: meetingParticipants },
];

function columnName(index) {
  let name = "";
  let n = index;
  while (n > 0) {
    const rem = (n - 1) % 26;
    name = String.fromCharCode(65 + rem) + name;
    n = Math.floor((n - 1) / 26);
  }
  return name;
}

async function writeWorkbook() {
  const workbook = Workbook.create();
  const readme = workbook.worksheets.add("README");
  const summaryRows = [
    ["table_name", "row_count", "description"],
    ["departments", departments.length, "部门表"],
    ["users", users.length, "用户表"],
    ["projects", projects.length, "项目表"],
    ["project_members", projectMembers.length, "项目成员关系表"],
    ["tasks", tasks.length, "任务表"],
    ["attendance_records", attendanceRecords.length, "考勤记录表"],
    ["devices", devices.length, "设备表"],
    ["device_usage_records", deviceUsageRecords.length, "设备使用记录表"],
    ["meetings", meetings.length, "会议表"],
    ["meeting_participants", meetingParticipants.length, "会议参与关系表"],
  ];
  readme.getRange(`A1:C${summaryRows.length}`).values = summaryRows;

  for (const table of tables) {
    const sheet = workbook.worksheets.add(table.name);
    const values = [
      table.columns,
      ...table.rows.map((row) => table.columns.map((column) => row[column] ?? "")),
    ];
    const endCell = `${columnName(table.columns.length)}${values.length}`;
    sheet.getRange(`A1:${endCell}`).values = values;
  }

  const output = await SpreadsheetFile.exportXlsx(workbook);
  await output.save(path.join(dataDir, "sample_dataset.xlsx"));
}

await fs.mkdir(dataDir, { recursive: true });
for (const table of tables) {
  await writeCsv(table.name, table.columns, table.rows);
}
await writeWorkbook();

const counts = Object.fromEntries(tables.map((table) => [table.name, table.rows.length]));
await fs.writeFile(path.join(dataDir, "dataset_counts.json"), `${JSON.stringify(counts, null, 2)}\n`, "utf8");

console.log(JSON.stringify(counts, null, 2));
