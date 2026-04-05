---
name: weekly-report-digest
version: 2.0.0
description: 企业周报智能汇总 — 自动拉取邮箱周报，生成管理层摘要、风险预警、重点关注事项，并持续积累公司知识
triggers:
  - 周报
  - 周报汇总
  - 周报总结
  - weekly report
  - weekly digest
author: TG Robot AI Team
---

# 📊 周报智能汇总技能（weekly-report-digest）v2.0

## 功能概述

自动从企业邮箱拉取员工周报，进行多维度分析，生成结构化管理摘要，同时**持续积累公司知识**，让 OpenClaw 对公司的理解越来越深。

## 核心架构

```
邮箱周报 ──→ 拉取(IMAP) ──→ AI 分析 ──→ 管理层摘要
                                │
                                ├──→ 员工档案更新 (people/)
                                ├──→ 项目档案更新 (projects/)
                                ├──→ 风险登记更新 (risks/)
                                ├──→ 趋势分析更新 (trends/)
                                ├──→ 摘要存档 (digests/)
                                └──→ 公司快照合成 (company_snapshot.md)
                                          │
                                          └──→ OpenClaw bootstrap 加载
                                                （所有对话自动携带公司上下文）
```

## 触发方式

```
/weekly-report-digest              # 汇总本周周报
/weekly-report-digest last         # 汇总上周周报
/weekly-report-digest 2026-03-30 2026-04-05  # 指定日期范围
```

或自然语言：「汇总一下本周的周报」「上周周报有什么风险？」

---

## 执行流程（完整 4 步）

### Step 1: 拉取周报邮件

```bash
# 本周
python3 ~/.claude/skills/weekly-report-digest/scripts/fetch_weekly_reports.py --week this -o /tmp/weekly_reports.json

# 上周
python3 ~/.claude/skills/weekly-report-digest/scripts/fetch_weekly_reports.py --week last -o /tmp/weekly_reports.json

# 指定范围
python3 ~/.claude/skills/weekly-report-digest/scripts/fetch_weekly_reports.py --since 2026-03-30 --until 2026-04-05 -o /tmp/weekly_reports.json
```

### Step 2: 构建/更新公司知识记忆

```bash
python3 ~/.openclaw/skills/weekly-report-digest/scripts/build_knowledge.py /tmp/weekly_reports.json
```

此步骤会自动：
- 更新 `/root/.openclaw/memory-weekly/people/` 下的员工档案
- 更新 `/root/.openclaw/memory-weekly/projects/` 下的项目档案
- 写入 `/root/.openclaw/memory-weekly/risks/{week}.md` 风险登记
- 合成 `/root/.openclaw/memory-weekly/company_snapshot.md` 公司全景快照

### Step 3: 读取周报 JSON + 公司快照，AI 生成汇总

读取以下文件进行分析：
1. `/tmp/weekly_reports.json` — 本周所有周报原文
2. `/root/.openclaw/memory-weekly/company_snapshot.md` — 公司累积知识
3. `/root/.openclaw/memory-weekly/risks/` — 历史风险（对比上周）
4. `/root/.openclaw/memory-weekly/trends/` — 历史趋势（识别变化）

**分析时必须结合历史知识**，产出以下内容：
- 对比上周风险的变化（新增/解决/恶化）
- 识别项目进度趋势（加速/停滞/延期）
- 发现跨部门关联问题
- 标注人员工作负荷异常

### Step 4: 保存输出 + 更新 OpenClaw 上下文

1. 将完整摘要写入 `/root/.openclaw/memory-weekly/digests/{week}.md`
2. 更新趋势分析 `/root/.openclaw/memory-weekly/trends/{week}.md`
3. 重新合成 `company_snapshot.md`（含最新摘要引用）
4. 同步更新 OpenClaw 的 bootstrap context

---

## 公司知识记忆系统

### 存储位置
`/root/.openclaw/memory-weekly/`

### 目录结构与用途

| 目录 | 文件格式 | 内容 | 更新频率 |
|------|---------|------|---------|
| `people/` | `{email}.md` | 员工姓名、部门、角色、技能标签、项目履历、工作模式 | 每周增量 |
| `projects/` | `{code}.md` | 项目编号、客户、阶段、里程碑、风险历史、关键人员 | 每周增量 |
| `org/` | `departments.md` | 部门划分、团队组成、汇报关系 | 每月更新 |
| `risks/` | `{YYYY-Wxx}.md` | 按周归档的风险记录（红/黄/绿三级） | 每周新建 |
| `trends/` | `{YYYY-Wxx}.md` | 周度趋势对比、环比变化 | 每周新建 |
| `digests/` | `{YYYY-Wxx}.md` | 完整 AI 生成的周报汇总 | 每周新建 |
| `company_snapshot.md` | 单文件 | **核心快照**：公司简介+组织+项目+最近风险+摘要 | 每周重建 |

### 知识积累维度

每次处理周报时，从以下维度提取并积累知识：

#### 1. 人员画像（People Profiling）
- 姓名、邮箱、部门归属
- 技能标签（从工作内容提取：Vue3、PLC、OCR、机械臂等）
- 项目参与历史
- 工作模式特征（如：AI辅助开发、跨项目支持等）
- 周报提交习惯（时间、格式规范度）

#### 2. 项目知识图谱（Project Knowledge Graph）
- 项目编号 → 客户 → 产品类型 → 阶段流转
- 里程碑时间线
- 风险演变历史
- 关键技术决策
- 人员投入变化

#### 3. 风险模式识别（Risk Pattern Recognition）
- 重复出现的风险类型（如：掉车、异常件、交期延迟）
- 风险解决效率
- 跨项目共性风险

#### 4. 组织洞察（Org Insights）
- 团队规模变化
- 人员流动（新入职/离职）
- 跨部门协作频率
- 工作负荷分布

#### 5. 技术趋势（Tech Trends）
- 新技术/工具采用（如 AI 辅助开发、Claude Code、OpenClaw）
- 架构演进（V2→V3、黑盒/白盒）
- 复用模式（跨项目组件）

---

## 与 OpenClaw 的集成

### Bootstrap Context 注入

`company_snapshot.md` 会被注入到 OpenClaw agent 的系统上下文中，使得：

1. **日常对话**：OpenClaw 知道公司有哪些人、哪些项目、当前风险
2. **任务执行**：当用户说「帮我查一下菜鸟项目的进展」，OpenClaw 能直接调用项目档案
3. **决策辅助**：基于历史风险模式给出预警
4. **写作辅助**：写对外邮件时自动带入正确的项目信息和人员称呼

### OpenClaw Bootstrap 文件

技能会自动维护 `/root/.openclaw/agents/main/agent/company-context.md`，内容精炼自 `company_snapshot.md`，控制在 2000 token 以内，确保不占用过多上下文窗口。

### 按需深度查询

当 OpenClaw 需要更详细的信息时，可以读取：
- `memory-weekly/people/{email}.md` — 某人详细档案
- `memory-weekly/projects/{code}.md` — 某项目完整历史
- `memory-weekly/risks/{week}.md` — 某周风险详情
- `memory-weekly/digests/{week}.md` — 某周完整摘要

---

## 输出模板

```markdown
# 📊 周报汇总（{period}）

> 生成时间：{datetime} | 收到周报：{count} 封 | 覆盖部门：{departments}
> 公司知识库：{people_count} 名员工 | {project_count} 个项目 | 累计 {weeks_count} 周数据

---

## 🚨 一、风险预警（按严重程度排序）

### 🔴 高风险（需立即关注）
| # | 风险描述 | 涉及项目/人员 | 影响范围 | 建议措施 |
|---|---------|-------------|---------|---------|

### 🟡 中风险（需持续跟踪）
| # | 风险描述 | 涉及项目/人员 | 与上周对比 | 建议措施 |
|---|---------|-------------|----------|---------|

### 🟢 低风险/已解决
| # | 风险描述 | 处理状态 |
|---|---------|---------|

### 📈 风险趋势（vs 上周）
- 新增风险：{new}
- 持续未解决：{ongoing}
- 本周已解决：{resolved}

---

## 🎯 二、重点关注事项

### 📌 关键决策项（需管理层介入）
- {item}: {detail}（报告人：{name}）

### 📌 关键里程碑（本周/下周）
| 项目 | 里程碑 | 状态 | 预计时间 | 风险等级 |
|------|-------|------|---------|---------|

### 📌 跨部门协作需求
- {item}

---

## 📋 三、各部门/项目进展概要

### 🖥 软件研发
| 人员 | 本周进展 | 下周计划 | 完成度 |
|------|---------|---------|-------|

### 🤖 算法组
| 人员 | 本周进展 | 下周计划 | 完成度 |
|------|---------|---------|-------|

### 🏗 项目现场（在建项目）
| 项目编号 | 项目名称 | 当前阶段 | 本周进展 | 风险 |
|---------|---------|---------|---------|------|

### 📈 商务/销售
| 人员 | 本周进展 | 关键动态 |
|------|---------|---------|

### 👥 HR/行政
| 人员 | 本周进展 | 关键数据 |
|------|---------|---------|

### 🔧 项目管理/体系
| 人员 | 本周进展 | 关键产出 |
|------|---------|---------|

### 🌐 IT/基础设施
| 人员 | 本周进展 | 下周计划 |
|------|---------|---------|

---

## 📊 四、数据看板

### 周报提交统计
- 已提交：{submitted_count} 人
- 未提交：{missing_list}（对比上周名单）
- 提交时间分布：周五 {fri}封 / 周六 {sat}封 / 迟交 {late}封

### 项目全景
- 在建项目：{active_projects}
- 投运项目：{live_projects}
- 本周新增风险：{new_risks}
- 持续风险：{ongoing_risks}
- 已解决风险：{resolved_risks}

---

## 💡 五、AI 洞察与建议

基于本周周报 + 历史 {weeks_count} 周累积知识的交叉分析：

1. **趋势观察**：{trend}
2. **异常检测**：{anomaly}（对比历史模式）
3. **资源协调建议**：{resource}
4. **下周重点关注**：{focus_next_week}

---

## 🧠 六、知识库更新摘要

本次处理更新了以下公司知识：
- 员工档案更新：{people_updated} 人
- 项目档案更新：{projects_updated} 个
- 新增风险记录：{risks_added} 条
- 公司快照已同步到 OpenClaw

*下次对话中 OpenClaw 将自动携带更新后的公司上下文。*
```

---

## 邮箱配置

| 配置项 | 值 |
|--------|---|
| IMAP 服务器 | imap.exmail.qq.com:993 (SSL) |
| 用户名 | agent@tgkwrobot.com |
| 密码 | 环境变量 `WEEKLY_IMAP_PASS` |

## 文件结构

```
~/.claude/skills/weekly-report-digest/    # 技能代码
├── SKILL.md                              # 本文件（技能定义）
└── scripts/
    └── fetch_weekly_reports.py           # IMAP 邮件拉取

~/.openclaw/skills/weekly-report-digest/  # 知识构建代码
└── scripts/
    └── build_knowledge.py                # 知识提取 & 记忆更新

~/.openclaw/memory-weekly/                # 公司知识记忆库
├── company_snapshot.md                   # 全景快照（OpenClaw 加载）
├── people/                               # 员工档案
├── projects/                             # 项目档案
├── org/                                  # 组织结构
├── risks/                                # 风险登记
├── trends/                               # 趋势分析
└── digests/                              # 周报摘要存档
```
