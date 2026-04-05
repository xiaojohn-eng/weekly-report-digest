#!/usr/bin/env python3
"""
将公司知识快照同步到 OpenClaw agent 的上下文中。

机制：
1. 精炼 company_snapshot.md → 控制在 ~2000 token
2. 写入 OpenClaw 的 bootstrap context 目录
3. 更新 memory-tdai 的 scene_block（如果可用）

用法:
  python3 sync_to_openclaw.py
"""
import os
import re
from pathlib import Path
from datetime import datetime

MEMORY_DIR = Path("/root/.openclaw/memory-weekly")
SNAPSHOT_PATH = MEMORY_DIR / "company_snapshot.md"

# OpenClaw bootstrap context（agent 启动时加载）
OPENCLAW_BOOTSTRAP_DIR = Path("/root/.openclaw/agents/main")
COMPANY_CONTEXT_PATH = OPENCLAW_BOOTSTRAP_DIR / "company-context.md"

# memory-tdai scene blocks
SCENE_BLOCKS_DIR = Path("/root/.openclaw/memory-tdai/scene_blocks")


def build_compact_context():
    """从完整快照中提炼精简版上下文（~2000 token）。"""
    if not SNAPSHOT_PATH.exists():
        return None

    full = SNAPSHOT_PATH.read_text(encoding="utf-8")

    # 提取关键段落
    sections = {}
    current = None
    for line in full.split("\n"):
        if line.startswith("## "):
            current = line.strip("# ").strip()
            sections[current] = []
        elif current:
            sections[current].append(line)

    # 构建精简版
    compact = f"""# 天下先智创机器人 — 公司上下文
> 数据来源: 员工周报 | 更新于 {datetime.now().strftime('%Y-%m-%d')}

## 公司概况
天下先智创机器人(TG Robot)：物流分拣机器人公司。
核心产品：木马分拣机（小车式自动分拣+视觉OCR）、工作站系统、PDA系统、3D演示。
主要客户：顺丰、拼多多、菜鸟、虾皮、希音、屈臣氏、Ozon。
业务区域：中国多城市 + 新加坡、日本、美国、俄罗斯。

"""

    # 组织架构（精简）
    if "组织架构" in sections:
        org_text = "\n".join(sections["组织架构"])
        # 提取部门和人数
        depts = re.findall(r"### (.+?)（(\d+)人）", org_text)
        compact += "## 组织架构\n"
        for dept, count in depts:
            members = re.findall(r"- (.+)", org_text.split(f"### {dept}")[1].split("###")[0] if f"### {dept}" in org_text else "")
            compact += f"- **{dept}**（{count}人）：{', '.join(members[:8])}\n"
        compact += "\n"

    # 项目全景（精简：只列项目名）
    if "项目全景" in sections:
        proj_text = "\n".join(sections["项目全景"])
        projects = re.findall(r"\| (.+?) \|", proj_text)
        projects = [p.strip() for p in projects if p.strip() not in ("项目", "状态", "------")]
        compact += f"## 活跃项目（{len(projects)//2}个）\n"
        # 去重并精简
        seen = set()
        for p in projects:
            if p != "进行中" and p not in seen:
                seen.add(p)
                compact += f"- {p}\n"
        compact += "\n"

    # 最近风险（从 risks/ 目录直接读取最新一期，精炼为要点）
    risks_dir = MEMORY_DIR / "risks"
    if risks_dir.exists():
        risk_files = sorted(risks_dir.glob("*.md"), reverse=True)
        if risk_files:
            risk_content = risk_files[0].read_text(encoding="utf-8")
            # 提取高风险和中风险的报告人+摘要
            compact += "## 最近风险\n"
            for level, emoji in [("🔴 高风险", "🔴"), ("🟡 中风险", "🟡")]:
                if level in risk_content:
                    compact += f"\n### {level}\n"
                    # 提取 **人名** (主题) 后面的 > 引用内容前100字
                    blocks = re.findall(r"\*\*(.+?)\*\*\s*\((.+?)\)\s*\n>\s*(.+?)(?=\n\n|\*\*|\Z)", risk_content, re.DOTALL)
                    section_text = risk_content.split(level)[-1].split("## ")[0] if level in risk_content else ""
                    reporter_blocks = re.findall(r"\*\*(.+?)\*\*\s*\((.+?)\)\n> (.+?)(?=\n\n\*\*|\n\n##|\Z)", section_text, re.DOTALL)
                    for name, subj, detail in reporter_blocks:
                        # 取第一行有意义的文字
                        detail_clean = re.sub(r'\s+', ' ', detail).strip()[:150]
                        compact += f"- **{name}**（{subj[:30]}）：{detail_clean}\n"
            compact += "\n"

    # 控制总长度
    if len(compact) > 4000:
        compact = compact[:4000] + "\n\n... [已截断，完整版见 memory-weekly/company_snapshot.md]"

    return compact


def sync_bootstrap():
    """写入 OpenClaw agent bootstrap context。"""
    compact = build_compact_context()
    if not compact:
        print("❌ 无公司快照可同步")
        return False

    COMPANY_CONTEXT_PATH.write_text(compact, encoding="utf-8")
    print(f"✅ 已同步到 OpenClaw bootstrap: {COMPANY_CONTEXT_PATH}")
    print(f"   大小: {len(compact)} 字符")
    return True


def sync_scene_block():
    """更新 memory-tdai 的 scene_block。"""
    if not SCENE_BLOCKS_DIR.exists():
        print("⚠️  memory-tdai scene_blocks 目录不存在，跳过")
        return

    scene_path = SCENE_BLOCKS_DIR / "公司知识-周报积累.md"
    compact = build_compact_context()
    if not compact:
        return

    # memory-tdai scene block 格式
    scene_content = f"""---
title: 公司知识-周报积累
heat: 50
updated: {datetime.now().isoformat()}
summary: 从员工周报中积累的天下先智创机器人公司知识，包含组织架构、项目全景、风险登记、人员档案。每周自动更新。
---

{compact}

## 知识库文件索引
- 完整快照: /root/.openclaw/memory-weekly/company_snapshot.md
- 员工档案: /root/.openclaw/memory-weekly/people/
- 项目档案: /root/.openclaw/memory-weekly/projects/
- 风险登记: /root/.openclaw/memory-weekly/risks/
- 周报摘要: /root/.openclaw/memory-weekly/digests/
"""
    scene_path.write_text(scene_content, encoding="utf-8")
    print(f"✅ 已更新 memory-tdai scene_block: {scene_path}")


def sync_workspace_memory():
    """更新 OpenClaw workspace 的 MEMORY.md（agent 启动时必读）。"""
    memory_path = Path("/root/.openclaw/workspace/MEMORY.md")
    snapshot = SNAPSHOT_PATH.read_text(encoding="utf-8") if SNAPSHOT_PATH.exists() else ""

    # 从快照提取关键信息构建 MEMORY.md
    people_dir = MEMORY_DIR / "people"
    projects_dir = MEMORY_DIR / "projects"

    people_count = len(list(people_dir.glob("*.md"))) if people_dir.exists() else 0
    project_count = len(list(projects_dir.glob("*.md"))) if projects_dir.exists() else 0
    risk_files = sorted((MEMORY_DIR / "risks").glob("*.md"), reverse=True) if (MEMORY_DIR / "risks").exists() else []
    digest_files = sorted((MEMORY_DIR / "digests").glob("*.md"), reverse=True) if (MEMORY_DIR / "digests").exists() else []

    compact = build_compact_context()
    if not compact:
        print("⚠️  无公司快照可同步到 MEMORY.md")
        return

    content = f"""# Long-Term Memory

## 公司知识（自动更新于 {datetime.now().strftime('%Y-%m-%d')}）

> 数据来源：员工周报 | {people_count} 名员工 | {project_count} 个项目 | {len(risk_files)} 周风险记录

{compact}

## 查询深度知识

需要更详细信息时，读取以下文件：
- 员工档案：`/root/.openclaw/memory-weekly/people/{{email}}.md`
- 项目档案：`/root/.openclaw/memory-weekly/projects/{{code}}.md`
- 风险登记：`/root/.openclaw/memory-weekly/risks/{{YYYY-Wxx}}.md`
- 周报摘要：`/root/.openclaw/memory-weekly/digests/{{YYYY-Wxx}}.md`
- 完整快照：`/root/.openclaw/memory-weekly/company_snapshot.md`
"""
    memory_path.write_text(content, encoding="utf-8")
    print(f"✅ 已更新 workspace MEMORY.md: {memory_path}")


def main():
    print(f"同步公司知识到 OpenClaw ...")
    print(f"快照路径: {SNAPSHOT_PATH}")
    print(f"{'存在' if SNAPSHOT_PATH.exists() else '不存在'}")
    print()

    sync_bootstrap()
    sync_scene_block()
    sync_workspace_memory()

    print()
    print("🔄 同步完成。OpenClaw 下次对话将自动携带公司上下文。")
    print("   如需立即生效，可重启 gateway: openclaw gateway restart")


if __name__ == "__main__":
    main()
