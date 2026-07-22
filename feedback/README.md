# Agent 错误反馈系统 (AEFS) 文档

> 自动检测 → 分类上报 → 修复记录 → 知识注入 → 永久闭环

## 目录

- [系统架构](#系统架构)
- [TEAL 终端错误自动检测](#teal-终端错误自动检测)
- [严重度分级](#严重度分级)
- [标签体系](#标签体系)
- [自动检测闭环](#自动检测闭环)
- [使用方法](#使用方法)
- [与 first-cc 项目的关联](#与-first-cc-项目的关联)

---

## 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                     Agent 工作会话                         │
│                                                           │
│  工具调用 ──→ 自动检测错误信号 ──→ TEAL 上报 ──→ 修复    │
│                         ↓                                │
│                   teal update (写入解决方案)               │
│                         ↓                                │
│                  JSON 报告 → error_message/ 目录           │
└──────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│                    AEFS 流水线                             │
│                                                           │
│  scan_raw_errors() ──→ 四方分析 ──→ 惩罚机制 ──→ 质检门禁 │
│                                              ↓            │
│                                       知识注入             │
│                                       预防规则生成          │
└──────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│                 跨 Session 知识继承                         │
│                                                           │
│  下个 session 开始 → 加载历史预防规则                         │
│  遇到同类错误 → 直接调用上次的解决方案                          │
└──────────────────────────────────────────────────────────┘
```

---

## TEAL 终端错误自动检测

**TEAL** = Terminal Error Auto-Detection Layer V1.0

核心脚本：`_terminal_monitor.py` — 纯 Python 3.12+ 标准库，零外部依赖。

### 工作原理

每次工具调用（Bash/Read/Write/Edit）返回后，Agent 自动检查：

1. **exit_code ≠ 0** → Bash 命令失败
2. **stderr 含 Traceback/Error** → Python/系统异常
3. **exit_code 特殊值** (124/137/139/143) → 超时/OOM/崩溃
4. **工具返回错误信息** → Read/Write/Edit 失败

检测到错误后，Agent **在开始修复之前**自动运行 TEAL 上报。

### 错误报告格式

```json
{
  "agent_type": "claude",
  "error_tag": "[Python]",
  "title": "[Auto] ModuleNotFoundError torch 导包失败",
  "problem": "Agent 自动上报:\nModuleNotFoundError torch 导包失败",
  "root_cause": "Python 解释器找不到目标模块：①包未安装 ②虚拟环境未激活 ③包名拼写错误",
  "solution": "pip install torch 或检查包名拼写和虚拟环境激活状态",
  "generalization": "导包前先确认：①环境已激活 ②pip list 检查 ③包名拼写正确",
  "severity": 2,
  "timestamp": "2026-07-22T22:34:19",
  "source": "terminal-auto-detect+fixed",
  "_teal_meta": {
    "exit_code": -1,
    "command_hash": "auto",
    "stderr_len": 0,
    "auto_description": true,
    "updated_at": "2026-07-22T22:34:45",
    "update_count": 1
  }
}
```

---

## 严重度分级

共 **3 个等级**，根据 exit_code 映射 + stderr 关键词 + 描述关键词三重判定。

### 等级定义

| 等级 | 标识 | 名称 | 含义 | 处理优先级 |
|:---:|:---:|------|------|:---------:|
| **3** | 🔴 | **严重** | 进程终止、数据损失、系统不可用 | 立即修复 |
| **2** | 🟡 | **中等** | 操作失败、功能不可用 | 需要处理 |
| **1** | 🟢 | **小问题** | 警告、提示、效率问题 | 知道即可 |

### exit_code 映射表

| exit_code | 含义 | 严重度 | 说明 |
|:---------:|------|:-----:|------|
| 1 | 通用错误 | 🟡 2 | 最常见的错误码 |
| 2 | Shell 内建错误 | 🟡 2 | 语法/参数错误 |
| 124 | 超时 | 🟡 2 | 命令执行超时 |
| 130 | Ctrl+C 打断 | 🟢 1 | 用户手动中断 |
| 134 | SIGABRT | 🔴 3 | 程序主动崩溃 |
| 137 | OOM(SIGKILL) | 🔴 3 | **内存溢出被系统杀掉** |
| 139 | SIGSEGV | 🔴 3 | **指针越界/段错误** |
| 143 | SIGTERM | 🔴 3 | 进程被终止 |
| 255 | Python exit(1) | 🟡 2 | Python 脚本退出 |

### 描述关键词判定

用 `teal "描述"` 时的自动推断规则：

- **等级 3** 🔴：`严重` `崩溃` `数据丢失` `死机` `OOM` `Killed` `segfault` `安全` `泄漏`
- **等级 2** 🟡：`错误` `失败` `报错` `异常` `冲突` `超时` `拒绝` `阻断` `卡住`
- **等级 1** 🟢：`警告` `提示` `小问题` `格式` `不规范` `效率低` `慢`

### 判定优先级

```
① stderr 模式匹配（最精确，可覆盖 exit_code 默认值）
    ↓
② exit_code 映射表（快速）
    ↓
③ 描述关键词自动推断（auto 模式兜底）
    ↓
④ 默认 2（中等）
```

### 典型场景示例

| 场景 | exit_code | stderr 关键词 | 最终严重度 |
|------|:---------:|:------------:|:---------:|
| ModuleNotFoundError | 1 | `ModuleNotFoundError` | 🟡 2 |
| Permission denied | 1 | `Permission denied` | 🔴 3 |
| OOM killed | 137 | `Killed` | 🔴 3 |
| 命令超时 | 124 | `timeout` | 🟡 2 |
| Git 冲突 | 1 | `Merge conflict` | 🔴 3 |
| 连接被拒 | 1 | `Connection refused` | 🟡 2 |
| DeprecationWarning | 0 | `DeprecationWarning` | 🟢 1（自动过滤） |

---

## 标签体系

| 标签 | 适用场景 | 典型错误 |
|------|---------|---------|
| `[Python]` | Python 异常 | ModuleNotFoundError, SyntaxError, TypeError, ValueError |
| `[Git]` | Git 操作 | merge conflict, push rejected, not a git repository |
| `[Env]` | 环境/网络 | pip 失败, OOM, 超时, CUDA 错误, 连接被拒 |
| `[Permission]` | 权限问题 | Permission denied, EACCES, sudo required |
| `[ToolCall]` | 工具操作 | 文件不存在, 无效参数, 命令未找到 |
| `[Communication]` | 沟通误解 | 意图理解偏差, 需多次澄清 |
| `[Knowledge]` | 知识错误 | 概念混淆, 记错 API, 模型理解偏差 |

---

## 自动检测闭环

这是整个系统的核心——Agent 在工作时自动完成以下循环：

```
┌──────────────────────────────────────────────────────────────────┐
│  ①  工具调用                                                     │
│  └─ 例如: python -c "import nonexistent_module"                  │
│                                                                  │
│  ②  Agent 自动检测错误信号                                        │
│  └─ exit_code=1 ?  stderr 含 Traceback ?  工具返回错误?          │
│  └─ 判定标签: [Python]  严重度: 2                                │
│                                                                  │
│  ③  自动 TEAL 上报（在开始修复之前）                               │
│  └─ teal "ModuleNotFoundError xyz 导包失败"                      │
│  └─ 生成 JSON 报告到 error_message/                              │
│                                                                  │
│  ④  修复问题                                                     │
│  └─ pip install xyz / 检查包名 / 切换环境                        │
│                                                                  │
│  ⑤  修复后更新报告 - teal update                                  │
│  └─ teal update 文件名 "pip install xyz 解决"                    │
│  └─ 写入实际解决方案 → solution 字段不再占位                       │
│                                                                  │
│  ⑥  AEFS 流水线处理                                              │
│  └─ 四方分析 → 惩罚 → 质检 → 知识注入 → 预防规则生成               │
│                                                                  │
│  ⑦  跨 Session 继承                                              │
│  └─ 下次 session 开始 → 加载预防规则                               │
│  └─ 遇到同类报错 → 直接调用上次存储的解决方案                       │
│                                                                  │
│  🔄 闭环完成，错误不再被遗忘                                       │
└──────────────────────────────────────────────────────────────────┘
```

---

## 使用方法

### 方式一：自动模式（推荐，最省心）

Agent 在工具调用返回错误时会**自动上报**，你不需要做任何操作。

### 方式二：一句话手动上报

当你在对话中发现错误时，只需输入：

```
!teal pip 超时了
```

或者更简单：

```
!teal
```

### 方式三：修复后补充解决方案

修复成功后，Agent 会自动更新报告，但你也手动补充：

```
teal update 2026-07-22_223419_claude_Python.json "pip install torch 解决"
```

### 方式四：完整参数模式

```bash
# 精确指定退出码和 stderr
python _terminal_monitor.py \
  --exit-code 1 \
  --stderr "ModuleNotFoundError: No module named 'torch'" \
  --cmd "python train.py"

# 管道模式
echo '{"exit_code":1,"stderr":"ModuleNotFoundError","cmd":"python train.py"}' \
  | python _terminal_monitor.py
```

---

## 与 first-cc 项目的关联

| 组件 | 位置 | 说明 |
|------|------|------|
| TEAL 核心 | `feedback/_terminal_monitor.py` | 自动检测+上报引擎 |
| 错误报告存储 | `feedback/error_message/` | JSON 格式 |
| 去重缓存 | `feedback/_terminal_monitor_cache.json` | 5 分钟窗口 + 3 次/标签 |
| 快捷入口 | `teal.cmd` | Windows 一键命令 |
| Agent 协议 | `.claude/agents/tutor.md` | 子 Agent 自动检测规则 |
| Agent 协议 | `.claude/agents/studyera.md` | 子 Agent 自动检测规则 |
| 质检门禁 | `feedback/_quality_gate_step2.py` | ≥9.6/10 执行准入 |
| 四方分析 | `feedback/fourcheck/` | 四个维度错误分析 |
| 错误协议 | `feedback/error_message/_ERROR_REPORT_PROTOCOL.md` | 错误格式标准 |

---

> **设计理念**：错误不应该被遗忘。每次错误都是一次学习机会——自动记录、自动分类、自动提炼预防规则。Agent 在持续工作中不断自我改进。
