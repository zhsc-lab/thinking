# 📮 Agent 错误自动上报协议 V2.0

## 三阶使用模型

| 模式 | 触发方式 | 适用场景 |
|------|---------|---------|
| 🟢 **自动模式** | Agent 每次工具调用后自动检测 | 日常最省心，无需任何操作 |
| 🟡 **一句话模式** | 手动输入 `teal "错误描述"` | 手动补充上报 |
| 🔵 **修复后补充** | `teal update 文件.json "解决方案"` | 修复后补全方案，AEFS 提取更精确 |

---

## 协议一：Agent 自动检测上报（V2.0 新增，推荐）

### 自动检测规则

每次工具调用返回后，Agent 自动检查以下信号：

| 信号来源 | 检测条件 | 自动操作 |
|---------|---------|---------|
| Bash exit_code ≠ 0 | 非零退出码 + stderr 非空且非无害 | 自动 `teal "命令 失败原因"` |
| Bash stderr 含 Traceback | 异常堆栈（ModuleNotFound 等） | 自动 `teal "Python 异常 类型"` |
| Bash 超时/OOM/崩溃 | exit_code=124/137/139/143 | 自动 `teal "严重 问题类型"` |
| Read/Write/Edit 报错 | 工具返回错误信息 | 自动 `teal "操作 失败原因"` |
| 同一操作重试 3 次才成功 | 技术性失败 | 仍须上报 |

### 执行规则

```
① 检测即上报：错误出现 → 立即 teal → 再动手修复
② 修复后更新：修复成功 → teal update 文件.json "实际解决方案"
③ 不跳过不重复：TEAL 自动去重（5min 窗口 + 3 次/标签上限），无害警告自动过滤
④ 跨 session 继承：session 开始加载历史预防规则，遇到同类错误直接调用上次方案
```

### 完整闭环

```
工具调用返回 ──→ 自动检测错误信号
                     │
                     ├─→ ① 自动 teal 上报（去重+分类+严重度判定）
                     ├─→ ② 修复问题
                     ├─→ ③ teal update 写入实际解决方案
                     └─→ ④ AEFS 流水线处理 → 下次 session 自动避开同类错误
```

---

## 协议二：终端错误一键上报（TEAL）

使用 `teal.cmd` 一句话上报，标签和严重度自动推断。

### 方式 A：一句话手动上报

```bash
teal "Read了一个不存在的文件"
teal "pip install 连接超时"
teal "Git push 被拒绝"
teal                              # 无描述兜底
```

### 方式 B：修复后补充方案

```bash
teal update 2026-07-22_223419_claude_Python.json "pip install torch 解决"
```

### 方式 C：精确上报（完整参数）

```bash
python agent-error-feedback/src/aefs/_terminal_monitor.py \
  --exit-code 1 \
  --stderr "ModuleNotFoundError: No module named 'torch'" \
  --cmd "python train.py"
```

---

## 协议三：手动写 JSON 文件

适用于无法通过命令行上报的场景：

```json
{
  "agent_type": "tutor",
  "error_tag": "[ToolCall]",
  "title": "错误标题",
  "problem": "问题描述",
  "root_cause": "根因分析",
  "solution": "解决方案",
  "generalization": "同类推广",
  "severity": 2,
  "timestamp": "2026-07-22T10:30:00",
  "source": "self-report"
}
```

文件命名：`YYYY-MM-DD_HHmmss_agentType_Tag.json`
写入路径：`agent-error-feedback/inbox/`

---

## 标签体系

| 标签 | 适用场景 | 典型错误 |
|------|---------|---------|
| `[Python]` | Python 异常 | ModuleNotFoundError, SyntaxError, TypeError |
| `[Git]` | Git 操作 | merge conflict, push rejected |
| `[Env]` | 环境/网络 | pip 失败, OOM, 超时, CUDA 错误 |
| `[Permission]` | 权限问题 | Permission denied, EACCES |
| `[ToolCall]` | 工具操作 | 文件不存在, 命令未找到 |
| `[Communication]` | 沟通误解 | 意图理解偏差 |
| `[Knowledge]` | 知识错误 | 概念混淆, API 记错 |
| `[Method]` | 方法论 | 流程失误 |
| `[Config]` | 配置错误 | 冻结文件误触 |
| `[Model]` | 模型异常 | 响应不稳定 |

---

## 严重度体系

### 三级定义

| 等级 | 标识 | 含义 | 处理优先级 |
|:---:|:---:|------|:---------:|
| **3** | 🔴 严重 | 进程终止、数据损失、系统不可用 | 立即修复 |
| **2** | 🟡 中等 | 操作失败、功能不可用 | 需要处理 |
| **1** | 🟢 小问题 | 警告、提示、效率问题 | 知道即可 |

### exit_code → 严重度映射

| exit_code | 含义 | 严重度 |
|:---------:|------|:-----:|
| 1 | 通用错误 | 🟡 2 |
| 2 | Shell 内建错误 | 🟡 2 |
| 124 | 超时 | 🟡 2 |
| 130 | Ctrl+C 打断 | 🟢 1 |
| 134 | SIGABRT（程序崩溃） | 🔴 3 |
| 137 | OOM kill（内存溢出被系统杀） | 🔴 3 |
| 139 | Segfault（指针越界） | 🔴 3 |
| 143 | SIGTERM（进程终止） | 🔴 3 |
| 255 | Python sys.exit() | 🟡 2 |

### 描述关键词判定

用 `teal "..."` 时的自动推断：

- **等级 3**：`严重` `崩溃` `OOM` `Killed` `segfault` `数据丢失` `安全` `泄漏`
- **等级 2**：`错误` `失败` `报错` `异常` `冲突` `超时` `拒绝` `阻断` `卡住`
- **等级 1**：`警告` `提示` `小问题` `格式` `不规范` `效率低` `慢`

### 判定优先级

```
① stderr 模式匹配（最精确，可覆盖 exit_code 默认值）
    ↓
② exit_code 映射表
    ↓
③ 描述关键词自动推断（auto 模式兜底）
    ↓
④ 默认 2（中等）
```

---

## 触发时机（V2.0 自动检测）

Agent **必须**在以下情况自动检测并上报：

| 触发条件 | 检测方式 | 上报方式 |
|---------|---------|---------|
| Bash exit_code ≠ 0 | 自动查看工具返回值 | 自动 teal |
| Bash stderr 含 Traceback | 自动查看 | 自动 teal |
| 工具调用报错 | 自动查看返回值 | 自动 teal |
| 超时/OOM/崩溃 | exit_code 特殊值 | 自动 teal |
| 同一操作重试 3 次 | 自检 | 自动 teal |
| 逻辑错误/理解偏差 | 自检 | 手动 teal |

> **核心原则：检测即上报，先上报再修复。** 错误不会因修复成功而被遗忘。
> 修复后执行 `teal update` 补充方案 → AEFS 处理 → 下次自动避开同类错误。
