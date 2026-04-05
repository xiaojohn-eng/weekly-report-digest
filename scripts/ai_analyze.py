#!/usr/bin/env python3
"""
AI 分析引擎 — 用 LLM 对周报做深度智能分析

功能：
1. 风险智能提取与分级（替代正则）
2. 交叉分析（多人提同一问题 = 系统性风险）
3. 项目进度趋势判断
4. 生成 CEO 级别的洞察与建议
5. 周度趋势对比

调用方式：
  python3 ai_analyze.py /tmp/weekly_reports.json
  python3 ai_analyze.py /tmp/weekly_reports.json --output /tmp/ai_analysis.json
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

# MiniMax API (Anthropic Messages 兼容格式)
API_BASE = os.environ.get("MINIMAX_API_BASE", "https://api.minimaxi.com/v1")
API_KEY = os.environ.get("MINIMAX_API_KEY", "")
MODEL = "MiniMax-M2.5"  # 快速且便宜，够用


def call_llm(system_prompt, user_message, max_tokens=4000):
    """调用 MiniMax API（Anthropic Messages 格式）。"""
    url = f"{API_BASE.rstrip('/').replace('/v1','')}/anthropic/v1/messages"
    headers = {
        "Content-Type": "application/json",
        "x-api-key": API_KEY,
        "anthropic-version": "2023-06-01",
    }
    payload = {
        "model": MODEL,
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_message}],
    }
    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        # MiniMax 返回 content 数组中可能有 thinking + text，取 text 类型
        for block in data.get("content", []):
            if block.get("type") == "text":
                return block["text"]
        return data["content"][0].get("text", str(data["content"][0]))
    except Exception as e:
        print(f"❌ LLM 调用失败: {e}", file=sys.stderr)
        # 回退到 OpenClaw agent
        import subprocess
        result = subprocess.run(
            ["openclaw", "agent", "--agent", "main", "-m", user_message[:3000]],
            capture_output=True, text=True, timeout=120
        )
        return result.stdout if result.returncode == 0 else f"AI 分析不可用: {e}"


def prepare_condensed_reports(data):
    """将周报压缩为 LLM 可处理的摘要。"""
    reports = data.get("reports", [])
    condensed = []
    for r in reports:
        body = r.get("body", "")[:800]  # 每人最多 800 字
        condensed.append(
            f"【{r['sender_name']}】{r['subject']}\n{body}"
        )
    return "\n\n---\n\n".join(condensed)


def load_last_week_risks():
    """加载上周风险用于趋势对比。"""
    risks_dir = MEMORY_DIR / "risks"
    if not risks_dir.exists():
        return ""
    files = sorted(risks_dir.glob("*.md"))
    if len(files) >= 2:
        return files[-2].read_text(encoding="utf-8")[:2000]
    return ""


def ai_risk_analysis(condensed_text):
    """AI 智能风险提取与分级。"""
    system = """你是天下先智创机器人（物流分拣机器人公司）的风险分析专家。
从员工周报中提取真实风险，严格区分"风险"和"正常工作内容"。

输出 JSON 格式：
{
  "high_risks": [{"reporter":"姓名", "project":"项目", "description":"风险描述", "impact":"影响", "suggestion":"建议"}],
  "medium_risks": [...],
  "low_risks": [...],
  "systemic_risks": [{"description":"描述", "involved_people":["人1","人2"], "pattern":"模式"}],
  "resolved": [{"description":"已解决的问题", "reporter":"姓名"}]
}

规则：
- 🔴 高风险：安全事故（掉车/损坏）、客户敏感（源代码/投诉/终验失败）、生产中断
- 🟡 中风险：延期风险、技术难题未解、供应商交期、识别率不达标
- 🟢 低风险：待确认事项、轻微异常、已有解决方案
- 系统性风险：多人同时提到的相同问题
- "暂无风险"、"无"、"本周正常"不是风险，忽略
- 正常工作进展不是风险，忽略"""

    user = f"以下是本周 {len(condensed_text.split('---'))} 名员工的周报摘要，请提取风险：\n\n{condensed_text[:12000]}"

    result = call_llm(system, user)
    try:
        # 提取 JSON
        json_match = re.search(r'\{[\s\S]*\}', result)
        if json_match:
            return json.loads(json_match.group())
    except json.JSONDecodeError:
        pass
    return {"raw_analysis": result}


def ai_insights(condensed_text, risk_analysis, last_week_risks):
    """生成 CEO 级别的洞察与建议。"""
    system = """你是天下先智创机器人 CEO 的管理顾问。基于员工周报和风险分析，为 CEO 生成简明的洞察报告。

输出 JSON 格式：
{
  "executive_summary": "3句话总结本周公司状态",
  "top3_priorities": [{"item":"事项", "reason":"原因", "action":"建议动作"}],
  "cross_department_issues": ["跨部门问题1", "问题2"],
  "workload_alerts": [{"person":"姓名", "issue":"问题"}],
  "positive_highlights": ["亮点1", "亮点2"],
  "trend_vs_last_week": "与上周对比的变化趋势",
  "next_week_focus": ["下周重点关注1", "关注2", "关注3"]
}

要求：
- 站在 CEO 视角，只说他需要做决策的事
- 数据说话，不要空话
- 建议要具体可执行"""

    risk_summary = json.dumps(risk_analysis, ensure_ascii=False)[:3000] if isinstance(risk_analysis, dict) else str(risk_analysis)[:3000]

    user = f"""本周周报摘要（{len(condensed_text.split('---'))}人）：
{condensed_text[:8000]}

---
风险分析结果：
{risk_summary}

---
上周风险（对比用）：
{last_week_risks[:2000]}

请生成 CEO 洞察报告。"""

    result = call_llm(system, user)
    try:
        json_match = re.search(r'\{[\s\S]*\}', result)
        if json_match:
            return json.loads(json_match.group())
    except json.JSONDecodeError:
        pass
    return {"raw_insights": result}


def ai_quality_scoring(condensed_text):
    """AI 周报质量评分 — 每人打分。"""
    system = """你是周报质量评审员。对每份周报从4个维度打分(1-5分)并给出简评。

输出 JSON 格式：
{
  "scores": [
    {
      "name": "姓名",
      "completeness": 4,
      "risk_clarity": 3,
      "quantification": 5,
      "actionability": 4,
      "total": 16,
      "grade": "A",
      "comment": "一句话点评"
    }
  ],
  "average_score": 13.5,
  "best": ["姓名1"],
  "needs_improvement": ["姓名2"]
}

评分标准：
- completeness(完整度): 问题风险+本周工作+下周计划三段齐全=5分,缺一段-1分,"暂无"算缺
- risk_clarity(风险清晰度): 有具体风险描述+影响+措施=5分,空泛=2分,没写=1分
- quantification(量化程度): 有百分比进度/数据=5分,纯文字描述=3分,太笼统=1分
- actionability(可执行度): 下周计划具体可执行=5分,模糊=2分
- grade: 18-20=S, 15-17=A, 12-14=B, 8-11=C, <8=D
- 只输出JSON,不要其他文字"""

    user = f"以下是本周各员工周报，请逐一打分：\n\n{condensed_text[:12000]}"
    result = call_llm(system, user, max_tokens=4000)
    try:
        json_match = re.search(r'\{[\s\S]*\}', result)
        if json_match:
            return json.loads(json_match.group())
    except json.JSONDecodeError:
        pass
    return {"raw_scores": result}


def ai_skill_extraction(condensed_text):
    """从周报中提取人员技能标签。"""
    system = """你是技术团队能力分析师。从员工周报中提取每人的技能标签和项目经验。

输出 JSON 格式：
{
  "profiles": [
    {
      "name": "姓名",
      "skills": ["Vue3", "TypeScript", "PLC", "OCR"],
      "projects": ["菜鸟新加坡", "屈臣氏V2"],
      "role_tags": ["前端", "全栈", "项目管理"],
      "ai_tools": ["Claude Code", "Codex"],
      "domains": ["物流分拣", "视觉识别"]
    }
  ]
}

规则：
- skills: 具体技术栈(编程语言/框架/协议/硬件)
- projects: 参与的项目名称
- role_tags: 实际承担的角色
- ai_tools: 使用的AI工具
- domains: 业务领域专长
- 只从周报内容中提取,不要猜测
- 只输出JSON"""

    user = f"从以下周报中提取每人的技能画像：\n\n{condensed_text[:12000]}"
    result = call_llm(system, user, max_tokens=4000)
    try:
        json_match = re.search(r'\{[\s\S]*\}', result)
        if json_match:
            return json.loads(json_match.group())
    except json.JSONDecodeError:
        pass
    return {"raw_profiles": result}


def ai_pattern_detection(trends_dir):
    """预测性预警 — 从历史趋势中识别模式（需3周以上数据）。"""
    trend_files = sorted(trends_dir.glob("*.json")) if trends_dir.exists() else []
    if len(trend_files) < 3:
        return {"message": f"数据不足({len(trend_files)}周)，需至少3周才能识别模式"}

    history = []
    for f in trend_files[-8:]:  # 最多看最近8周
        try:
            history.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            pass

    if len(history) < 3:
        return {"message": "有效数据不足"}

    history_text = json.dumps(history, ensure_ascii=False)[:6000]

    system = """你是项目风险模式识别专家。从多周的趋势数据中识别重复模式和潜在风险。

输出 JSON：
{
  "patterns": [
    {"pattern":"描述", "confidence":"高/中/低", "evidence":"证据", "prediction":"预测", "action":"建议"}
  ],
  "recurring_risks": ["反复出现的风险类型"],
  "improving_areas": ["改善中的领域"],
  "deteriorating_areas": ["恶化中的领域"]
}"""

    user = f"以下是最近{len(history)}周的趋势数据，请识别模式：\n\n{history_text}"
    result = call_llm(system, user, max_tokens=2000)
    try:
        json_match = re.search(r'\{[\s\S]*\}', result)
        if json_match:
            return json.loads(json_match.group())
    except json.JSONDecodeError:
        pass
    return {"raw_patterns": result}


def update_people_skills(profiles_data):
    """将技能画像写入员工档案。"""
    people_dir = MEMORY_DIR / "people"
    if not people_dir.exists():
        return

    profiles = profiles_data.get("profiles", [])
    for profile in profiles:
        name = profile.get("name", "")
        skills = profile.get("skills", [])
        if not name or not skills:
            continue

        # 查找匹配的员工文件
        for f in people_dir.glob("*.md"):
            content = f.read_text(encoding="utf-8")
            if f"# {name}" in content:
                # 更新或添加技能段落
                skills_str = ", ".join(skills)
                projects_str = ", ".join(profile.get("projects", []))
                role_str = ", ".join(profile.get("role_tags", []))

                if "## 技能画像" in content:
                    # 更新已有段落
                    content = re.sub(
                        r"## 技能画像[\s\S]*?(?=\n## |\Z)",
                        f"## 技能画像\n- 技术栈：{skills_str}\n- 项目经验：{projects_str}\n- 角色：{role_str}\n\n",
                        content
                    )
                else:
                    content = content.rstrip() + f"\n\n## 技能画像\n- 技术栈：{skills_str}\n- 项目经验：{projects_str}\n- 角色：{role_str}\n"

                f.write_text(content, encoding="utf-8")
                break


def save_trend(week_label, risk_analysis, insights):
    """保存趋势分析。"""
    trends_dir = MEMORY_DIR / "trends"
    trends_dir.mkdir(exist_ok=True)

    trend_data = {
        "week": week_label,
        "generated_at": datetime.now().isoformat(),
        "risk_counts": {
            "high": len(risk_analysis.get("high_risks", [])),
            "medium": len(risk_analysis.get("medium_risks", [])),
            "low": len(risk_analysis.get("low_risks", [])),
            "systemic": len(risk_analysis.get("systemic_risks", [])),
        },
        "executive_summary": insights.get("executive_summary", ""),
        "top3_priorities": insights.get("top3_priorities", []),
        "trend_vs_last_week": insights.get("trend_vs_last_week", ""),
    }

    filepath = trends_dir / f"{week_label}.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(trend_data, f, ensure_ascii=False, indent=2)

    # 也保存可读的 markdown
    md_path = trends_dir / f"{week_label}.md"
    md = f"# 趋势分析 {week_label}\n\n"
    md += f"## 总结\n{trend_data['executive_summary']}\n\n"
    md += f"## 风险统计\n🔴 高 {trend_data['risk_counts']['high']} / 🟡 中 {trend_data['risk_counts']['medium']} / 🟢 低 {trend_data['risk_counts']['low']} / 🔗 系统性 {trend_data['risk_counts']['systemic']}\n\n"
    md += f"## 与上周对比\n{trend_data['trend_vs_last_week']}\n\n"
    md += f"## CEO 优先事项\n"
    for i, p in enumerate(trend_data["top3_priorities"], 1):
        if isinstance(p, dict):
            md += f"{i}. **{p.get('item','')}** — {p.get('reason','')} → {p.get('action','')}\n"
        else:
            md += f"{i}. {p}\n"
    md_path.write_text(md, encoding="utf-8")

    return filepath


def main():
    parser = argparse.ArgumentParser(description="AI 周报分析引擎")
    parser.add_argument("json_path", help="周报 JSON 路径")
    parser.add_argument("--output", "-o", help="输出路径")
    parser.add_argument("--week", help="周标签")
    args = parser.parse_args()

    with open(args.json_path, encoding="utf-8") as f:
        data = json.load(f)

    period = data.get("period", "")
    week_label = args.week
    if not week_label:
        try:
            start = datetime.strptime(period.split(" ~ ")[0], "%Y-%m-%d")
            week_label = f"{start.isocalendar()[0]}-W{start.isocalendar()[1]:02d}"
        except Exception:
            week_label = datetime.now().strftime("%Y-W%W")

    print(f"🤖 AI 分析引擎启动", file=sys.stderr)
    print(f"   周期: {period} ({week_label})", file=sys.stderr)
    print(f"   周报数: {data['count']}", file=sys.stderr)

    # 压缩周报
    print(f"\n📝 压缩周报...", file=sys.stderr)
    condensed = prepare_condensed_reports(data)
    print(f"   压缩后: {len(condensed)} 字符", file=sys.stderr)

    # AI 风险分析
    print(f"\n🔍 AI 风险分析...", file=sys.stderr)
    risk_analysis = ai_risk_analysis(condensed)
    h = len(risk_analysis.get("high_risks", []))
    m = len(risk_analysis.get("medium_risks", []))
    s = len(risk_analysis.get("systemic_risks", []))
    print(f"   🔴 高风险 {h} / 🟡 中风险 {m} / 🔗 系统性 {s}", file=sys.stderr)

    # 加载上周风险
    last_week = load_last_week_risks()

    # AI 洞察
    print(f"\n💡 AI CEO 洞察...", file=sys.stderr)
    insights = ai_insights(condensed, risk_analysis, last_week)
    print(f"   ✅ 洞察生成完成", file=sys.stderr)

    # 周报质量评分
    print(f"\n📝 AI 周报质量评分...", file=sys.stderr)
    quality_scores = ai_quality_scoring(condensed)
    scores = quality_scores.get("scores", [])
    avg = quality_scores.get("average_score", 0)
    print(f"   ✅ {len(scores)} 人评分完成，均分 {avg}", file=sys.stderr)

    # 人员技能画像
    print(f"\n👤 AI 技能画像提取...", file=sys.stderr)
    skill_profiles = ai_skill_extraction(condensed)
    profiles = skill_profiles.get("profiles", [])
    print(f"   ✅ {len(profiles)} 人技能提取完成", file=sys.stderr)
    update_people_skills(skill_profiles)

    # 预测性模式检测
    print(f"\n🔮 预测性模式检测...", file=sys.stderr)
    patterns = ai_pattern_detection(MEMORY_DIR / "trends")
    if "message" in patterns:
        print(f"   ⏳ {patterns['message']}", file=sys.stderr)
    else:
        print(f"   ✅ 检测到 {len(patterns.get('patterns', []))} 个模式", file=sys.stderr)

    # 保存趋势
    print(f"\n📊 保存趋势...", file=sys.stderr)
    trend_path = save_trend(week_label, risk_analysis, insights)
    print(f"   ✅ {trend_path}", file=sys.stderr)

    # 输出结果
    result = {
        "week": week_label,
        "period": period,
        "report_count": data["count"],
        "risk_analysis": risk_analysis,
        "insights": insights,
        "quality_scores": quality_scores,
        "skill_profiles": skill_profiles,
        "patterns": patterns,
        "trend_path": str(trend_path),
    }

    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"\n💾 已保存到 {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
