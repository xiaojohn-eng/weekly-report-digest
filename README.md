# 📊 weekly-report-digest

OpenClaw 周报智能管理技能 — CEO 周报管理全自动化。

## 功能

- **IMAP 周报拉取** — 自动从企业邮箱收取员工周报
- **AI 智能分析** — MiniMax M2.5 驱动，风险分级、系统性风险识别、CEO 洞察
- **CEO HTML 简报** — 品牌化邮件，含风险预警、项目进展、OKR 追踪
- **自动催报** — 对比花名册检测缺交，自动发提醒邮件
- **实时预警** — 高风险检测 → 企微推送 + 邮件预警
- **CEO 回复闭环** — 监听 CEO 对简报的回复，AI 自动查周报原文回答
- **周报质量评分** — 4 维度打分（完整度/风险清晰度/量化/可执行）
- **人员技能画像** — 从周报中提取技能标签，持续积累员工能力图谱
- **OKR 自动追踪** — 从周报中匹配 OKR 关键结果进展
- **预测性预警** — 3 周数据后自动识别风险模式
- **公司知识积累** — 每周自动更新员工档案/项目档案/风险登记，OpenClaw 越来越懂公司
- **腾讯文档看板** — 项目进度智能表格，自动更新

## 自动化时间线

| 时间 | 任务 |
|------|------|
| 每天 9:00-21:00 每 2h | CEO 邮件回复监听 |
| 周六 10:00 | 自动催交周报 |
| 周日 09:00 | CEO 智能简报（7 步流水线） |
| 实时 | 高风险 → 企微推送 + 邮件预警 |

## 架构

```
邮箱 IMAP → 拉取周报 → 知识提取 → AI 分析引擎
                                     │
                         ┌───────────┼───────────┐
                         ▼           ▼           ▼
                    风险分级     质量评分     技能画像
                    CEO洞察     OKR追踪     模式检测
                         │           │           │
                         └───────────┼───────────┘
                                     ▼
                         ┌──── 双向输出 ────┐
                         │                  │
                    📧 CEO 简报        🤖 OpenClaw
                    🚨 风险预警        知识记忆库
                         │
                    📧 CEO 回复 → AI 自动回答
```

## 文件结构

```
scripts/
├── fetch_weekly_reports.py   # IMAP 邮件拉取
├── build_knowledge.py        # 知识提取 + 项目去重
├── ai_analyze.py             # AI 分析引擎（5 模块）
├── ceo_briefing.py           # CEO 简报生成器（7 步流水线）
├── auto_reminder.py          # 自动催报 + 退信追踪
├── realtime_alert.py         # 实时预警（企微 + 邮件）
├── sync_to_openclaw.py       # 三路知识同步
├── ceo_reply_monitor.py      # CEO 回复闭环
└── okr_tracker.py            # OKR 自动追踪
```

## 环境变量

| 变量 | 用途 |
|------|------|
| `WEEKLY_IMAP_PASS` | 企业邮箱 IMAP 密码 |
| `MINIMAX_API_KEY` | MiniMax AI API Key |
| `MINIMAX_API_BASE` | MiniMax API Base URL |

## 依赖

- Python 3.10+
- beautifulsoup4, httpx
- OpenClaw (可选，用于企微推送和知识同步)

## 许可

MIT
