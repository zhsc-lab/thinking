#!/usr/bin/env python3
"""
AEFS Cross-Agent Propagator — 跨 Agent 学习传播器
====================================================
当一个 Agent 的某错误类型触发权重升级时，自动将轻量预防规则
传播给同类标签的其他 Agent，实现跨 Agent 经验共享。

设计原则：
- 传播的规则权重减半（不会喧宾夺主）
- 仅传播「高频通用」的错误类型（排除 Agent 特定 bug）
- 每个 Agent 接收的跨源规则 ≤ 3 条（避免信息过载）

用法:
  python -m src.aefs.propagator --upgrade tutor ToolCall 1.5
  python -m src.aefs.propagator --review
"""
import json, os, sys
from datetime import datetime

from .config import (
    PENALTY_FILE, INJECTION_FILE,
    ALL_AGENTS, UNIVERSAL_TAGS,
)


def load_injections() -> dict:
    if os.path.exists(INJECTION_FILE):
        with open(INJECTION_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"active_injections": []}


def save_injections(data: dict):
    data["_meta"]["last_updated"] = datetime.now().strftime("%Y-%m-%d")
    with open(INJECTION_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_penalty() -> dict:
    if os.path.exists(PENALTY_FILE):
        with open(PENALTY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_penalty(data: dict):
    data["_meta"]["last_updated"] = datetime.now().strftime("%Y-%m-%d")
    with open(PENALTY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def propagate(source_agent: str, tag: str, source_weight: float, source_rule: str) -> dict:
    """
    从 source_agent 向其他 Agent 传播预防规则

    规则：
    - 只有通用标签才传播
    - 传播目标 = 除 source 外的所有 Agent
    - 传播权重 = source_weight × 0.5（减半）
    - 不覆盖目标 Agent 自身已有的更高权重规则
    """
    if tag not in UNIVERSAL_TAGS:
        return {"propagated": False, "reason": f"标签 [{tag}] 是 Agent 特有类型，不跨传播"}

    injections = load_injections()
    active = injections["active_injections"]
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    propagated_count = 0
    targets = []

    for target_agent in ALL_AGENTS:
        if target_agent == source_agent:
            continue

        prop_weight = max(0.5, round(source_weight * 0.5, 1))

        existing = None
        for r in active:
            if r.get("agent") == target_agent and r.get("tag") == tag:
                existing = r
                break

        if existing:
            if prop_weight > existing.get("weight", 0):
                old_w = existing.get("weight", 1.0)
                existing["weight"] = prop_weight
                existing["rule"] = f"[跨 Agent 学习] {source_rule}"
                existing["source"] = f"来自 {source_agent} 的经验"
                existing["cross_agent"] = True
                existing["propagated_at"] = now
                propagated_count += 1
                targets.append(f"{target_agent} (更新: {old_w}→{prop_weight})")
        else:
            new_rule = {
                "tag": tag,
                "agent": target_agent,
                "weight": prop_weight,
                "priority": "low",
                "rule": f"[跨 Agent 学习] {source_rule}",
                "source": f"来自 {source_agent} 的经验",
                "cross_agent": True,
                "propagated_at": now,
                "checklist": [
                    "❓ 你的同类操作是否也有同样风险？",
                    f"❓ ({source_agent} 已经在这个坑上吃过亏)",
                ],
            }
            active.append(new_rule)
            propagated_count += 1
            targets.append(f"{target_agent} (新增, {prop_weight})")

    injections["_meta"]["last_cross_propagate"] = now
    injections["_meta"]["cross_propagate_count"] = (
        injections["_meta"].get("cross_propagate_count", 0) + propagated_count
    )

    save_injections(injections)

    return {
        "propagated": True,
        "source": source_agent,
        "tag": tag,
        "propagated_count": propagated_count,
        "targets": targets,
    }


def review_cross_rules() -> dict:
    """审查当前所有跨 Agent 学习规则的摘要"""
    injections = load_injections()
    active = injections["active_injections"]
    cross = [r for r in active if r.get("cross_agent")]

    summary = {}
    for r in cross:
        agent = r.get("agent", "?")
        tag = r.get("tag", "?")
        weight = r.get("weight", 0)
        source = r.get("source", "未知")
        if agent not in summary:
            summary[agent] = []
        summary[agent].append({"tag": tag, "weight": weight, "source": source})

    return {
        "total_cross_rules": len(cross),
        "agents_affected": len(summary),
        "details": summary,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def main():
    args = sys.argv[1:]

    if "--review" in args:
        result = review_cross_rules()
        print("=" * 56)
        print("  跨 Agent 学习 — 状态审查")
        print("=" * 56)
        print(f"  总跨源规则数: {result['total_cross_rules']}")
        print(f"  受影响 Agent: {result['agents_affected']} 个")
        print()
        for agent, rules in result["details"].items():
            print(f"  🤖 {agent}:")
            for r in rules:
                print(f"    [{r['tag']}] 权重 {r['weight']}× ← {r['source']}")
        print()
        if not result["total_cross_rules"]:
            print("  (暂无跨 Agent 学习规则)")
        return

    if "--upgrade" in args:
        idx = args.index("--upgrade")
        if idx + 3 >= len(args):
            print("[Error] --upgrade 需要 agent tag weight 三个参数")
            sys.exit(1)
        source = args[idx + 1]
        tag = args[idx + 2].replace("[", "").replace("]", "")
        weight = float(args[idx + 3])

        injections = load_injections()
        rule_text = ""
        for r in injections.get("active_injections", []):
            if r.get("agent") == source and r.get("tag") == tag:
                rule_text = r.get("rule", "")
                break

        result = propagate(source, tag, weight, rule_text)
        if result["propagated"]:
            print(f"[Cross] ✅ 已向 {result['propagated_count']} 个 Agent 传播 [{tag}] 预防规则")
            for t in result["targets"]:
                print(f"  → {t}")
        else:
            print(f"[Cross] ⏭️ {result.get('reason', '跳过')}")
        return

    print("用法:")
    print("  python -m src.aefs.propagator --upgrade agent tag weight")
    print("  python -m src.aefs.propagator --review")
    print()
    print("示例:")
    print("  python -m src.aefs.propagator --upgrade tutor ToolCall 1.5")


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    main()
