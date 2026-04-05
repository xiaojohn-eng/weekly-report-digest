#!/usr/bin/env python3
"""
从周报 JSON 中提取结构化知识，更新公司知识记忆库。
每次运行后生成/更新：
  - people/{email}.md      员工档案
  - projects/{code}.md     项目档案
  - risks/{week}.md        风险登记
  - digests/{week}.md      周报摘要存档
  - company_snapshot.md    全景快照（供 OpenClaw 加载）

用法:
  python3 build_knowledge.py /tmp/weekly_reports.json
  python3 build_knowledge.py /tmp/weekly_reports.json --week 2026-W14
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

MEMORY_DIR = Path(os.environ.get("WEEKLY_MEMORY_DIR", "/root/.openclaw/memory-weekly"))
SNAPSHOT_PATH = MEMORY_DIR / "company_snapshot.md"

# 部门分类规则
DEPT_RULES = {
    "软件研发": ["开发", "V2", "V3", "前端", "后端", "PDA", "系统", "代码", "Bug", "工作站", "黑盒", "白盒"],
    "算法组": ["算法", "视觉", "模型", "训练", "机械臂", "MinIO", "3D", "相机", "SCARA"],
    "项目现场": ["安装", "调试", "现场", "施工", "发货", "里程碑", "上电"],
    "项目管理": ["体系", "SOP", "验收报告", "项目监管", "PM", "项��经理"],
    "商务/销售": ["招标", "报价", "客户", "商务", "回款", "中标", "代理"],
    "HR/行政": ["招聘", "薪资", "考勤", "入职", "晋级", "人力"],
    "IT/基础设施": ["部署", "VPN", "环境", "远程", "服��器", "Claude", "OpenClaw"],
    "运输物流": ["发货", "包装", "物流", "运输", "BOM"],
}

# 项目编号提取
PROJECT_CODE_RE = re.compile(r"(TG\d{3})")
# 项目名称提取（从主题）
PROJECT_NAME_PATTERNS = [
    re.compile(r"【(TG\d{3}[^】]*)】(.+?)(?:周报|项目)", re.DOTALL),
    re.compile(r"(顺丰|PDD|菜鸟|虾皮|希音|Ozon|屈臣氏|美国|日本|武汉|郑州|成都|佛山|东莞|清远|深圳|太原|北京|肇庆)[^\s]*项目"),
]

# 风险关键词
def normalize_project_code(code):
    """Normalize project codes: TG058-佛山拼多多 → TG058"""
    match = re.match(r'(TG\d{3})', code)
    if match:
        return match.group(1)
    return code


RISK_KEYWORDS = {
    "high": ["掉车", "损坏", "事故", "安全事故", "严重", "源代码", "泄漏"],
    "medium": ["延期", "推迟", "滞后", "异常", "故障", "识别率低", "成本增加", "交期", "缺少物料", "不足"],
    "low": ["待确认", "待客���", "待商务", "排期", "跟进"],
}


def classify_department(body, subject):
    """根据内容和���题分类部门。"""
    text = subject + " " + body
    scores = {}
    for dept, keywords in DEPT_RULES.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            scores[dept] = score
    # 项目编号出现在主题中 → 项目现场
    if PROJECT_CODE_RE.search(subject):
        scores["项目现场"] = scores.get("项目现场", 0) + 5
    if not scores:
        return "其他"
    return max(scores, key=scores.get)


def extract_risks(body):
    """从正文中提取风险。"""
    risks = []
    # 查找风险段落
    risk_section = re.search(
        r"(?:问题|风险|问题.*风险|风险.*问题)[：:&]?\s*([\s\S]*?)(?:(?:二|本周|主要工作|工作进展)|$)",
        body, re.IGNORECASE
    )
    if risk_section:
        risk_text = risk_section.group(1).strip()
        if risk_text and not re.match(r"^(暂无|无|本周无)", risk_text):
            # 判断严重程度
            level = "low"
            for lv in ["high", "medium"]:
                if any(kw in risk_text for kw in RISK_KEYWORDS[lv]):
                    level = lv
                    break
            risks.append({"level": level, "text": risk_text[:500]})
    return risks


def extract_projects(body, subject):
    """从周报中提取涉及的项目。"""
    projects = set()
    codes = PROJECT_CODE_RE.findall(subject + " " + body)
    projects.update(codes)
    # 提取客户项目名
    for pattern in PROJECT_NAME_PATTERNS:
        matches = pattern.findall(subject + " " + body)
        for m in matches:
            if isinstance(m, tuple):
                projects.add("".join(m).strip())
            else:
                projects.add(m.strip())
    return list(projects)


def update_person_file(person_dir, report):
    """更新员工档案。"""
    email = report["sender_email"]
    safe_name = email.replace("@", "_at_").replace(".", "_")
    filepath = person_dir / f"{safe_name}.md"

    name = report["sender_name"]
    dept = classify_department(report["body"], report["subject"])
    projects = extract_projects(report["body"], report["subject"])
    date = report["date"]

    if filepath.exists():
        content = filepath.read_text(encoding="utf-8")
        # 更新最后活跃时间
        content = re.sub(r"最后周报：.*", f"最后周报：{date}", content)
        # 追加项目（去重）
        existing_projects = re.findall(r"- (.+)", content.split("## 涉及项目")[-1]) if "## 涉及项目" in content else []
        new_projects = [p for p in projects if p not in existing_projects]
        if new_projects:
            content = content.rstrip() + "\n" + "\n".join(f"- {p}" for p in new_projects) + "\n"
        filepath.write_text(content, encoding="utf-8")
    else:
        content = f"""# {name}

- 邮箱：{email}
- 部门：{dept}
- 最后周报：{date}

## 涉及项目
{chr(10).join(f'- {p}' for p in projects) if projects else '- （暂无）'}

## 工作记录摘要
- [{date}] {report['subject'][:60]}
"""
        filepath.write_text(content, encoding="utf-8")

    return {"name": name, "email": email, "dept": dept, "projects": projects}


def update_project_file(project_dir, code, info):
    """更新项目档案。"""
    safe_code = re.sub(r"[^\w\-]", "_", code)
    filepath = project_dir / f"{safe_code}.md"

    if not filepath.exists():
        content = f"""# {code}

- 状态：进行中
- 首次出现：{info.get('date', '未知')}
- 最后更新：{info.get('date', '未知')}
- 相关人员：{', '.join(info.get('people', []))}

## 周报提及记录
- [{info.get('date', '')}] {info.get('summary', '')}
"""
        filepath.write_text(content, encoding="utf-8")
    else:
        content = filepath.read_text(encoding="utf-8")
        content = re.sub(r"最后更新：.*", f"最后更新：{info.get('date', '未知')}", content)
        # 追加人员
        for person in info.get("people", []):
            if person not in content:
                content = content.replace("- 相关人员：", f"- 相关人员：{person}, ", 1)
        # 追加周报记录
        new_entry = f"- [{info.get('date', '')}] {info.get('summary', '')}\n"
        if new_entry.strip() not in content:
            content = content.rstrip() + "\n" + new_entry
        filepath.write_text(content, encoding="utf-8")


def save_risk_registry(risks_dir, week_label, all_risks):
    """保存本周风险登记簿。"""
    filepath = risks_dir / f"{week_label}.md"
    lines = [f"# 风险登记簿 {week_label}\n"]
    level_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}

    for level in ["high", "medium", "low"]:
        items = [r for r in all_risks if r["level"] == level]
        if items:
            lines.append(f"\n## {level_emoji[level]} {'高' if level == 'high' else '中' if level == 'medium' else '低'}风险\n")
            for r in items:
                lines.append(f"**{r['reporter']}** ({r['project']})")
                lines.append(f"> {r['text'][:300]}\n")

    filepath.write_text("\n".join(lines), encoding="utf-8")
    return filepath


def build_company_snapshot(memory_dir):
    """合成公司全景快照 — 这是 OpenClaw 加载的核心上下文。"""
    people_dir = memory_dir / "people"
    projects_dir = memory_dir / "projects"
    risks_dir = memory_dir / "risks"
    digests_dir = memory_dir / "digests"

    # 统计员工
    people = {}
    dept_members = {}
    for f in sorted(people_dir.glob("*.md")):
        content = f.read_text(encoding="utf-8")
        name_match = re.search(r"^# (.+)", content)
        dept_match = re.search(r"部门：(.+)", content)
        email_match = re.search(r"邮箱：(.+)", content)
        if name_match:
            name = name_match.group(1).strip()
            dept = dept_match.group(1).strip() if dept_match else "未知"
            email_addr = email_match.group(1).strip() if email_match else ""
            people[name] = {"dept": dept, "email": email_addr}
            dept_members.setdefault(dept, []).append(name)

    # 统计项目
    project_list = []
    for f in sorted(projects_dir.glob("*.md")):
        content = f.read_text(encoding="utf-8")
        title_match = re.search(r"^# (.+)", content)
        status_match = re.search(r"状态：(.+)", content)
        if title_match:
            project_list.append({
                "name": title_match.group(1).strip(),
                "status": status_match.group(1).strip() if status_match else "未知",
            })

    # 最近风险
    risk_files = sorted(risks_dir.glob("*.md"), reverse=True)
    latest_risks = ""
    if risk_files:
        latest_risks = risk_files[0].read_text(encoding="utf-8")

    # 最近摘要
    digest_files = sorted(digests_dir.glob("*.md"), reverse=True)
    latest_digest_summary = ""
    if digest_files:
        content = digest_files[0].read_text(encoding="utf-8")
        # 取前2000字
        latest_digest_summary = content[:2000]

    snapshot = f"""# 天下先智创机器人 — 公司知识快照

> 自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')}，由 weekly-report-digest 技能维护
> 数据来源：员工周报邮件

---

## 公司简介

天下先智创机器人（TG Robot��是一家物流分拣机器人公司，主要产品包括：
- **木马分拣机**：核心产品，小车式自动分拣系统，配备视觉识别、OCR扫码
- **工作站系统**：人工/自动混合分拣工作站
- **3D 演示系统**：用于展会和客户演示
- **PDA 系统**：手持终端配套软件

主要客户：顺丰、拼多多(PDD)、菜鸟、虾皮(Shopee)、希音(SHEIN)、屈臣氏、Ozon
业务区域：中国（北京、佛山、东莞、清远、郑州、成都、深圳、太原、武汉、九江）、新加坡、日本、美国、俄罗斯

## 组织架构

共 {len(people)} 名周报活跃员工，分布如下：

{chr(10).join(f'### {dept}（{len(members)}人）' + chr(10) + chr(10).join(f'- {m}' for m in members) for dept, members in sorted(dept_members.items()))}

## 项目全景（{len(project_list)} 个）

| 项目 | 状态 |
|------|------|
{chr(10).join(f'| {p["name"]} | {p["status"]} |' for p in project_list)}

## 最近风险

{latest_risks[:1500] if latest_risks else '暂无风险记录'}

## 最近周报摘要

{latest_digest_summary if latest_digest_summary else '暂无摘要'}

---

*本文件由 weekly-report-digest 技能自动更新，作为 OpenClaw 的公司知识上下文。*
"""
    SNAPSHOT_PATH.write_text(snapshot, encoding="utf-8")
    return SNAPSHOT_PATH


def process_reports(json_path, week_label=None):
    """主处理流程。"""
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    period = data["period"]
    reports = data["reports"]

    if not week_label:
        # 从 period 推算周标签
        try:
            start_date = datetime.strptime(period.split(" ~ ")[0], "%Y-%m-%d")
            week_label = f"{start_date.isocalendar()[0]}-W{start_date.isocalendar()[1]:02d}"
        except Exception:
            week_label = datetime.now().strftime("%Y-W%W")

    print(f"处理周报: {period} ({week_label})", file=sys.stderr)
    print(f"共 {len(reports)} 封", file=sys.stderr)

    people_dir = MEMORY_DIR / "people"
    projects_dir = MEMORY_DIR / "projects"
    risks_dir = MEMORY_DIR / "risks"
    digests_dir = MEMORY_DIR / "digests"

    all_people = []
    all_risks = []
    all_project_codes = {}

    for report in reports:
        # 1. 更新员工档案
        person_info = update_person_file(people_dir, report)
        all_people.append(person_info)

        # 2. 提取风险
        risks = extract_risks(report["body"])
        for r in risks:
            r["reporter"] = report["sender_name"]
            r["project"] = report["subject"][:40]
        all_risks.extend(risks)

        # 3. 提取项目
        projects = extract_projects(report["body"], report["subject"])
        for code in projects:
            if code not in all_project_codes:
                all_project_codes[code] = {
                    "date": report["date"],
                    "people": [],
                    "summary": report["subject"][:60],
                }
            all_project_codes[code]["people"].append(report["sender_name"])

    # 3.5 Dedup projects by base code
    deduped = {}
    for code, info in all_project_codes.items():
        base = normalize_project_code(code)
        if base not in deduped:
            deduped[base] = info
            deduped[base]["aliases"] = [code]
        else:
            deduped[base]["people"].extend(info.get("people", []))
            deduped[base]["aliases"].append(code)
            # Keep longer name as summary
            if len(info.get("summary", "")) > len(deduped[base].get("summary", "")):
                deduped[base]["summary"] = info["summary"]
    all_project_codes = deduped

    # 4. 更新项目档案
    for code, info in all_project_codes.items():
        update_project_file(projects_dir, code, info)

    # 5. 保存风险登记
    if all_risks:
        save_risk_registry(risks_dir, week_label, all_risks)

    # 6. 保存摘要存档占位（实际摘要由 AI 生成后写入���
    digest_path = digests_dir / f"{week_label}.md"
    if not digest_path.exists():
        digest_path.write_text(
            f"# 周报摘要 {week_label}\n\n> 周期: {period}\n> 周报数: {len(reports)}\n\n（待 AI 生成完整摘要后更新）\n",
            encoding="utf-8",
        )

    # 7. 合成公司快照
    snapshot_path = build_company_snapshot(MEMORY_DIR)

    # 输出统计
    stats = {
        "week": week_label,
        "period": period,
        "report_count": len(reports),
        "people_updated": len(all_people),
        "projects_found": len(all_project_codes),
        "risks_found": len(all_risks),
        "risk_high": sum(1 for r in all_risks if r["level"] == "high"),
        "risk_medium": sum(1 for r in all_risks if r["level"] == "medium"),
        "risk_low": sum(1 for r in all_risks if r["level"] == "low"),
        "snapshot_path": str(snapshot_path),
        "digest_path": str(digest_path),
    }
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return stats


def main():
    parser = argparse.ArgumentParser(description="从周报构建公司知识记忆")
    parser.add_argument("json_path", help="周报 JSON 文件路径")
    parser.add_argument("--week", help="周标签，如 2026-W14")
    args = parser.parse_args()
    process_reports(args.json_path, args.week)


if __name__ == "__main__":
    main()
