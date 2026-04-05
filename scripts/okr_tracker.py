#!/usr/bin/env python3
"""
OKR/KPI 自动追踪 — 从周报中匹配 OKR 关键结果的进展

用法：
  python3 okr_tracker.py                           # 用现有OKR追踪本周周报
  python3 okr_tracker.py --init                     # 交互式录入OKR
  python3 okr_tracker.py --report                   # 生成OKR进度报告
  python3 okr_tracker.py --add "O:目标" "KR:关键结果" "owner:负责人"
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    import httpx
except ImportError:
    os.system(f"{sys.executable} -m pip install -q httpx")
    import httpx

MEMORY_DIR = Path("/root/.openclaw/memory-weekly")
OKR_FILE = MEMORY_DIR / "org" / "okr.json"
OKR_PROGRESS_DIR = MEMORY_DIR / "okr_progress"

API_BASE = os.environ.get("MINIMAX_API_BASE", "https://api.minimaxi.com/v1")
API_KEY = os.environ.get("MINIMAX_API_KEY", "")


def call_llm(system, user_msg, max_tokens=3000):
    url = f"{API_BASE.rstrip('/').replace('/v1','')}/anthropic/v1/messages"
    headers = {
        "Content-Type": "application/json",
        "x-api-key": API_KEY,
        "anthropic-version": "2023-06-01",
    }
    payload = {
        "model": "MiniMax-M2.5",
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user_msg}],
    }
    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=90)
        resp.raise_for_status()
        for block in resp.json().get("content", []):
            if block.get("type") == "text":
                return block["text"]
    except Exception as e:
        return f"error: {e}"
    return ""


def load_okrs():
    if OKR_FILE.exists():
        return json.loads(OKR_FILE.read_text(encoding="utf-8"))
    return {"objectives": [], "updated_at": None}


def save_okrs(data):
    OKR_FILE.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.now().isoformat()
    OKR_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def add_okr(objective, key_result, owner, quarter=None):
    data = load_okrs()
    if not quarter:
        month = datetime.now().month
        quarter = f"Q{(month - 1) // 3 + 1} {datetime.now().year}"

    # 查找已有 objective
    obj = None
    for o in data["objectives"]:
        if o["objective"] == objective:
            obj = o
            break

    if not obj:
        obj = {"objective": objective, "quarter": quarter, "key_results": []}
        data["objectives"].append(obj)

    obj["key_results"].append({
        "kr": key_result,
        "owner": owner,
        "target": "",
        "current": "",
        "progress": 0,
        "status": "on_track",
        "history": [],
    })

    save_okrs(data)
    print(f"✅ 已添加: {objective} → {key_result} ({owner})")


def track_from_weekly_reports(reports_path):
    """从周报中追踪 OKR 进展。"""
    data = load_okrs()
    if not data["objectives"]:
        print("⚠️ 未设置 OKR，请先用 --add 或 --init 添加", file=sys.stderr)
        return None

    with open(reports_path, encoding="utf-8") as f:
        reports = json.load(f)

    # 构建周报摘要
    condensed = []
    for r in reports.get("reports", []):
        condensed.append(f"【{r['sender_name']}】{r['body'][:600]}")
    report_text = "\n---\n".join(condensed)

    okr_text = json.dumps(data["objectives"], ensure_ascii=False)

    system = """你是 OKR 追踪专家。对比公司 OKR 和员工周报，评估每个关键结果的进展。

输出 JSON：
{
  "tracking": [
    {
      "objective": "目标",
      "kr": "关键结果",
      "owner": "负责人",
      "progress_pct": 60,
      "evidence": "从周报中找到的进展证据",
      "status": "on_track|at_risk|behind|completed",
      "delta": "+10%",
      "note": "一句话说明"
    }
  ],
  "untracked_okrs": ["没在周报中找到进展的KR"],
  "overall_health": "整体OKR健康度评估"
}

规则：
- progress_pct 基于周报中的实际证据估算
- evidence 必须引用具体周报内容
- 找不到相关信息的标为 untracked
- status: completed(≥100%), on_track(按计划), at_risk(可能延期), behind(落后)"""

    user = f"""公司 OKR：
{okr_text}

---
本周员工周报：
{report_text[:10000]}

请追踪每个 KR 的进展。"""

    result = call_llm(system, user)
    try:
        json_match = re.search(r'\{[\s\S]*\}', result)
        if json_match:
            tracking = json.loads(json_match.group())

            # 更新 OKR 进度
            for t in tracking.get("tracking", []):
                for obj in data["objectives"]:
                    for kr in obj["key_results"]:
                        if kr["kr"] == t.get("kr") or kr["owner"] == t.get("owner"):
                            kr["progress"] = t.get("progress_pct", kr["progress"])
                            kr["status"] = t.get("status", kr["status"])
                            kr["current"] = t.get("evidence", "")[:200]
                            kr["history"].append({
                                "date": datetime.now().strftime("%Y-%m-%d"),
                                "progress": t.get("progress_pct", 0),
                                "note": t.get("note", ""),
                            })
                            break

            save_okrs(data)

            # 保存周度追踪
            OKR_PROGRESS_DIR.mkdir(exist_ok=True)
            week = datetime.now().strftime("%Y-W%W")
            progress_file = OKR_PROGRESS_DIR / f"{week}.json"
            progress_file.write_text(json.dumps(tracking, ensure_ascii=False, indent=2), encoding="utf-8")

            return tracking
    except json.JSONDecodeError:
        pass
    return {"raw": result}


def generate_report():
    """生成 OKR 进度报告（Markdown）。"""
    data = load_okrs()
    if not data["objectives"]:
        return "未设置 OKR"

    lines = [f"# OKR 进度报告\n> 更新于 {datetime.now().strftime('%Y-%m-%d')}\n"]

    for obj in data["objectives"]:
        lines.append(f"\n## 🎯 {obj['objective']}（{obj.get('quarter', '')}）\n")
        lines.append("| KR | 负责人 | 进度 | 状态 | 最新证据 |")
        lines.append("|-----|-------|------|------|---------|")

        for kr in obj["key_results"]:
            status_emoji = {"on_track": "🟢", "at_risk": "🟡", "behind": "🔴", "completed": "✅"}.get(kr["status"], "⚪")
            progress = kr.get("progress", 0)
            bar = "█" * (progress // 10) + "░" * (10 - progress // 10)
            lines.append(f"| {kr['kr'][:40]} | {kr['owner']} | {bar} {progress}% | {status_emoji} | {kr.get('current', '')[:50]} |")

    report = "\n".join(lines)

    # 保存
    report_path = MEMORY_DIR / "org" / "okr_report.md"
    report_path.write_text(report, encoding="utf-8")
    print(report)
    return report


def init_default_okrs():
    """基于公司情况初始化默认 OKR。"""
    default_okrs = {
        "objectives": [
            {
                "objective": "提升项目交付质量与效率",
                "quarter": "Q2 2026",
                "key_results": [
                    {"kr": "在建项目按期交付率≥90%", "owner": "曲锐", "target": "90%", "current": "", "progress": 0, "status": "on_track", "history": []},
                    {"kr": "项目现场问题48h内响应率≥95%", "owner": "郭立娜", "target": "95%", "current": "", "progress": 0, "status": "on_track", "history": []},
                    {"kr": "客户终验一次通过率≥80%", "owner": "曲锐", "target": "80%", "current": "", "progress": 0, "status": "on_track", "history": []},
                ],
            },
            {
                "objective": "完成V3软件系统架构升级",
                "quarter": "Q2 2026",
                "key_results": [
                    {"kr": "V3黑盒系统核心模块完成度≥60%", "owner": "刘晓键", "target": "60%", "current": "", "progress": 0, "status": "on_track", "history": []},
                    {"kr": "V3白盒工作站标准版上线", "owner": "殷伟伟", "target": "上线", "current": "", "progress": 0, "status": "on_track", "history": []},
                    {"kr": "V3 PDA系统完成核心页面开发", "owner": "赵亮", "target": "完成", "current": "", "progress": 0, "status": "on_track", "history": []},
                ],
            },
            {
                "objective": "海外业务稳步推进",
                "quarter": "Q2 2026",
                "key_results": [
                    {"kr": "菜鸟新加坡项目通过终验", "owner": "Rodgers", "target": "终验通过", "current": "", "progress": 0, "status": "at_risk", "history": []},
                    {"kr": "美国3城环境配置完成并开始联调", "owner": "刘晓键", "target": "联调开始", "current": "", "progress": 0, "status": "on_track", "history": []},
                    {"kr": "W项目中标并签约", "owner": "朱光楣", "target": "签约", "current": "", "progress": 0, "status": "on_track", "history": []},
                ],
            },
            {
                "objective": "团队能力建设",
                "quarter": "Q2 2026",
                "key_results": [
                    {"kr": "完成PM招聘≥3人到岗", "owner": "李梦", "target": "3人", "current": "", "progress": 0, "status": "on_track", "history": []},
                    {"kr": "AI辅助开发覆盖率≥50%研发人员", "owner": "刘旭", "target": "50%", "current": "", "progress": 0, "status": "on_track", "history": []},
                    {"kr": "项目管理体系文件全部发布", "owner": "曲锐", "target": "全部发布", "current": "", "progress": 0, "status": "on_track", "history": []},
                ],
            },
        ],
        "updated_at": datetime.now().isoformat(),
    }
    save_okrs(default_okrs)
    print(f"✅ 已初始化 {len(default_okrs['objectives'])} 个目标，{sum(len(o['key_results']) for o in default_okrs['objectives'])} 个关键结果")
    return default_okrs


def main():
    parser = argparse.ArgumentParser(description="OKR 自动追踪")
    parser.add_argument("--init", action="store_true", help="初始化默认 OKR")
    parser.add_argument("--add", nargs=3, metavar=("O", "KR", "OWNER"), help="添加 OKR")
    parser.add_argument("--track", help="从周报 JSON 追踪进展")
    parser.add_argument("--report", action="store_true", help="生成进度报告")
    args = parser.parse_args()

    if args.init:
        init_default_okrs()
    elif args.add:
        add_okr(args.add[0], args.add[1], args.add[2])
    elif args.track:
        result = track_from_weekly_reports(args.track)
        if result:
            print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.report:
        generate_report()
    else:
        # 默认：追踪最新周报
        if Path("/tmp/weekly_reports.json").exists():
            track_from_weekly_reports("/tmp/weekly_reports.json")
            generate_report()
        else:
            parser.print_help()


if __name__ == "__main__":
    main()
