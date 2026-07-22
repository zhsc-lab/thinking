# 📮 Agent 错误自动上报协议

## 在 feedback/error_message/ 目录下

### 你用这种方式向 pipeline 报告自己的错误

当你（作为 Agent）在执行任务时犯了错误——无论是工具调用失败、理解偏差、还是逻辑错误——**请立即主动报告**，而不是等用户发现后手动记录。

---

## 协议一：手动 JSON 上报（标准版）

```json
{
  "agent_type": "tutor",
  "error_tag": "[ToolCall]",
  "title": "简短的错误标题",
  "problem": "详细描述发生了什么问题",
  "root_cause": "根因分析：为什么会出这个问题",
  "solution": "解决方案：怎么修复的",
  "generalization": "同类推广：以后怎么避免",
  "severity": 2,
  "timestamp": "2026-07-22T10:30:00",
  "source": "self-report"
}
```

### 文件命名规则

```
YYYY-MM-DD_HHmmss_agentType_Tag.json
示例：2026-07-22_103000_tutor_ToolCall.json
```

### 写入路径

```
agent_learning_progress/feedback/error_message/2026-07-22_103000_tutor_ToolCall.json
```

---

## 协议二：终端错误自动上报（TEAL V2.0）

> **自动检测 + 一键上报 + 修复后补充方案**

### 三阶使用模型

| 模式 | 触发方式 | 适用场景 |
|------|---------|---------|
| 🟢 **自动模式** | 工具调用返回错误时 Agent 自动触发 | 日常最省心，无需任何操作 |
| 🟡 **一句话模式** | `teal pip 超时了` | 手动补充上报 |
| 🔵 **修复后补充** | `teal update 文件名.json "解决方案"` | 修复后补全方案 |

---

### 方式 A：Agent 自动检测（推荐，V2.0 新增）

每次工具调用返回后，Agent 自动检查：

```bash
# Bash 命令失败 → 自动上报（无需任何操作）
[exit_code=1, stderr="ModuleNotFoundError: No module named 'torch'"]
→ Agent 自动: teal "ModuleNotFoundError torch 导包失败"
→ pip install torch 修复
→ Agent 自动: teal update 文件 "pip install torch 解决"
```

**检测规则：**

| 信号 | 检测条件 | 自动操作 |
|------|---------|---------|
| Bash exit_code ≠ 0 | 非零退出码 + stderr 非空 | `teal "命令 失败原因"` |
| stderr 含 Traceback | 异常堆栈 | `teal "Python 异常 类型"` |
| 超时/OOM/崩溃 | exit=124/137/139/143 | `teal "严重 问题类型"` |
| Read/Write/Edit 报错 | 工具返回错误 | `teal "操作 失败原因"` |

---

### 方式 B：一句话手动上报

```bash
# 一句话上报，标签和严重度自动推断
teal "Read了一个不存在的文件"
teal "pip install 连接超时"
teal "Git push 被拒绝"
teal "ModuleNotFoundError torch 导包失败"

# 无描述兜底
teal
```

---

### 方式 C：修复后补充方案（V2.0 新增）

```bash
# 修复成功后更新报告，写入实际解决方案
teal update 2026-07-22_223419_claude_Python.json "pip install torch 解决，需要先激活 conda 环境"
```

---

### 完整闭环流程

```
工具调用返回 ──→ 自动检测错误信号
                     │
                     ├─→ ① 自动 TEAL 上报（去重+分类+严重度判定）
                     ├─→ ② 开始修复问题
                     ├─→ ③ 修复成功 → teal update 写入实际解决方案
                     └─→ ④ AEFS 流水线处理
                           ├─ 四方分析 → 惩罚 → 质检
                           └─ 知识注入 → 下次 session 自动避开同类错误
```

报告写入 `error_message/{date}_{time}_{agent}_{tag}.json`，
其中 `source` 标记为 `"terminal-auto-detect"`，修复后变为 `"terminal-auto-detect+fixed"`。

### 自动标签推断规则

脚本根据 stderr 内容和 exit_code 自动匹配以下模式：

| 模式 | 自动标签 | 自动严重度 |
|------|---------|:---------:|
| Traceback / SyntaxError / NameError | [Python] | 2 |
| ModuleNotFoundError / ImportError | [Python] | 2 |
| Git fatal / Merge conflict | [Git] | 2–3 |
| pip / npm / network error | [Env] | 2 |
| Permission denied / EACCES | [Permission] | 3 |
| OOM / Killed / signal 9 | [Env] | 3 |
| exit=124 (超时) | [Env] | 2 |
| exit=137 (OOM) | [Env] | 3 |
| exit=139 (Segfault) | [Env] | 3 |
| No such file / not found | [ToolCall] | 2 |
| 未匹配任何特征 | [ToolCall] | 2 |

### 去重保护

- 同一错误（基于 command + stderr 摘要的 MD5 hash）**5 分钟内不重复上报**
- 同一 session 内相同标签**最多上报 3 次**
- stderr 只有无害警告（DeprecationWarning 等）**直接跳过**

---

## 标签体系

| 标签 | 适用场景 |
|------|---------|
| `[ToolCall]` | 工具调用参数错误/权限问题/格式错误 |
| `[Python]` | Python 脚本/库兼容性/API 调用失败 |
| `[Git]` | Git 操作异常/分支冲突 |
| `[Permission]` | 权限不足/工具拒绝/审批阻塞 |
| `[Communication]` | 理解偏差/用户意图误判 |
| `[Knowledge]` | 知识错误/概念混淆/信息过时 |
| `[Method]` | 方法论/流程失误 |
| `[Env]` | 环境/路径/网络问题 |
| `[Config]` | 配置文件误改/冻结文件误触 |
| `[Model]` | 模型行为异常/响应不稳定 |

---

## 严重度

| 等级 | 适用场景 |
|------|---------|
| 1 | 小问题（卡顿/格式错误/效率低） |
| 2 | 中等（逻辑错误/理解偏差） |
| 3 | 严重（数据丢失/阻断任务/崩溃） |

---

## 触发时机（强制，V2.0 自动检测）

Agent **必须**在以下情况自动检测并上报（不再等待用户发现或提醒）：

| 触发条件 | 检测方式 | 上报方式 | 处理流程 |
|---------|---------|---------|---------|
| Bash exit_code ≠ 0 | 自动查看工具返回值 | 自动 teal | 检测→上报→修复→update |
| Bash stderr 含 Traceback | 自动查看 | 自动 teal | 检测→上报→修复→update |
| 工具调用报错 | 自动查看返回值 | 自动 teal | 同上 |
| 超时/OOM/崩溃 | exit_code 特殊值 | 自动 teal | 同上 |
| 同一操作重试 3 次 | 自检 | 自动 teal | 同上 |
| 逻辑错误/理解偏差 | 自检 | 手动 teal | 手动补充 |

> **核心原则：检测即上报，先上报再修复。** 错误不会因修复成功而被遗忘。
> 修复后执行 `teal update` 补充方案 → AEFS 处理 → 下次自动避开同类错误。
