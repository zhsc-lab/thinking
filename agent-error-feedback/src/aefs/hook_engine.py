#!/usr/bin/env python3
"""
AEFS Hook Engine — Agent 预防规则查询
=======================================
供子 Agent 在启动时自读自己的预防规则。

用法:
  python -m src.aefs.hook_engine tutor           # 输出 tutor 的预防规则
  python -m src.aefs.hook_engine --all            # 输出所有 Agent 的规则
  python -m src.aefs.hook_engine --notify tutor   # 只输出有变化的规则
  python -m src.aefs.hook_engine --check          # 检查是否有新规则
"""
import json, os, sys
from datetime import datetime

from .config import PENALTY_FILE, INJECTION_FILE


def load_injections() -> dict:
    if os.path.exists(INJECTION_FILE):
        with open(INJECTION_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"active_injections": []}


def load_penalty() -> dict:
    if os.path.exists(PENALTY_FILE):
        with open(PENALTY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def get_agent_table(penalty: dict) -> dict:
    """从惩罚数据库中提取所有 Agent 的违规摘要表格"""
    table = {}
    for agent in sorted(penalty.keys()):
        if agent == "_meta":
            continue
        tags = penalty.get(agent, {})
        for tag, entry in tags.items():
            if agent not in table:
                table[agent] = {}
            table[agent][tag] = {
                "points": entry.get("points", 3),
                "strikes": entry.get("strikes", 0),
                "weight": entry.get("weight", 1.0),
            }
    return table


def format_rules_for_agent(agent_type: str, injections: list, penalty_table: dict) -> str:
    """为指定 Agent 格式化预防规则"""
    my_rules = [r for r in injections if r.get("agent") == agent_type]
    my_penalty = penalty_table.get(agent_type, {})

    lines = []
    lines.append(f"## ⚠️ 错题本 — {agent_type} 的历史犯规记录")
    lines.append(f"> 自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")

    if my_penalty:
        lines.append("### 📊 当前扣分状态")
        lines.append("")
        lines.append("| 错误类型 | 剩余分数 | 违规次数 | 权重 |")
        lines.append("|----------|---------|---------|------|")
        for tag, data in sorted(my_penalty.items()):
            pts = data.get("points", 3)
            stk = data.get("strikes", 0)
            wt = data.get("weight", 1.0)
            display_tag = tag.replace("[", "").replace("]", "")
            bar = "█" * pts + "░" * max(0, 3 - pts)
            lines.append(f"| [{display_tag}] | {bar} {pts}/3 | {stk} 次 | {wt}× |")
        lines.append("")

    if not my_rules:
        lines.append("*暂无活跃预防规则*")
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("> 💡 无规则意味着该 Agent 近期未触发惩罚升级，继续保持。")
        return "\n".join(lines)

    my_rules.sort(key=lambda r: r.get("weight", 1.0), reverse=True)

    lines.append("### 🚨 必须遵守的预防规则")
    lines.append("")
    for rule in my_rules:
        tag = rule.get("tag", "?")
        weight = rule.get("weight", 1.0)
        rule_text = rule.get("rule", "无具体规则")

        if weight >= 3.0:
            badge = "🔴 CRITICAL"
        elif weight >= 2.0:
            badge = "🟠 HIGH"
        elif weight >= 1.5:
            badge = "🟡 MEDIUM"
        else:
            badge = "🟢 NORMAL"

        lines.append(f"**{badge}** `[{tag}]` (权重 {weight}×)")
        lines.append(f"> {rule_text}")
        lines.append("")

        checklist = rule.get("checklist", [])
        if checklist:
            lines.append("自查清单：")
            for item in checklist:
                lines.append(f"- {item}")
            lines.append("")

    cross_rules = [r for r in injections if r.get("agent") != agent_type and r.get("weight", 0) >= 2.0]
    if cross_rules:
        lines.append("### 🔗 跨 Agent 参考（同伴踩过的坑）")
        lines.append("")
        lines.append("以下规则来自其他 Agent 的高频错误，虽然还没在你身上发生，但值得注意：")
        lines.append("")
        for rule in cross_rules[:3]:
            src_agent = rule.get("agent", "?")
            tag = rule.get("tag", "?")
            rule_text = rule.get("rule", "")
            lines.append(f"- **{src_agent}** `[{tag}]` → {rule_text[:80]}...")
        lines.append("")

    lines.append("---")
    lines.append("> 执行前请逐条过一遍自查清单。如果你犯了规则中描述的错误，分数会被扣减。")

    return "\n".join(lines)


def check_new_rules(injections: dict) -> bool:
    """检查自上次查看后是否有新规则"""
    history = injections.get("injection_history", [])
    if not history:
        return False
    last = history[-1]
    last_time = last.get("date", "")
    if not last_time:
        return False
    today = datetime.now().strftime("%Y-%m-%d")
    return today in last_time


def main():
    args = sys.argv[1:]
    injections = load_injections()
    active = injections.get("active_injections", [])
    penalty = load_penalty()
    penalty_table = get_agent_table(penalty)

    if "--check" in args:
        sys.exit(0 if check_new_rules(injections) else 1)

    if "--notify" in args:
        if not check_new_rules(injections):
            sys.exit(0)
        history = injections.get("injection_history", [])
        last = history[-1] if history else {}
        print(f"[Hooks] 🚨 新预防规则已注入: {last.get('agent','?')} × {last.get('tag','?')} (权重 {last.get('weight',1.0)}×)")
        print(f"[Hooks] 运行 `python -m src.aefs.hook_engine {last.get('agent','')}` 查看详情")
        return

    if "--all" in args:
        agents_in_use = set(r.get("agent", "") for r in active)
        agents_in_use.update(k for k in penalty_table.keys() if k != "_meta")
        for agent in sorted(agents_in_use):
            output = format_rules_for_agent(agent, active, penalty_table)
            print(f"\n{'='*60}")
            print(output)

    elif not args or args[0].startswith("-"):
        agents_in_use = set(r.get("agent", "") for r in active)
        agents_in_use.update(k for k in penalty_table.keys() if k != "_meta")
        for agent in sorted(agents_in_use):
            output = format_rules_for_agent(agent, active, penalty_table)
            print(f"\n{'='*60}")
            print(output)
    else:
        agent_type = args[0]
        output = format_rules_for_agent(agent_type, active, penalty_table)
        print(output)


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    main()
