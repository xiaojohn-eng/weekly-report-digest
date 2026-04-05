#!/usr/bin/env python3
"""
实时预警 — 检测高风险关键词，立即通过企微 + 邮件通知 CEO

可由 ceo_briefing.py 调用，也可独立运行扫描最新周报。

用法：
  python3 realtime_alert.py /tmp/ai_analysis.json
  python3 realtime_alert.py --scan  # 扫描最新周报并分析
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

CEO_EMAIL = "shaw@tgkwrobot.com"
SEND_SCRIPT = "/root/.claude/send_email.py"
BRAND_COLOR = "#e05a2b"


def send_wecom_alert(message):
    """通过 OpenClaw 企微通道推送给 CEO。"""
    try:
        result = subprocess.run(
            ["openclaw", "agent", "--agent", "main",
             "--session-id", "agent:main:wecom:direct:xiaojun",
             "-m", message],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            print(f"  ✅ 企微推送成功", file=sys.stderr)
            return True
    except Exception as e:
        print(f"  ⚠️ 企微推送失败: {e}", file=sys.stderr)
    return False


def send_email_alert(subject, html_body):
    """邮件预警。"""
    try:
        result = subprocess.run(
            [sys.executable, SEND_SCRIPT,
             "--to", CEO_EMAIL,
             "--subject", subject,
             "--body", html_body,
             "--html"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            print(f"  ✅ 邮件预警已发送", file=sys.stderr)
            return True
    except Exception as e:
        print(f"  ⚠️ 邮件发送失败: {e}", file=sys.stderr)
    return False


def check_and_alert(analysis):
    """检查分析结果，触发预警。"""
    risk_data = analysis.get("risk_analysis", {})
    high_risks = risk_data.get("high_risks", [])
    systemic_risks = risk_data.get("systemic_risks", [])

    if not high_risks and not systemic_risks:
        print("✅ 无高风险或系统性风险，无需预警", file=sys.stderr)
        return

    now = datetime.now().strftime("%m-%d %H:%M")

    # 1. 企微消息（简短）
    wecom_msg = f"🚨 周报风险预警（{now}）\n\n"
    if high_risks:
        wecom_msg += f"🔴 高风险 {len(high_risks)} 项：\n"
        for r in high_risks[:5]:
            if isinstance(r, dict):
                wecom_msg += f"• {r.get('reporter','')}: {r.get('description','')[:80]}\n"
        wecom_msg += "\n"
    if systemic_risks:
        wecom_msg += f"⚠️ 系统性风险 {len(systemic_risks)} 项：\n"
        for r in systemic_risks[:3]:
            if isinstance(r, dict):
                wecom_msg += f"• {r.get('description','')[:80]}\n"
    wecom_msg += "\n详情已发送至邮箱。"

    send_wecom_alert(wecom_msg)

    # 2. 邮件（详细 HTML）
    risk_rows = ""
    for r in high_risks:
        if isinstance(r, dict):
            risk_rows += f"""<tr style="border-bottom:1px solid #eee;">
                <td style="padding:8px;font-weight:bold;">{r.get('reporter','')}</td>
                <td style="padding:8px;">{r.get('project','')}</td>
                <td style="padding:8px;">{r.get('description','')}</td>
                <td style="padding:8px;color:#e05a2b;">{r.get('suggestion','')}</td>
            </tr>"""

    systemic_rows = ""
    for r in systemic_risks:
        if isinstance(r, dict):
            people = ", ".join(r.get("involved_people", []))
            systemic_rows += f"""<tr style="border-bottom:1px solid #eee;">
                <td style="padding:8px;">{r.get('description','')}</td>
                <td style="padding:8px;">{people}</td>
                <td style="padding:8px;">{r.get('pattern','')}</td>
            </tr>"""

    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,sans-serif;max-width:650px;margin:0 auto;padding:20px;">
<div style="background:#dc3545;color:#fff;padding:15px;border-radius:8px;text-align:center;">
    <h2 style="margin:0;color:#fff;">🚨 周报风险预警</h2>
    <p style="margin:5px 0 0;color:#fff;opacity:0.9;">{now}</p>
</div>

<h3 style="color:#dc3545;margin-top:20px;">🔴 高风险（{len(high_risks)} 项）</h3>
<table style="width:100%;border-collapse:collapse;font-size:14px;">
<tr style="background:#dc3545;color:#fff;">
    <th style="padding:8px;text-align:left;color:#fff !important;">报告人</th>
    <th style="padding:8px;text-align:left;color:#fff !important;">项目</th>
    <th style="padding:8px;text-align:left;color:#fff !important;">风险</th>
    <th style="padding:8px;text-align:left;color:#fff !important;">建议</th>
</tr>
{risk_rows}
</table>

{"<h3 style='color:#ff8c00;margin-top:20px;'>⚠️ 系统性风险（" + str(len(systemic_risks)) + " 项）</h3>" if systemic_risks else ""}
{"<table style='width:100%;border-collapse:collapse;font-size:14px;'><tr style='background:#ff8c00;color:#fff;'><th style='padding:8px;text-align:left;color:#fff !important;'>描述</th><th style='padding:8px;text-align:left;color:#fff !important;'>涉及人员</th><th style='padding:8px;text-align:left;color:#fff !important;'>模式</th></tr>" + systemic_rows + "</table>" if systemic_risks else ""}

<div style="margin-top:20px;padding:10px;background:#f8f9fa;border-radius:8px;font-size:12px;color:#666;">
    ⚡ OpenClaw AI 自动检测 · 天下先智创机器人
</div>
</body></html>"""

    subject = f"🚨 周报风险预警 — {len(high_risks)} 项高风险 / {len(systemic_risks)} 项系统性风险"
    send_email_alert(subject, html)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("json_path", nargs="?", help="AI 分析结果 JSON")
    parser.add_argument("--scan", action="store_true", help="扫描最新周报")
    args = parser.parse_args()

    if args.scan:
        # 拉取 + 分析 + 检查
        scripts = Path(__file__).parent
        subprocess.run([sys.executable, str(Path("/root/.claude/skills/weekly-report-digest/scripts/fetch_weekly_reports.py")),
                       "--week", "this", "-o", "/tmp/weekly_reports.json"],
                      capture_output=True, timeout=120)
        subprocess.run([sys.executable, str(scripts / "ai_analyze.py"),
                       "/tmp/weekly_reports.json", "-o", "/tmp/ai_analysis.json"],
                      capture_output=True, timeout=180)
        args.json_path = "/tmp/ai_analysis.json"

    if not args.json_path or not Path(args.json_path).exists():
        print("❌ 无分析结果", file=sys.stderr)
        return

    with open(args.json_path, encoding="utf-8") as f:
        analysis = json.load(f)

    check_and_alert(analysis)


if __name__ == "__main__":
    main()
