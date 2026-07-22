#!/usr/bin/env python3
"""
AEFS Pipeline — 四方分析 × 惩罚机制 × 质检门禁 × 知识注入闭环
==============================================================

对 Agent（Claude、GPT 等 LLM Agent）运行中的错误进行：
  ① 错误收集与结构化
  ② 四方分析（Qwen 完整性 + GLM 根因质检 + Kimi 标签审计 + DeepSeek 仲裁）
  ③ 惩罚机制（每 agent×tag 3 分，扣光→权重提升）
  ④ 质检门禁（≥9.6，不通过→迭代修订，最多 3 轮）
  ⑤ 知识注入（生成预防规则，更新 weight_injection.json）

用法:
  python -m src.aefs.pipeline                          # 增量：只处理新增错误
  python -m src.aefs.pipeline --full-scan               # 全量：重扫所有日志
  python -m src.aefs.pipeline --status                  # 查看状态
  python -m src.aefs.pipeline --dry-run                 # 试运行（不修改文件）
  python -m src.aefs.pipeline --reset tutor ToolCall    # 重置某组合分数
"""
import json, os, sys, time, re, urllib.request, urllib.error
from datetime import datetime

from .config import (
    DATA_DIR, INBOX_DIR, INBOX_ARCHIVE_DIR,
    PENALTY_FILE, INJECTION_FILE, AUDIT_LOG,
    QWEN_KEY, GLM_KEY, KIMI_KEY, KIMI_URL,
    QUALITY_THRESHOLD, MAX_ITERATIONS,
    PENALTY_INIT, PENALTY_DEDUCT, PENALTY_DEDUCT_SEVERE,
    WEIGHT_TABLE, TAG_SYSTEM,
)


# ════════════════════════════════════════════════════════════
#  底层 API 调用
# ════════════════════════════════════════════════════════════

def _call_llm(url: str, body: dict, api_key: str, timeout: int = 90) -> dict:
    """通用 HTTP LLM 调用"""
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"),
        headers=headers, method="POST",
    )
    start = time.time()
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                elapsed = time.time() - start
                if "choices" in result and result["choices"]:
                    msg = result["choices"][0]["message"]
                    text = msg.get("reasoning_content") or msg.get("content", "")
                    usage = result.get("usage", {})
                    return {"text": text, "usage": usage, "elapsed": elapsed, "success": True}
                return {"error": json.dumps(result, ensure_ascii=False)[:300], "success": False}
        except urllib.error.HTTPError as e:
            body_text = e.read().decode("utf-8", errors="replace")
            err_msg = f"HTTP {e.code}: {body_text[:200]}"
        except Exception as e:
            err_msg = str(e)[:200]
        if attempt < 1:
            time.sleep(3)
            continue
        return {"error": err_msg, "success": False}


def _extract_score(text: str) -> float:
    """从模型返回中提取综合评分"""
    for p in [r"综合评分[：:]\s*(\d+\.?\d*)", r"(\d+\.?\d*)\s*/?\s*10"]:
        m = re.search(p, text)
        if m:
            return float(m.group(1))
    return 0.0


def _extract_dim_scores(text: str) -> dict:
    """提取各维度子分"""
    scores = {}
    for line in text.split("\n"):
        m = re.match(r"(.+?)[：:]\s*(\d+\.?\d*)\s*/?\s*10?", line.strip())
        if m:
            dim = m.group(1).strip()
            scores[dim] = float(m.group(2))
    return scores


# ════════════════════════════════════════════════════════════
#  四方分析 — 四模型调用
# ════════════════════════════════════════════════════════════

def qwen_check_completeness(error_text: str, tag: str) -> dict:
    """Qwen — 错误记录完整性检查"""
    prompt = f"""你是一名 Agent 错误分析专家。请对以下 Agent 运行错误的**记录完整性**进行评分(满分10分)。

错误标签：{tag}

错误记录：
{error_text[:2000]}

评分维度（四维度）：
1. **描述清晰度** — 问题描述是否让人一眼看明白发生了什么？
2. **解决方案完整性** — 解决路径是否清晰可复现？是否有关键代码/命令？
3. **根因深度** — 是否追溯到根本原因，而不只是表面现象？
4. **泛化价值** — 是否有同类推广或通用化总结？

请按以下格式输出：
描述清晰度：X.X/10
解决方案完整性：X.X/10
根因深度：X.X/10
泛化价值：X.X/10
综合评分：X.X/10
修改建议：（如果评分<9.6，给出具体改进方向，每维最多一句话）"""
    return _call_llm(
        "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        {"model": "qwen-plus", "messages": [{"role": "user", "content": prompt}],
         "max_tokens": 1024, "temperature": 0.2},
        QWEN_KEY, 90)


def glm_quality_gate(error_text: str, tag: str) -> dict:
    """GLM — 根因正确性质检（主质检模型）"""
    prompt = f"""你是一名 Agent 质量质检员。请对以下 Agent 错误的**根因分析和解决方案**进行四维度评分(满分10分)，≥{QUALITY_THRESHOLD} 为通过。

错误标签：{tag}

错误记录：
{error_text[:1800]}

评分维度：
1. **根因准确性** — 根因分析是否站得住脚？有没有误判？
2. **修复正确性** — 给出的解决方案是否真的能解决问题？有没有潜在风险？
3. **安全性** — 该解决方案是否有副作用？会不会引入新问题？
4. **完整性** — 覆盖了从问题→分析→解决→预防的全流程吗？

请严格按以下格式输出：
根因准确性：X.X/10
修复正确性：X.X/10
安全性：X.X/10
完整性：X.X/10
综合评分：X.X/10
判定：[通过/不通过]
修改建议：（列出具体需要改进的地方，每维一句话，用 - 开头）"""
    r = _call_llm(
        "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        {"model": "glm-4-flash", "messages": [{"role": "user", "content": prompt}],
         "max_tokens": 1024, "temperature": 0.1},
        GLM_KEY, 60)
    if r.get("success"):
        r["score"] = _extract_score(r["text"])
        r["passed"] = r["score"] >= QUALITY_THRESHOLD
        r["dim_scores"] = _extract_dim_scores(r["text"])
    return r


def kimi_audit_tagging(error_text: str, tag: str) -> dict:
    """Kimi — 标签与分类审计"""
    valid_tags = ", ".join(TAG_SYSTEM)
    prompt = f"""你是一名错误分类审计员。请审计以下 Agent 错误的**标签与分类策略**。

当前标签：{tag}

可用标签：{valid_tags}

错误记录摘要：
{error_text[:1500]}

请从以下维度审查：
1. **标签准确性** — 当前标签 {tag} 是否准确？如果不准确，应该用什么标签？
2. **跨类关联** — 该错误是否与其他标签类别有关联？
3. **检索效率** — 如果以后要查同类错误，这个标签能快速定位吗？
4. **建议** — 给出标签优化建议

输出格式：
标签准确性：X.X/10
跨类关联度：X.X/10
检索效率：X.X/10
综合评分：X.X/10
标签建议：[推荐标签列表]
优化说明：..."""
    r = _call_llm(
        f"{KIMI_URL}/chat/completions",
        {"model": "kimi-k2.6", "messages": [{"role": "user", "content": prompt}],
         "max_tokens": 1024, "temperature": 0.2},
        KIMI_KEY, 90)
    if r.get("success"):
        r["score"] = _extract_score(r["text"])
        r["dim_scores"] = _extract_dim_scores(r["text"])
    return r


def ds_synthesize(
    agent_type: str, tag: str, error_text: str,
    qwen_r: dict, glm_r: dict, kimi_r: dict,
    penalty: dict,
) -> dict:
    """DeepSeek（主控）角色：合成四方分析结果，给出最终判定"""
    qwen_score = _extract_score(qwen_r.get("text", "")) if qwen_r.get("success") else 0
    glm_score = glm_r.get("score", 0) if glm_r.get("success") else 0
    kimi_score = _extract_score(kimi_r.get("text", "")) if kimi_r.get("success") else 0

    weights = {"qwen": 0.2, "glm": 0.4, "kimi": 0.2}
    available = sum(1 for s in [qwen_score, glm_score, kimi_score] if s > 0)

    if available == 0:
        composite = 0.0
    elif available == 1:
        composite = max(qwen_score, glm_score, kimi_score)
    else:
        keys = [k for k, s in [("qwen", qwen_score), ("glm", glm_score), ("kimi", kimi_score)] if s > 0]
        total_w = sum(weights[k] for k in keys)
        composite = sum(weights[k] / total_w * s
                        for k, s in [("qwen", qwen_score), ("glm", glm_score), ("kimi", kimi_score)]
                        if s > 0)

    passed = composite >= QUALITY_THRESHOLD and glm_r.get("passed", False)

    current_weight = penalty.get("weight", 1.0)
    strikes = penalty.get("strikes", 0)
    points = penalty.get("points", PENALTY_INIT)
    new_weight = current_weight
    if points <= 0 and strikes > 0:
        weight_idx = min(strikes, len(WEIGHT_TABLE) - 1)
        new_weight = max(current_weight, WEIGHT_TABLE[weight_idx])

    comp_issues = []
    if qwen_r.get("success") and qwen_score < QUALITY_THRESHOLD:
        comp_issues.append(f"记录完整性不足（{qwen_score:.1f}）— 建议补充关键细节")
    if glm_r.get("success") and glm_score < QUALITY_THRESHOLD:
        comp_issues.append(f"根因质检不达标（{glm_score:.1f}）— 建议重新审查根因分析")
    if kimi_r.get("success") and kimi_score < 7.0:
        comp_issues.append(f"标签分类需优化（{kimi_score:.1f}）")

    prevention_rule = _generate_prevention_rule(agent_type, tag, error_text, glm_r.get("text", ""), new_weight)

    return {
        "composite_score": round(composite, 2),
        "passed": passed,
        "qwen_score": qwen_score,
        "glm_score": glm_score,
        "kimi_score": kimi_score,
        "available_models": available,
        "current_weight": current_weight,
        "new_weight": new_weight,
        "weight_upgrade": new_weight > current_weight,
        "comp_issues": comp_issues,
        "prevention_rule": prevention_rule,
    }


def _generate_prevention_rule(agent_type: str, tag: str, error_text: str, glm_feedback: str, weight: float) -> dict:
    """从错误记录中提炼预防规则"""
    gen = ""
    for line in error_text.split("\n"):
        if "同类推广" in line or "通用" in line or "下次" in line:
            gen = line.strip()

    lines = [l.strip() for l in error_text.split("\n") if l.strip()]
    first_problem = ""
    for l in lines[:20]:
        if "问题" in l or "卡点" in l or "错误" in l:
            first_problem = l[:100]
            break

    suggestions = []
    if glm_feedback:
        for l in glm_feedback.split("\n"):
            if l.strip().startswith("-") and len(l) > 5:
                suggestions.append(l.strip().lstrip("- ").strip()[:120])

    return {
        "tag": tag,
        "agent": agent_type,
        "weight": weight,
        "priority": "high" if weight >= 2.0 else ("medium" if weight >= 1.5 else "normal"),
        "rule": gen[:200] if gen else f"使用 {tag} 类工具/方法时需注意规范操作",
        "problem_hint": first_problem[:120],
        "suggestions": suggestions[:3],
        "checklist": [
            f"❓ 是否已确认 {tag} 相关前置条件？",
            "❓ 是否有已知的同类错误可参考？",
            "❓ 操作前是否已充分理解上下文？",
        ],
    }


# ════════════════════════════════════════════════════════════
#  数据管理
# ════════════════════════════════════════════════════════════

def load_penalty_tracker() -> dict:
    if os.path.exists(PENALTY_FILE):
        with open(PENALTY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"_meta": {"version": "1.0", "last_updated": datetime.now().strftime("%Y-%m-%d")}}


def save_penalty_tracker(data: dict):
    data["_meta"]["last_updated"] = datetime.now().strftime("%Y-%m-%d")
    with open(PENALTY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_injection_config() -> dict:
    if os.path.exists(INJECTION_FILE):
        with open(INJECTION_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"_meta": {"version": "1.0", "last_updated": datetime.now().strftime("%Y-%m-%d")}, "active_injections": []}


def save_injection_config(data: dict):
    data["_meta"]["last_updated"] = datetime.now().strftime("%Y-%m-%d")
    with open(INJECTION_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def append_audit_log(entry: dict):
    with open(AUDIT_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def scan_raw_errors() -> list[dict]:
    """从 inbox/ 中读取 JSON 格式的自动上报错误

    文件命名: YYYY-MM-DD_HHmmss_agentType_Tag.json
    处理完的文件会被移动到 inbox/archived/。
    """
    errors = []
    if not os.path.exists(INBOX_DIR):
        return errors

    os.makedirs(INBOX_ARCHIVE_DIR, exist_ok=True)

    for fname in sorted(os.listdir(INBOX_DIR)):
        if not fname.endswith(".json"):
            continue
        if fname.startswith("_"):
            continue

        fpath = os.path.join(INBOX_DIR, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, Exception):
            import shutil
            shutil.move(fpath, os.path.join(INBOX_ARCHIVE_DIR, fname + ".invalid"))
            continue

        agent_type = data.get("agent_type", "claude")
        tag_raw = data.get("error_tag", "[Unknown]")
        tag = tag_raw.replace("[", "").replace("]", "")
        title = data.get("title", "自动上报错误")
        date_str = fname[:10] if len(fname) >= 10 else "unknown"

        errors.append({
            "date": date_str,
            "tag": tag,
            "title": title,
            "agent_type": agent_type,
            "severity": data.get("severity", 1),
            "text": (
                f"## 标题: {title}\n"
                f"**问题描述**: {data.get('problem', '')}\n"
                f"**根因分析**: {data.get('root_cause', '')}\n"
                f"**解决路径**: {data.get('solution', '')}\n"
                f"**同类推广**: {data.get('generalization', '')}"
            ),
            "sections": {
                "问题描述": data.get("problem", ""),
                "根因分析": data.get("root_cause", ""),
                "解决路径": data.get("solution", ""),
                "同类推广": data.get("generalization", ""),
            },
            "source": "auto-report",
            "raw_file": fname,
        })

    return errors


def archive_processed_errors(errors: list[dict]):
    """将处理过的自动上报文件移动到 inbox/archived/"""
    if not os.path.exists(INBOX_DIR):
        return
    os.makedirs(INBOX_ARCHIVE_DIR, exist_ok=True)

    import shutil
    for e in errors:
        raw_file = e.get("raw_file", "")
        if not raw_file:
            continue
        src = os.path.join(INBOX_DIR, raw_file)
        dst = os.path.join(INBOX_ARCHIVE_DIR, raw_file)
        if os.path.exists(src):
            shutil.move(src, dst)

    count = len([e for e in errors if e.get("raw_file")])
    if count > 0:
        print(f"    [归档] {count} 个自动上报文件已移至 inbox/archived/")


# ════════════════════════════════════════════════════════════
#  惩罚机制
# ════════════════════════════════════════════════════════════

def apply_penalty(tracker: dict, agent_type: str, tag: str, severity: int) -> dict:
    """对 (agent_type × tag) 组合执行惩罚扣分"""
    if agent_type not in tracker:
        tracker[agent_type] = {}
    if tag not in tracker[agent_type]:
        tracker[agent_type][tag] = {
            "points": PENALTY_INIT, "strikes": 0,
            "last_triggered": "", "weight": 1.0, "history": [],
        }

    entry = tracker[agent_type][tag]
    now = datetime.now().strftime("%Y-%m-%d")

    deduct = PENALTY_DEDUCT
    if severity >= 3:
        deduct += PENALTY_DEDUCT_SEVERE - PENALTY_DEDUCT

    entry["points"] = max(0, entry["points"] - deduct)
    entry["strikes"] += 1
    entry["last_triggered"] = now
    entry["history"].append({
        "date": now, "change": f"-{deduct}",
        "points_after": entry["points"], "severity": severity,
    })

    weight_upgraded = False
    new_weight = entry["weight"]
    if entry["points"] <= 0 and entry["strikes"] > 0:
        idx = min(entry["strikes"], len(WEIGHT_TABLE) - 1)
        new_weight = max(entry["weight"], WEIGHT_TABLE[idx])
        if new_weight > entry["weight"]:
            entry["weight"] = new_weight
            weight_upgraded = True
            entry["points"] = PENALTY_INIT

    return {
        "deducted": deduct,
        "points_after": entry["points"],
        "weight_upgraded": weight_upgraded,
        "new_weight": entry["weight"],
        "total_strikes": entry["strikes"],
    }


# ════════════════════════════════════════════════════════════
#  质检门禁 — 迭代修订
# ════════════════════════════════════════════════════════════

def run_quality_gate(error: dict) -> dict:
    """对单条错误执行四方分析 + 质检门禁"""
    agent_type = error["agent_type"]
    tag = error["tag"]
    error_text = error["text"]

    print(f"    [四方分析] 开始质检: {agent_type} × [{tag}] — {error.get('title', '')[:40]}")

    print(f"    [1/4] Qwen 完整性检查...", end="")
    qwen_r = qwen_check_completeness(error_text, tag)
    if qwen_r.get("success"):
        q_score = _extract_score(qwen_r["text"])
        print(f" {q_score:.1f}/10 ({qwen_r['elapsed']:.1f}s)")
    else:
        print(f" ❌ ({qwen_r.get('error','')[:30]})")

    print(f"    [2/4] GLM 质检评分...", end="")
    glm_r = glm_quality_gate(error_text, tag)
    if glm_r.get("success"):
        g_score = glm_r.get("score", 0)
        g_passed = glm_r.get("passed", False)
        print(f" {g_score:.1f}/10 {'✅' if g_passed else '❌'} ({glm_r['elapsed']:.1f}s)")
    else:
        print(f" ❌ ({glm_r.get('error','')[:30]})")

    print(f"    [3/4] Kimi 标签审计...", end="")
    kimi_r = kimi_audit_tagging(error_text, tag)
    if kimi_r.get("success"):
        k_score = _extract_score(kimi_r["text"])
        print(f" {k_score:.1f}/10 ({kimi_r['elapsed']:.1f}s)")
    else:
        print(f" ⚠️ 降级跳过 ({kimi_r.get('error','')[:30]})")

    print(f"    [4/4] DeepSeek 仲裁合成...", end="")
    tracker = load_penalty_tracker()
    penalty_state = tracker.get(agent_type, {}).get(tag, {"points": PENALTY_INIT, "strikes": 0, "weight": 1.0})
    ds_r = ds_synthesize(agent_type, tag, error_text, qwen_r, glm_r, kimi_r, penalty_state)
    print(f" 综合:{ds_r['composite_score']:.1f}/10 {'✅通过' if ds_r['passed'] else '❌不通过'}")

    return {
        "error": error,
        "qwen": qwen_r,
        "glm": glm_r,
        "kimi": kimi_r,
        "deepseek": ds_r,
        "timestamp": datetime.now().isoformat(),
    }


def iterative_refine(result: dict) -> dict:
    """质检门禁迭代修订 — 不通过则修订后重新评分，最多 MAX_ITERATIONS 轮"""
    ds = result["deepseek"]
    if ds["passed"]:
        result["iterations"] = 0
        return result

    print(f"\n    ⚠️ 综合评分 {ds['composite_score']:.1f}/10 < {QUALITY_THRESHOLD}，进入迭代修订...")

    for iteration in range(1, MAX_ITERATIONS + 1):
        print(f"\n    [迭代 {iteration}/{MAX_ITERATIONS}] 修订中...")

        suggestions = []
        for model_name, model_r in [("Qwen", result["qwen"]), ("GLM", result["glm"]), ("Kimi", result["kimi"])]:
            if model_r.get("success"):
                text = model_r["text"]
                for line in text.split("\n"):
                    if "修改建议" in line or "建议" in line or line.strip().startswith("-"):
                        suggestions.append(f"[{model_name}] {line.strip()}")
                    if "改进" in line:
                        suggestions.append(f"[{model_name}] {line.strip()}")

        print(f"      收集到 {len(suggestions)} 条改进建议")

        revision_note = f"\n\n> [修订 v{iteration}] 根据质检反馈改进：{' | '.join(suggestions[:3])}"
        revised_text = result["error"]["text"] + revision_note
        revised_error = dict(result["error"])
        revised_error["text"] = revised_text
        revised_error["_revision"] = iteration

        print(f"      [复查] GLM 重新评分...", end="")
        glm_r = glm_quality_gate(revised_text, revised_error["tag"])
        if glm_r.get("success"):
            g_score = glm_r.get("score", 0)
            g_passed = glm_r.get("passed", False)
            print(f" {g_score:.1f}/10 {'✅通过' if g_passed else '❌不通过'} ({glm_r['elapsed']:.1f}s)")

            result["glm"] = glm_r
            result["deepseek"]["glm_score"] = g_score
            result["deepseek"]["composite_score"] = g_score
            result["deepseek"]["passed"] = g_passed
            result["deepseek"]["comp_issues"] = []
            result["iterations"] = iteration

            if g_passed:
                print(f"      ✅ 第 {iteration} 轮迭代通过！")
                return result

    print(f"    ❌ {MAX_ITERATIONS} 轮迭代后仍未通过，标记为「待人工审查」")
    result["deepseek"]["passed"] = False
    result["deepseek"]["requires_manual_review"] = True
    result["iterations"] = MAX_ITERATIONS
    return result


# ════════════════════════════════════════════════════════════
#  知识注入
# ════════════════════════════════════════════════════════════

def inject_knowledge(result: dict) -> dict:
    """将经过质检门禁的错误分析结果注入 weight_injection.json"""
    error = result["error"]
    ds = result["deepseek"]
    agent_type = error["agent_type"]
    tag = error["tag"]

    injection = load_injection_config()
    now = datetime.now()

    if ds["passed"] and ds.get("prevention_rule"):
        rule = ds["prevention_rule"]
        rule["source"] = f"{error['date']}-{error.get('title', '')[:30]}"
        rule["injected_at"] = now.strftime("%Y-%m-%d %H:%M")
        rule["iteration_count"] = result.get("iterations", 0)
        rule["composite_score"] = ds["composite_score"]

        found = False
        for i, existing in enumerate(injection["active_injections"]):
            if existing.get("agent") == agent_type and existing.get("tag") == tag:
                old_weight = existing.get("weight", 1.0)
                injection["active_injections"][i] = rule
                injection["active_injections"][i]["weight"] = max(old_weight, rule["weight"])
                found = True
                break

        if not found:
            injection["active_injections"].append(rule)

        if "injection_history" not in injection:
            injection["injection_history"] = []
        injection["injection_history"].append({
            "date": now.strftime("%Y-%m-%d %H:%M"),
            "agent": agent_type,
            "tag": tag,
            "score": ds["composite_score"],
            "iterations": result.get("iterations", 0),
            "weight": rule["weight"],
            "source": rule["source"],
        })

        injection["_meta"]["total_rules"] = len(injection["active_injections"])
        injection["_meta"]["last_pipeline_run"] = now.strftime("%Y-%m-%d %H:%M:%S")
        save_injection_config(injection)

        print(f"    [注入] ✅ 规则已注入: {agent_type} × [{tag}] (权重 {rule['weight']}×)")

    return injection


# ════════════════════════════════════════════════════════════
#  状态查看
# ════════════════════════════════════════════════════════════

def show_status():
    """显示当前系统状态"""
    print("=" * 60)
    print("  AEFS — Agent 错误反馈系统 — 状态报告")
    print("=" * 60)

    tracker = load_penalty_tracker()
    injection = load_injection_config()

    print(f"\n📊 惩罚追踪 ({len(tracker) - 1} 个 Agent):")
    for agent_type in sorted(tracker.keys()):
        if agent_type == "_meta":
            continue
        print(f"\n  🤖 {agent_type}:")
        for tag, entry in sorted(tracker[agent_type].items()):
            pts = entry.get("points", "?")
            stk = entry.get("strikes", 0)
            wt = entry.get("weight", 1.0)
            bar = "█" * pts + "░" * max(0, PENALTY_INIT - pts)
            display_tag = tag.replace("[", "").replace("]", "")
            flag = " 🚨权重提升" if wt > 1.0 else ""
            print(f"    [{display_tag}] {bar} {pts}/{PENALTY_INIT} (违规{stk}次, 权重{wt}×){flag}")

    rules = injection.get("active_injections", [])
    print(f"\n📋 活跃注入规则: {len(rules)} 条")
    for r in rules:
        print(f"  [{r.get('agent','?')}×{r.get('tag','?')}] 权重{r.get('weight',1.0)}× — {r.get('rule','')[:60]}...")

    history = injection.get("injection_history", [])
    if history:
        last = history[-1]
        print(f"\n⏱ 上次成功注入: {last.get('date','?')} ({last.get('agent','?')}×{last.get('tag','?')})")

    print(f"\n✅ 系统状态: 正常运行")
    print("=" * 60)


def reset_penalty(agent_type: str, tag: str):
    """重置某 (agent × tag) 组合的分数"""
    tracker = load_penalty_tracker()
    if agent_type not in tracker:
        tracker[agent_type] = {}
    tracker[agent_type][tag] = {
        "points": PENALTY_INIT, "strikes": 0,
        "last_triggered": "", "weight": 1.0,
        "history": [{"date": datetime.now().strftime("%Y-%m-%d"), "change": "reset", "points_after": PENALTY_INIT}],
    }
    save_penalty_tracker(tracker)
    print(f"[Reset] {agent_type} × [{tag}] → 已重置为 {PENALTY_INIT} 分")


# ════════════════════════════════════════════════════════════
#  CLI 主入口
# ════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("  🤖 AEFS — Agent 错误反馈系统 V1.0")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    full_scan = "--full-scan" in args

    if "--status" in args:
        show_status()
        return

    if "--reset" in args:
        idx = args.index("--reset")
        if idx + 2 < len(args):
            reset_penalty(args[idx + 1], args[idx + 2])
            return
        print("[Error] --reset 需要 agent_type 和 tag 两个参数")
        return

    # Step 1: 扫描错误日志
    print("\n[1/5] 扫描错误日志...")
    errors = scan_raw_errors()

    if not errors:
        print("  ℹ️ 没有新错误记录需要处理")
        archive_processed_errors([])
        print("\n✅ 完成")
        return

    print(f"  发现 {len(errors)} 条错误记录 (自动上报)")
    for e in errors:
        print(f"    [{e['tag']}] {e['agent_type']} — {e.get('title', '')[:40]} ({e['date']})")

    if dry_run:
        print("\n[DRY-RUN] 试运行模式，不执行分析")
        return

    # Step 2-5: 逐条处理
    print(f"\n[2/5] 四方分析质检...")
    results = []
    for i, error in enumerate(errors, 1):
        print(f"\n  ── [{i}/{len(errors)}] {error['agent_type']} × [{error['tag']}] ──")
        result = run_quality_gate(error)

        print(f"\n[3/5] 质检门禁（≥{QUALITY_THRESHOLD}）...")
        result = iterative_refine(result)

        print(f"\n[4/5] 惩罚机制...")
        tracker = load_penalty_tracker()
        penalty_result = apply_penalty(tracker, error["agent_type"], error["tag"], error["severity"])
        save_penalty_tracker(tracker)
        result["penalty"] = penalty_result

        pts_after = penalty_result["points_after"]
        bar = "█" * pts_after + "░" * max(0, PENALTY_INIT - pts_after)
        issues = ""
        if penalty_result["weight_upgraded"]:
            issues = f" 🚨 权重提升至 {penalty_result['new_weight']}×"
        print(f"    扣分: -{penalty_result['deducted']} → [{bar}] {pts_after}/{PENALTY_INIT} (第{penalty_result['total_strikes']}次){issues}")

        print(f"\n[5/5] 知识注入...")
        if result["deepseek"]["passed"]:
            injection = inject_knowledge(result)

            if penalty_result["weight_upgraded"]:
                print(f"    [5b/5] 跨 Agent 学习传播...", end="")
                try:
                    from . import propagator as _propagator
                    prop_result = _propagator.propagate(
                        source_agent=error["agent_type"],
                        tag=error["tag"],
                        source_weight=penalty_result["new_weight"],
                        source_rule=result["deepseek"].get("prevention_rule", {}).get("rule", ""),
                    )
                    if prop_result.get("propagated"):
                        print(f" ✅ {prop_result['propagated_count']} 个 Agent 已接收")
                        for tgt in prop_result.get("targets", []):
                            print(f"      → {tgt}")
                    else:
                        print(f" ⏭️ {prop_result.get('reason', '跳过')}")
                except Exception as e:
                    print(f" ⚠️ {str(e)[:60]}")
        else:
            print(f"    ⏭️ 跳过注入（质检未通过，需人工审查）")

        results.append(result)

        append_audit_log({
            "timestamp": result["timestamp"],
            "agent_type": error["agent_type"],
            "tag": error["tag"],
            "title": error.get("title", ""),
            "composite_score": result["deepseek"]["composite_score"],
            "passed": result["deepseek"]["passed"],
            "iterations": result.get("iterations", 0),
            "penalty_deducted": penalty_result["deducted"],
            "penalty_points_after": penalty_result["points_after"],
            "weight": result["deepseek"].get("new_weight", 1.0),
            "requires_review": result["deepseek"].get("requires_manual_review", False),
            "error_source": error.get("source", "manual"),
        })

    if errors:
        archive_processed_errors(errors)

    passed_count = sum(1 for r in results if r["deepseek"]["passed"])
    reviewed = sum(1 for r in results if r["deepseek"].get("requires_manual_review", False))
    total_iterations = sum(r.get("iterations", 0) for r in results)
    avg_score = sum(r["deepseek"]["composite_score"] for r in results) / len(results) if results else 0

    print("\n" + "=" * 60)
    print(f"  📊 本次运行汇总")
    print(f"  ────────────────────────────")
    print(f"  错误总数:       {len(results)}")
    print(f"  质检通过:       {passed_count}/{len(results)}")
    print(f"  待人工审查:     {reviewed}")
    print(f"  平均迭代轮数:   {total_iterations/len(results) if results else 0:.1f}")
    print(f"  平均综合评分:   {avg_score:.2f}/10")
    print(f"  审计日志:       {AUDIT_LOG}")
    print(f"  ────────────────────────────")
    if passed_count > 0:
        print(f"  🎉 {datetime.now().strftime('%Y-%m-%d %H:%M')} 完成")
    else:
        print(f"  ⚠️ 没有错误通过质检，请检查日志")
    print("=" * 60)


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    main()
