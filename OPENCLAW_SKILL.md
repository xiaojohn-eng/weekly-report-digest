---
name: weekly-report-digest
description: 周报智能管理 — 自动拉取周报、AI分析、CEO简报、催报、风险预警、OKR追踪、知识积累
version: 2.0.0
triggers:
  - 周报
  - 周报汇总
  - 周报总结
  - 催报
  - 风险预警
  - OKR
  - 项目进度
---

# 📊 周报智能管理技能

CEO 周报管理全自动化：拉取周报 → AI 分析 → 简报邮件 → 风险预警 → 知识积累。

## 触发词

- "汇总本周周报" / "周报总结" / "上周周报"
- "催报" / "谁没交周报"
- "XX项目怎么样了" / "XX最近在做什么"（自动查知识库）
- "OKR进度" / "项目进度"
- "风险预警"

## 使用方式

### 1. 周报汇总
```bash
# 本周
python3 ~/.openclaw/skills/weekly-report-digest/scripts/ceo_briefing.py --week this --to shaw@tgkwrobot.com

# 上周
python3 ~/.openclaw/skills/weekly-report-digest/scripts/ceo_briefing.py --week last --to shaw@tgkwrobot.com

# 指定范围
python3 ~/.openclaw/skills/weekly-report-digest/scripts/ceo_briefing.py --since 2026-03-30 --until 2026-04-05 --to shaw@tgkwrobot.com

# 预览不发送
python3 ~/.openclaw/skills/weekly-report-digest/scripts/ceo_briefing.py --week this --dry-run
```

### 2. 催交周报
```bash
python3 ~/.openclaw/skills/weekly-report-digest/scripts/auto_reminder.py
```

### 3. AI 分析（独立运行）
```bash
# 拉取周报
python3 ~/.claude/skills/weekly-report-digest/scripts/fetch_weekly_reports.py --week this -o /tmp/weekly_reports.json

# AI 分析（风险+洞察+评分+技能+模式）
python3 ~/.openclaw/skills/weekly-report-digest/scripts/ai_analyze.py /tmp/weekly_reports.json -o /tmp/ai_analysis.json
```

### 4. OKR 追踪
```bash
# 查看 OKR 进度报告
python3 ~/.openclaw/skills/weekly-report-digest/scripts/okr_tracker.py --report

# 从周报追踪 OKR
python3 ~/.openclaw/skills/weekly-report-digest/scripts/okr_tracker.py --track /tmp/weekly_reports.json

# 添加新 OKR
python3 ~/.openclaw/skills/weekly-report-digest/scripts/okr_tracker.py --add "目标" "关键结果" "负责人"
```

### 5. CEO 邮件回复
```bash
python3 ~/.openclaw/skills/weekly-report-digest/scripts/ceo_reply_monitor.py
```

### 6. 实时预警
```bash
python3 ~/.openclaw/skills/weekly-report-digest/scripts/realtime_alert.py --scan
```

## 自动化定时任务（已配置 cron）

| 时间 | 任务 |
|------|------|
| 每天 9:00-21:00 每2h | 监听 CEO 邮件回复，AI 自动回答 |
| 周六 10:00 | 自动催交周报 |
| 周日 09:00 | CEO 智能简报（7步流水线） |

## 公司知识查询

当用户问公司相关问题时，按以下路径查找：

1. `MEMORY.md` — 公司快照（快速参考）
2. `/root/.openclaw/memory-weekly/people/{name}.md` — 员工档案
3. `/root/.openclaw/memory-weekly/projects/{TGxxx}.md` — 项目档案
4. `/root/.openclaw/memory-weekly/risks/` — 风险登记（最新 .md）
5. `/root/.openclaw/memory-weekly/digests/` — AI 分析（最新 _ai.json）
6. `/root/.openclaw/memory-weekly/org/departments.md` — 组织架构
7. `/root/.openclaw/memory-weekly/org/okr.json` — OKR 数据

## 邮箱配置

- 收件（IMAP）：agent@tgkwrobot.com / imap.exmail.qq.com:993
- 发件（SMTP）：agent@tgkwrobot.com / smtp.exmail.qq.com:465
- CEO 邮箱：shaw@tgkwrobot.com
- AI 分析：MiniMax M2.5 API

## 腾讯文档看板

项目进度看板：https://docs.qq.com/smartsheet/DV05BVE5PbXBUc09M
