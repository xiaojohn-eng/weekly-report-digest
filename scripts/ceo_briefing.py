#!/usr/bin/env python3
"""
CEO 周报智能简报 — 全自动流水线

完整流程：
  1. IMAP 拉取本周周报
  2. 构建/更新公司知识记忆
  3. 对比上周风险，生成变化追踪
  4. 生成 HTML 格式的 CEO 简报邮件
  5. 自动发送至 CEO 邮箱
  6. 同步更新 OpenClaw 记忆

用法:
  python3 ceo_briefing.py                    # 本周简报
  python3 ceo_briefing.py --week last        # 上周简报
  python3 ceo_briefing.py --dry-run          # 只生成不发送
  python3 ceo_briefing.py --to other@xx.com  # 发给其他人
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent
# fetch_weekly_reports.py 在 claude skills 目录
CLAUDE_SCRIPTS_DIR = Path("/root/.claude/skills/weekly-report-digest/scripts")
MEMORY_DIR = Path("/root/.openclaw/memory-weekly")
SEND_EMAIL_SCRIPT = "/root/.claude/send_email.py"
CEO_EMAIL = "shaw@tgkwrobot.com"

# 品牌色
BRAND_COLOR = "#e05a2b"
BRAND_BG = "#fef6f3"


def run_step(desc, cmd, timeout=60):
    """运行子步骤并返回输出。"""
    print(f"  ⏳ {desc}...", file=sys.stderr)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        print(f"  ❌ {desc} 失败: {result.stderr[:200]}", file=sys.stderr)
        return None
    print(f"  ✅ {desc}", file=sys.stderr)
    return result.stdout


def fetch_reports(week_arg):
    """Step 1: 拉取周报。"""
    cmd = [
        sys.executable,
        str(CLAUDE_SCRIPTS_DIR / "fetch_weekly_reports.py"),
        "--week", week_arg,
        "-o", "/tmp/weekly_reports.json",
    ]
    run_step("拉取周报邮件", cmd, timeout=120)
    if not Path("/tmp/weekly_reports.json").exists():
        return None
    with open("/tmp/weekly_reports.json", encoding="utf-8") as f:
        return json.load(f)


def build_knowledge():
    """Step 2: 构建知识。"""
    cmd = [
        sys.executable,
        str(SCRIPTS_DIR / "build_knowledge.py"),
        "/tmp/weekly_reports.json",
    ]
    output = run_step("构建公司知识", cmd, timeout=30)
    if output:
        try:
            return json.loads(output)
        except Exception:
            pass
    return {}


def load_previous_risks():
    """加载上周风险用于对比。"""
    risks_dir = MEMORY_DIR / "risks"
    if not risks_dir.exists():
        return ""
    risk_files = sorted(risks_dir.glob("*.md"))
    if len(risk_files) >= 2:
        return risk_files[-2].read_text(encoding="utf-8")
    return ""


def analyze_risk_changes(current_risks_path, prev_risks_text):
    """分析风险变化：新增/持续/解决。"""
    if not current_risks_path or not Path(current_risks_path).exists():
        return {"new": [], "ongoing": [], "resolved": []}

    current = Path(current_risks_path).read_text(encoding="utf-8") if current_risks_path else ""

    # 提取当前风险人员+关键词
    current_items = set(re.findall(r"\*\*(.+?)\*\*", current))
    prev_items = set(re.findall(r"\*\*(.+?)\*\*", prev_risks_text))

    return {
        "new": list(current_items - prev_items),
        "ongoing": list(current_items & prev_items),
        "resolved": list(prev_items - current_items),
    }


def classify_reports(data):
    """将周报按部门分类。"""
    dept_keywords = {
        "软件研发": ["开发", "V2", "V3", "前端", "后端", "PDA", "系统", "代码", "Bug", "工作站", "黑盒", "白盒"],
        "算法组": ["算法", "视觉", "模型", "训练", "机械臂", "MinIO", "3D"],
        "项目现场": ["安装", "调试", "现场", "施工", "发货", "里程碑", "上电"],
        "项目管理": ["体系", "SOP", "验收", "项目监管", "PM"],
        "商务/销售": ["招标", "报价", "客户", "商务", "回款", "中标"],
        "HR/行政": ["招聘", "薪资", "考勤", "入职"],
        "IT/基础设施": ["部署", "VPN", "环境", "远程", "服务器"],
    }

    classified = {}
    for report in data.get("reports", []):
        text = report.get("subject", "") + " " + report.get("body", "")[:500]
        best_dept = "其他"
        best_score = 0
        # 项目编号优先
        if re.search(r"TG\d{3}", report.get("subject", "")):
            best_dept = "项目现场"
            best_score = 10
        for dept, kws in dept_keywords.items():
            score = sum(1 for kw in kws if kw in text)
            if score > best_score:
                best_dept = dept
                best_score = score
        classified.setdefault(best_dept, []).append(report)

    return classified


def extract_key_items(data):
    """提取需要 CEO 关注的关键事项。"""
    items = []
    for report in data.get("reports", []):
        body = report.get("body", "")
        name = report.get("sender_name", "")

        # 涉及金额/成本
        if re.search(r"成本|费用|万|报价|尾款|付款", body):
            match = re.search(r"[^。\n]*(?:成本|费用|万|报价|尾款|付款)[^。\n]*", body)
            if match:
                items.append({"type": "💰 财务", "reporter": name, "detail": match.group()[:100]})

        # 涉及客户关系敏感事项
        if re.search(r"源代码|投诉|不满|竞对|终验|客户要求", body):
            match = re.search(r"[^。\n]*(?:源代码|投诉|不满|竞对|终验|客户要求)[^。\n]*", body)
            if match:
                items.append({"type": "⚠️ 客户", "reporter": name, "detail": match.group()[:100]})

        # 涉及安全事故
        if re.search(r"掉车|事故|损坏|安全|急停", body):
            match = re.search(r"[^。\n]*(?:掉车|事故|损坏|安全|急停)[^。\n]*", body)
            if match:
                items.append({"type": "🚨 安全", "reporter": name, "detail": match.group()[:100]})

        # 招聘/人员
        if re.search(r"招聘|面试|入职|离职|缺人", body):
            match = re.search(r"[^。\n]*(?:招聘|面试|入职|离职|缺人)[^。\n]*", body)
            if match:
                items.append({"type": "👥 人事", "reporter": name, "detail": match.group()[:100]})

    # 去重
    seen = set()
    unique = []
    for item in items:
        key = item["detail"][:50]
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique[:15]  # 最多15条


def submission_stats(data):
    """统计周报提交情况。"""
    reports = data.get("reports", [])
    # 按天统计
    day_counts = {}
    submitters = set()
    for r in reports:
        date_str = r.get("date", "")
        submitters.add(r.get("sender_name", ""))
        try:
            dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
            day_name = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][dt.weekday()]
            day_counts[day_name] = day_counts.get(day_name, 0) + 1
        except Exception:
            pass

    return {
        "total": len(reports),
        "unique_submitters": len(submitters),
        "submitters": sorted(submitters),
        "by_day": day_counts,
    }


def generate_html_briefing(data, knowledge_stats, risk_changes, classified, key_items, stats):
    """生成 HTML 格式的 CEO 简报。"""
    period = data.get("period", "未知")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # 风险摘要
    risks_dir = MEMORY_DIR / "risks"
    risk_files = sorted(risks_dir.glob("*.md"), reverse=True) if risks_dir.exists() else []
    risk_html = ""
    if risk_files:
        risk_content = risk_files[0].read_text(encoding="utf-8")
        # 提取高/中风险
        for level, color, label in [("🔴 高风险", "#dc3545", "高风险"), ("🟡 中风险", "#ffc107", "中风险")]:
            if level in risk_content:
                section = risk_content.split(level)[-1].split("## ")[0]
                blocks = re.findall(r"\*\*(.+?)\*\*\s*\((.+?)\)\n> (.+?)(?=\n\n\*\*|\n\n##|\Z)", section, re.DOTALL)
                if blocks:
                    risk_html += f'<h3 style="color:{color};margin:15px 0 8px;">{level}</h3>'
                    risk_html += '<table style="width:100%;border-collapse:collapse;font-size:14px;">'
                    risk_html += f'<tr style="background:{color};color:#fff;"><th style="padding:8px;text-align:left;">报告人</th><th style="padding:8px;text-align:left;">来源</th><th style="padding:8px;text-align:left;">风险描述</th></tr>'
                    for name, src, detail in blocks:
                        detail_clean = re.sub(r'\s+', ' ', detail).strip()[:120]
                        risk_html += f'<tr style="border-bottom:1px solid #eee;"><td style="padding:8px;font-weight:bold;">{name}</td><td style="padding:8px;font-size:12px;">{src[:25]}</td><td style="padding:8px;">{detail_clean}</td></tr>'
                    risk_html += '</table>'

    # 风险变化
    change_html = ""
    if risk_changes.get("new") or risk_changes.get("resolved"):
        change_html = '<div style="background:#f0f9ff;padding:12px;border-radius:8px;margin:10px 0;">'
        if risk_changes["new"]:
            change_html += f'<p style="margin:4px 0;">🆕 <b>新增风险</b>：{", ".join(risk_changes["new"][:5])}</p>'
        if risk_changes["ongoing"]:
            change_html += f'<p style="margin:4px 0;">🔄 <b>持续跟踪</b>：{", ".join(risk_changes["ongoing"][:5])}</p>'
        if risk_changes["resolved"]:
            change_html += f'<p style="margin:4px 0;">✅ <b>本周解决</b>：{", ".join(risk_changes["resolved"][:5])}</p>'
        change_html += '</div>'

    # 关键事项
    key_html = ""
    if key_items:
        key_html = '<table style="width:100%;border-collapse:collapse;font-size:14px;">'
        key_html += f'<tr style="background:{BRAND_COLOR};color:#ffffff !important;"><th style="padding:8px;text-align:left;color:#ffffff !important;">类型</th><th style="padding:8px;text-align:left;color:#ffffff !important;">报告人</th><th style="padding:8px;text-align:left;color:#ffffff !important;">事项</th></tr>'
        for item in key_items:
            key_html += f'<tr style="border-bottom:1px solid #eee;"><td style="padding:8px;">{item["type"]}</td><td style="padding:8px;font-weight:bold;">{item["reporter"]}</td><td style="padding:8px;">{item["detail"]}</td></tr>'
        key_html += '</table>'

    # 部门概要
    dept_html = ""
    for dept, reports in sorted(classified.items()):
        names = ", ".join(set(r["sender_name"] for r in reports))
        dept_html += f'''
        <div style="background:#fff;border:1px solid #eee;border-radius:8px;padding:12px;margin:8px 0;">
            <h4 style="margin:0 0 6px;color:{BRAND_COLOR};">{dept}（{len(reports)}人）</h4>
            <p style="margin:0;font-size:13px;color:#666;">{names}</p>
        </div>'''

    # 提交统计
    day_str = " | ".join(f"{k}: {v}封" for k, v in sorted(stats["by_day"].items()))

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:700px;margin:0 auto;padding:20px;color:#333;background:#fff;">

<div style="background:{BRAND_COLOR};color:#fff;padding:20px;border-radius:12px 12px 0 0;text-align:center;">
    <h1 style="margin:0;font-size:22px;color:#fff;">📊 CEO 周报智能简报</h1>
    <p style="margin:8px 0 0;opacity:0.9;font-size:14px;color:#fff;">{period}</p>
</div>

<div style="background:{BRAND_BG};padding:15px;border:1px solid #f0d0c0;">
    <table style="width:100%;font-size:13px;">
        <tr>
            <td>📨 收到周报 <b>{stats['total']}</b> 封</td>
            <td>👥 提交人数 <b>{stats['unique_submitters']}</b> 人</td>
            <td>⚠️ 风险 <b>{knowledge_stats.get('risks_found', 0)}</b> 条</td>
        </tr>
        <tr>
            <td colspan="3" style="padding-top:5px;color:#888;">{day_str}</td>
        </tr>
    </table>
</div>

<div style="padding:0 15px 15px;border:1px solid #eee;border-top:none;">

<h2 style="color:{BRAND_COLOR};border-bottom:2px solid {BRAND_COLOR};padding-bottom:8px;margin-top:20px;">🚨 一、风险预警</h2>
{risk_html or '<p style="color:#999;">本周无重大风险报告</p>'}

{change_html}

<h2 style="color:{BRAND_COLOR};border-bottom:2px solid {BRAND_COLOR};padding-bottom:8px;margin-top:25px;">🎯 二、CEO 关注事项</h2>
{key_html or '<p style="color:#999;">本周无需特别关注的事项</p>'}

<h2 style="color:{BRAND_COLOR};border-bottom:2px solid {BRAND_COLOR};padding-bottom:8px;margin-top:25px;">📋 三、各部门概要</h2>
{dept_html}

<h2 style="color:{BRAND_COLOR};border-bottom:2px solid {BRAND_COLOR};padding-bottom:8px;margin-top:25px;">📊 四、知识库更新</h2>
<div style="background:#f8f9fa;padding:12px;border-radius:8px;font-size:13px;">
    <p style="margin:4px 0;">👤 员工档案更新：<b>{knowledge_stats.get('people_updated', 0)}</b> 人</p>
    <p style="margin:4px 0;">📁 项目档案更新：<b>{knowledge_stats.get('projects_found', 0)}</b> 个</p>
    <p style="margin:4px 0;">⚠️ 风险记录：🔴 {knowledge_stats.get('risk_high', 0)} 高 / 🟡 {knowledge_stats.get('risk_medium', 0)} 中 / 🟢 {knowledge_stats.get('risk_low', 0)} 低</p>
    <p style="margin:4px 0;color:#888;">公司知识已同步到 OpenClaw，下次对话自动携带上下文</p>
</div>

</div>

<div style="text-align:center;padding:15px;font-size:12px;color:#999;border-top:1px solid #eee;">
    ⚡ 由 OpenClaw AI 助手自动生成 | {now}<br>
    天下先智创机器人 · AI 管理赋能
</div>

</body>
</html>"""
    return html


def build_ai_section(ai_analysis, ai_insights):
    """构建 AI 分析 HTML 段落。"""
    if not ai_insights and not ai_analysis:
        return ""

    html = f'<h2 style="color:{BRAND_COLOR};border-bottom:2px solid {BRAND_COLOR};padding-bottom:8px;margin-top:25px;">🤖 五、AI 智能分析</h2>'

    # CEO 总结
    summary = ai_insights.get("executive_summary", "")
    if summary:
        html += f'<div style="background:#fff3e6;padding:12px;border-left:4px solid {BRAND_COLOR};border-radius:4px;margin:10px 0;font-size:15px;">{summary}</div>'

    # Top 3 优先事项
    priorities = ai_insights.get("top3_priorities", [])
    if priorities:
        html += '<h3 style="margin:15px 0 8px;">🎯 CEO 优先处理事项</h3><ol style="font-size:14px;">'
        for p in priorities[:3]:
            if isinstance(p, dict):
                html += f'<li style="margin:8px 0;"><b>{p.get("item","")}</b><br><span style="color:#666;">{p.get("reason","")}</span><br><span style="color:{BRAND_COLOR};">→ {p.get("action","")}</span></li>'
            else:
                html += f'<li style="margin:8px 0;">{p}</li>'
        html += '</ol>'

    # 系统性风险
    systemic = ai_analysis.get("systemic_risks", [])
    if systemic:
        html += '<h3 style="margin:15px 0 8px;">🔗 系统性风险（多人同时反映）</h3>'
        html += f'<table style="width:100%;border-collapse:collapse;font-size:14px;"><tr style="background:#ff8c00;color:#fff;"><th style="padding:8px;text-align:left;color:#fff !important;">风险</th><th style="padding:8px;text-align:left;color:#fff !important;">涉及人员</th></tr>'
        for s in systemic[:5]:
            if isinstance(s, dict):
                people = ", ".join(s.get("involved_people", []))
                html += f'<tr style="border-bottom:1px solid #eee;"><td style="padding:8px;">{s.get("description","")}</td><td style="padding:8px;">{people}</td></tr>'
        html += '</table>'

    # 跨部门问题
    cross = ai_insights.get("cross_department_issues", [])
    if cross:
        html += '<h3 style="margin:15px 0 8px;">🔀 跨部门协作问题</h3><ul style="font-size:14px;">'
        for c in cross[:5]:
            html += f'<li>{c}</li>'
        html += '</ul>'

    # 趋势对比
    trend = ai_insights.get("trend_vs_last_week", "")
    if trend:
        html += f'<h3 style="margin:15px 0 8px;">📈 趋势对比</h3><p style="font-size:14px;background:#f0f9ff;padding:10px;border-radius:6px;">{trend}</p>'

    # 下周关注
    focus = ai_insights.get("next_week_focus", [])
    if focus:
        html += '<h3 style="margin:15px 0 8px;">👁️ 下周重点关注</h3><ul style="font-size:14px;">'
        for f_item in focus[:5]:
            html += f'<li>{f_item}</li>'
        html += '</ul>'

    # 亮点
    highlights = ai_insights.get("positive_highlights", [])
    if highlights:
        html += '<h3 style="margin:15px 0 8px;">✨ 本周亮点</h3><ul style="font-size:14px;color:#28a745;">'
        for h in highlights[:3]:
            html += f'<li>{h}</li>'
        html += '</ul>'

    return html


def send_email(to, subject, html_body, dry_run=False):
    """发送邮件。"""
    if dry_run:
        output_path = f"/tmp/ceo_briefing_{datetime.now().strftime('%Y%m%d')}.html"
        Path(output_path).write_text(html_body, encoding="utf-8")
        print(f"  📄 [DRY RUN] 简报已保存到 {output_path}", file=sys.stderr)
        return output_path

    cmd = [
        sys.executable, SEND_EMAIL_SCRIPT,
        "--to", to,
        "--subject", subject,
        "--body", html_body,
        "--html",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode == 0:
        print(f"  ✅ 邮件已发送至 {to}", file=sys.stderr)
        return True
    else:
        print(f"  ❌ 邮件发送失败: {result.stderr}", file=sys.stderr)
        return False


def sync_openclaw():
    """同步知识到 OpenClaw。"""
    cmd = [sys.executable, str(SCRIPTS_DIR / "sync_to_openclaw.py")]
    run_step("同步知识到 OpenClaw", cmd, timeout=15)


def main():
    parser = argparse.ArgumentParser(description="CEO 周报智能简报")
    parser.add_argument("--week", choices=["this", "last"], default="this")
    parser.add_argument("--to", default=CEO_EMAIL, help="收件人邮箱")
    parser.add_argument("--dry-run", action="store_true", help="只生成不发送")
    parser.add_argument("--since", help="起始日期")
    parser.add_argument("--until", help="截止日期")
    args = parser.parse_args()

    print(f"\n{'='*50}", file=sys.stderr)
    print(f"  🤖 CEO 周报智能简报生成器", file=sys.stderr)
    print(f"  📧 收件人: {args.to}", file=sys.stderr)
    print(f"{'='*50}\n", file=sys.stderr)

    # Step 1: 拉取周报
    print("📥 Step 1/5: 拉取周报", file=sys.stderr)
    if args.since and args.until:
        cmd = [
            sys.executable, str(CLAUDE_SCRIPTS_DIR / "fetch_weekly_reports.py"),
            "--since", args.since, "--until", args.until,
            "-o", "/tmp/weekly_reports.json",
        ]
        run_step("拉取指定范围周报", cmd, timeout=120)
    else:
        data = fetch_reports(args.week)

    if not Path("/tmp/weekly_reports.json").exists():
        print("❌ 无法拉取周报，退出", file=sys.stderr)
        sys.exit(1)

    with open("/tmp/weekly_reports.json", encoding="utf-8") as f:
        data = json.load(f)

    if data["count"] == 0:
        print("⚠️ 本周无周报，退出", file=sys.stderr)
        sys.exit(0)

    # Step 2: 构建知识
    print("\n🧠 Step 2/5: 构建公司知识", file=sys.stderr)
    knowledge_stats = build_knowledge()

    # Step 3: AI 智能分析
    print("\n🤖 Step 3/7: AI 智能分析", file=sys.stderr)
    ai_analysis = {}
    ai_insights_data = {}
    try:
        ai_cmd = [sys.executable, str(SCRIPTS_DIR / "ai_analyze.py"),
                  "/tmp/weekly_reports.json", "-o", "/tmp/ai_analysis.json"]
        run_step("AI 风险分析 + CEO 洞察", ai_cmd, timeout=180)
        if Path("/tmp/ai_analysis.json").exists():
            with open("/tmp/ai_analysis.json", encoding="utf-8") as f:
                ai_result = json.load(f)
            ai_analysis = ai_result.get("risk_analysis", {})
            ai_insights_data = ai_result.get("insights", {})
    except Exception as e:
        print(f"  ⚠️ AI 分析跳过: {e}", file=sys.stderr)

    # Step 4: 分析风险变化
    print("\n📊 Step 4/7: 风险变化追踪", file=sys.stderr)
    prev_risks = load_previous_risks()
    risk_week = knowledge_stats.get("week", "")
    risk_path = MEMORY_DIR / "risks" / f"{risk_week}.md" if risk_week else None
    risk_changes = analyze_risk_changes(risk_path, prev_risks)
    print(f"  ✅ 新增 {len(risk_changes['new'])} / 持续 {len(risk_changes['ongoing'])} / 解决 {len(risk_changes['resolved'])}", file=sys.stderr)

    # Step 5: 生成简报
    print("\n📝 Step 5/7: 生成 CEO 简报", file=sys.stderr)
    classified = classify_reports(data)
    key_items = extract_key_items(data)
    stats = submission_stats(data)
    html = generate_html_briefing(data, knowledge_stats, risk_changes, classified, key_items, stats)

    # 注入 AI 分析段落
    ai_section = build_ai_section(ai_analysis, ai_insights_data)
    if ai_section:
        html = html.replace("</div>\n\n<div style=\"text-align:center", f"{ai_section}</div>\n\n<div style=\"text-align:center")
    print(f"  ✅ 简报生成完成（{len(html)} 字符）", file=sys.stderr)

    # Step 6: 实时预警检查
    print("\n🚨 Step 6/7: 实时预警检查", file=sys.stderr)
    if ai_analysis.get("high_risks") or ai_analysis.get("systemic_risks"):
        try:
            alert_cmd = [sys.executable, str(SCRIPTS_DIR / "realtime_alert.py"), "/tmp/ai_analysis.json"]
            run_step("发送风险预警", alert_cmd, timeout=60)
        except Exception:
            pass
    else:
        print("  ✅ 无高风险，跳过预警", file=sys.stderr)

    # Step 7: 发送 & 同步
    print("\n📤 Step 7/7: 发送邮件 & 同步 OpenClaw", file=sys.stderr)
    period = data.get("period", "")
    high_count = len(ai_analysis.get("high_risks", []))
    subject = f"📊 CEO 周报简报（{period}）— {'🔴 ' + str(high_count) + '项高风险 / ' if high_count else ''}{stats['unique_submitters']} 人提交"
    send_email(args.to, subject, html, dry_run=args.dry_run)

    # 保存一份到 digests
    digest_path = MEMORY_DIR / "digests" / f"{knowledge_stats.get('week', 'latest')}.html"
    digest_path.write_text(html, encoding="utf-8")

    # 保存 AI 分析到 digests 目录
    if ai_insights_data:
        ai_digest = MEMORY_DIR / "digests" / f"{knowledge_stats.get('week', 'latest')}_ai.json"
        with open(ai_digest, "w", encoding="utf-8") as f:
            json.dump({"risk_analysis": ai_analysis, "insights": ai_insights_data}, f, ensure_ascii=False, indent=2)

    sync_openclaw()

    print(f"\n{'='*50}", file=sys.stderr)
    print(f"  ✅ 全部完成！", file=sys.stderr)
    print(f"{'='*50}", file=sys.stderr)


if __name__ == "__main__":
    main()
