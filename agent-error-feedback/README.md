# 🤖 Agent Error Feedback System (AEFS)

> **AI Agent 错误自动收集 → 四方分析 → 惩罚机制 → 质量门禁 → 知识注入闭环**

[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen)](CONTRIBUTING.md)

一个**零外部依赖**的 AI Agent 错误管理框架。当 LLM Agent（如 Claude、GPT 等）在运行中犯错时，自动收集错误、多模型交叉验证、量化扣分、生成预防规则并跨 Agent 传播——让每个犯过的错都不白犯。

> 🌱 本项目是从 [`my-project`](https://github.com/zhsc-lab/my-project) 中独立出来的子模块，原仓库是一个包含番茄钟、深度学习教学计划等功能的综合项目。独立后更聚焦于 Agent 错误管理本身。

---

## 📋 目录

- [一、核心特性](#一核心特性)
- [二、系统架构](#二系统架构)
- [三、快速开始](#三快速开始)
- [四、文件结构](#四文件结构)
- [五、运行指南](#五运行指南)
- [六、四方分析详解](#六四方分析详解)
- [七、惩罚机制](#七惩罚机制)
- [八、质量门禁](#八质量门禁)
- [九、跨 Agent 学习](#九跨-agent-学习)
- [十、配置说明](#十配置说明)
- [十一、最佳实践](#十一最佳实践)
- [十二、更新日志](#十二更新日志)
- [十三、许可证](#十三许可证)

---

## 一、核心特性

| 特性 | 说明 |
|------|------|
| 📮 **Agent 自报错** | Agent 执行出错后自动写 JSON 错误报告，无需人工干预 |
| 🔍 **四方分析** | Qwen(完整性) + GLM(根因质检) + Kimi(标签审计) + DeepSeek(仲裁) 四模型交叉验证 |
| ⚖️ **惩罚机制** | 每 (Agent × 错误类型) 初始 3 分，重复→扣分→扣光→权重提升，最高 3.0× |
| 🧪 **质量门禁** | 四模型加权评分 ≥9.6/10 为通过，不通过自动迭代修订，最多 3 轮 |
| 💉 **知识注入** | 通过质检的预防规则自动写入配置文件，Agent 启动时自读 |
| 🔗 **跨 Agent 学习** | A Agent 犯的错 → 减半权重传播给 B/C/D Agent |
| 🔔 **Hook 自动通知** | 有新预防规则时 PostToolUse Hook 自动通知主会话 |
| 📊 **审计追踪** | 每次运行写入 JSONL 审计日志，可追溯全部历史 |
| 🏭 **零外部依赖** | 纯 Python 3.12+ 标准库，仅 `urllib` 做 API 调用 |
| ⚡ **API 保护** | 三级降级策略：80% 错误走本地逻辑（0 API），15% 走单模型，仅 5% 走全流程 |

---

## 二、系统架构

```
                        ┌─────────────────────────────────────────────┐
                        │              错误来源                       │
                        └──────────┬──────────────────┬──────────────┘
                                   │                  │
                     ┌─────────────▼─────┐    ┌──────▼───────────┐
                     │ 📮 自动上报        │    │ 📝 手动记录       │
                     │ error_message/*.json│   │ YYYY-MM-DD.md    │
                     └──────────┬─────────┘    └────────┬─────────┘
                                │                       │
                                ▼                       ▼
                     ┌───────────────────────────────────────┐
                     │     ① 错误收集层                       │
                     │     scan_raw_errors() + scan_error_logs()│
                     └──────────────────┬────────────────────┘
                                        │
                                        ▼
                     ┌───────────────────────────────────────┐
                     │     ② 四方分析层                       │
                     │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ │
                     │  │Qwen  │ │GLM   │ │Kimi  │ │Deep  │ │
                     │  │完整性│ │根因  │ │标签  │ │Seek  │ │
                     │  │20%   │ │40%   │ │20%   │ │20%   │ │
                     │  └──────┘ └──────┘ └──────┘ └──────┘ │
                     └──────────────────┬────────────────────┘
                                        │
                                        ▼
                     ┌───────────────────────────────────────┐
                     │     ③ 惩罚机制层                       │
                     │     每 (Agent × Tag) = 3 分           │
                     │     重复→扣 1 分→扣光→权重升级        │
                     └──────────────────┬────────────────────┘
                                        │
                                        ▼
                     ┌───────────────────────────────────────┐
                     │     ④ 质检门禁层                       │
                     │     ≥ 9.6 ✅ 通过                      │
                     │     < 9.6 ❌ 迭代修订（最多 3 轮）     │
                     └──────────────────┬────────────────────┘
                                        │
                                        ▼
                     ┌───────────────────────────────────────┐
                     │     ⑤ 知识注入 + 跨 Agent 传播         │
                     │     weight_injection.json ← 预防规则    │
                     │     ↓ 50% 权重 → 其他 Agent             │
                     └───────────────────────────────────────┘
```

### 双源错误收集

```
主通道（新）          📮 自动上报 — Agent 自写 JSON
Agent 执行时出错 ────→ 无需人工干预、实时落盘
                       error_message/          ← 本仓库内
                              │
备用通道（保留）      📝 手动记录 — 你写 markdown
你发现Agent的错 ────→ (你的项目)/           ← 在你的主项目中
                       YYYY-MM-DD.md
                              │
                              ▼
                       pipeline 读取两个源，合并处理
                       自动上报优先
                       处理完自动归档到 _archived/
```

---

## 三、快速开始

### 安装

```bash
# 本项目在 thinking 仓库的 agent-error-feedback/ 子目录下
git clone git@github.com:zhsc-lab/thinking.git
cd thinking/agent-error-feedback
```

### 环境变量（如需调用云端模型）

```bash
# 至少配置一个 API Key 即可运行，其余会自动降级
export QWEN_API_KEY="sk-xxx"          # Qwen 完整性检查
export GLM_API_KEY="xxx"              # GLM 根因质检（建议必配）
export KIMI_API_KEY="sk-xxx"         # Kimi 标签审计
```

如果没有任何 API Key，系统自动运行**纯本地模式**（Level 0），使用本地逻辑分析错误。

### 运行一次全量扫描

```bash
python -m src.aefs.pipeline --full-scan
```

### 查看状态

```bash
python -m src.aefs.pipeline --status
```

### 查看某个 Agent 的预防规则

```bash
python -m src.aefs.hook_engine tutor      # 查看 tutor 的错题本
python -m src.aefs.hook_engine studyera   # 查看 studyera 的错题本
python -m src.aefs.hook_engine --all      # 查看所有 Agent
```

---

## 四、文件结构

```
.
├── README.md                          ← 本文件（含更新日志）
├── LICENSE                            ← MIT 许可证
├── pyproject.toml                     ← 项目元数据
│
├── src/aefs/                          ← 🔥 核心 Python 包
│   ├── __init__.py                    ← 包入口
│   ├── pipeline.py                    ← 主流水线（四方分析+惩罚+质检+注入）
│   ├── hook_engine.py                 ← Agent 错题本生成器
│   ├── propagator.py                  ← 跨 Agent 学习传播器
│   └── config.py                      ← 配置常量
│
├── data/                              ← 运行时数据（自动生成）
│   ├── weight_injection.json          ← 预防规则数据库
│   ├── penalty_tracker.json           ← 惩罚扣分追踪
│   └── audit_log.jsonl                ← 流水线审计日志
│
├── inbox/                             ← Agent 自报错误入口
│   └── archived/                      ← 已处理的错误报告
│
├── protocols/                         ← 协议文档
│   └── error-report.md                ← Agent 自报错误协议
│
├── examples/                          ← 使用示例
│   └── quickstart.sh
│
└── tests/                             ← 测试
    └── __init__.py
```

---

## 五、运行指南

### 5.1 核心流水线

```bash
# 增量运行（只处理新增错误）
python -m src.aefs.pipeline

# 全量扫描（重新分析所有日志）
python -m src.aefs.pipeline --full-scan

# 试运行（只检查不修改）
python -m src.aefs.pipeline --dry-run

# 查看状态
python -m src.aefs.pipeline --status

# 重置某 Agent 的某错误类型分数
python -m src.aefs.pipeline --reset tutor ToolCall
```

### 5.2 Hook 引擎

```bash
# 查看特定 Agent 的错题本
python -m src.aefs.hook_engine tutor

# 查看所有 Agent
python -m src.aefs.hook_engine --all

# 仅供 Hook 系统调用（静默检查）
python -m src.aefs.hook_engine --check
python -m src.aefs.hook_engine --notify
```

### 5.3 跨 Agent 传播

```bash
# 手动触发传播
python -m src.aefs.propagator --upgrade tutor ToolCall 1.5

# 审查当前跨源规则
python -m src.aefs.propagator --review
```

### 5.4 典型工作流

```
每日流程：
  1. python -m src.aefs.pipeline                # 收集今天的错误
  2. python -m src.aefs.hook_engine --all       # 查看各 Agent 新增规则
  
Agent 启动时：
  1. python -m src.aefs.hook_engine tutor        # 自读错题本
  2. 逐条确认预防规则后开始工作
  
常规运维：
  1. python -m src.aefs.pipeline --status        # 查看各 Agent 扣分情况
  2. python -m src.aefs.pipeline --full-scan     # 周末全量扫描
```

---

## 六、四方分析详解

### 6.1 模型角色映射

| 视角 | 模型 | 权重 | 职责 | 评分维度 |
|------|------|------|------|---------|
| 🔵 **Qwen** | `qwen-plus` | 20% | 错误记录完整性检查 | 描述清晰度、解决方案完整性、根因深度、泛化价值 |
| 🟢 **GLM** | `glm-4-flash` | 40% | 根因正确性质检（主质检） | 根因准确性、修复正确性、安全性、完整性 |
| 🔴 **Kimi** | `kimi-k2.6` | 20% | 标签与分类审计 | 标签准确性、跨类关联度、检索效率 |
| 🟣 **DeepSeek** | 主控合成 | 20% | 仲裁与权重建议 | 综合评分、权重建议合理性、仲裁公正性 |

### 6.2 复合评分公式

```
综合评分 = Qwen_score × 0.2 + GLM_score × 0.4 + Kimi_score × 0.2 + DS_score × 0.2
```

- GLM 权重最高（40%）——反映根因质检的核心地位
- 模型不可用时自动重分配权重给可用模型
- 单模型可用时直接取该模型评分

### 6.3 API 三级降级策略

| 级别 | 调用模型数 | 适用场景 | 占比 |
|------|-----------|---------|------|
| Level 0 | 0（纯本地） | 简单格式错误、描述性错误 | 80% |
| Level 1 | 1（仅 GLM） | 有明确根因但需验证 | 15% |
| Level 2 | 3-4（全流程） | 复杂错误、首次出现、高风险 | 5% |

---

## 七、惩罚机制

### 7.1 扣分规则

每个 `(Agent × 错误类型)` 组合初始拥有 **3 分**。

| 场景 | 扣分 | 说明 |
|------|------|------|
| 首次出现该类型错误 | **不扣分** | 第 1 次属于学习成本 |
| 同一组合再次出现 | **扣 1 分** | 3→2→1→0 |
| 严重性 3 的错误 | **额外扣 1 分** | 严重错误加倍惩罚 |
| 权重注入后重置 | **重置为 3 分** | 重新计数 |

### 7.2 权重提升

| 扣光次数 | 权重倍率 | 预防规则强度 |
|----------|---------|-------------|
| 第 1 次 | **1.5×** | 提示中增加 1 条预防规则 |
| 第 2 次 | **2.0×** | 规则前置到提示词前 1/3 |
| 第 3 次+ | **3.0×** | 加粗 + 前置 + 检查清单 |

### 7.3 综合影响力公式

```
影响力 = 基础权重 × 时间衰减 × 频率乘数 × 跨Agent乘数 × 严重度乘数
        ↑1.0-3.0    ↑0.5-1.5    ↑1.0-2.0     ↑1.0-1.5     ↑1.0-1.5
```

---

## 八、质量门禁

### 8.1 评分流程

```
输入：错误记录分析结果
  ├── Step 1: Qwen 完整性评分 → 输出完整性子分（20%）
  ├── Step 2: GLM 根因质检 → 输出根因子分（40%）
  ├── Step 3: Kimi 标签审计 → 输出标签子分（20%）
  └── Step 4: DeepSeek 合成 → 权重建议 + 综合评分（20%）
       │
       ▼
  综合评分 ≥ 9.6？───✅──→ 通过 → 知识注入
       │
       ❌ < 9.6
       ▼
  迭代修订（最多 3 轮）
       │
       ▼
  3 轮后仍 < 9.6 → 标记「待人工审查」
```

### 8.2 迭代修订机制

```
轮次 1: 收集四模型改进建议 → 修订 → GLM 复查
轮次 2: 收集改进建议 → 修订 → GLM 复查
轮次 3: 收集改进建议 → 修订 → GLM 复查
结果: 通过 ✅ 或 待人工审查 ⚠️
```

---

## 九、跨 Agent 学习

### 9.1 传播规则

| 规则 | 说明 |
|------|------|
| 仅传播「通用型」标签 | ToolCall、Communication、Knowledge、Permission、Python、Git、Env |
| 不传播「Agent 特有」标签 | Method、Config、Model |
| 传播权重减半 | `prop_weight = max(0.5, source_weight × 0.5)` |
| 不降级覆盖 | 传播权重大于现有才更新，避免降级 |
| 每 Agent 最多接收 | 不限，但同标签只保留最高权重 |

### 9.2 通用 vs 特有标签

```
通用标签（跨Agent传播）      Agent特有标签（不传播）
───────────────────────      ───────────────────────
[ToolCall] 工具调用规范       [Method]    方法论
[Communication] 沟通理解      [Config]    配置修改
[Knowledge] 知识错误          [Model]     模型行为
[Permission] 权限问题
[Python] Python 错误
[Git] Git 操作异常
[Env] 环境/网络问题
```

---

## 十、配置说明

### 10.1 常量配置（`src/aefs/config.py`）

```python
QUALITY_THRESHOLD = 9.6       # 质检通过阈值
MAX_ITERATIONS = 3             # 最大迭代轮次
PENALTY_INIT = 3               # 初始分数
PENALTY_DEDUCT = 1             # 每次扣分
PENALTY_DEDUCT_SEVERE = 2      # 严重错误扣分
WEIGHT_TABLE = [1.0, 1.5, 2.0, 3.0]  # 权重阶梯
```

### 10.2 Agent 标签系统

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

## 十一、最佳实践

### 11.1 给 Agent 配置自动错题本

在 Agent 定义文件（如 `tutor.md`）的开头添加：

```markdown
## ⚠️ 错题本（自动加载）

1. 运行以下命令查看你的历史犯规记录：
   ```bash
   python path/to/agent-error-feedback/src/aefs/hook_engine.py tutor
   ```
2. 高优先级规则必须逐条确认后再开始工作
```

> 💡 如果 AEFS 安装在项目子目录（而非独立仓库），路径改为相对路径，如 `agent_learning_progress/feedback/src/aefs/hook_engine.py`。

### 11.2 配置 PostToolUse Hook

在你的 Claude Code 项目中添加 `settings.local.json`：

```json
{
  "PostToolUse": {
    "command": "python path/to/agent-error-feedback/src/aefs/hook_engine.py --notify",
    "timeout": 15000,
    "async": true
  }
}
```

这样每次 Agent 工具调用后自动检查是否有新预防规则。

### 11.3 将 AEFS 作为子目录集成到现有项目

如果你不想 clone 独立仓库，也可以把整个 `agent-error-feedback` 目录复制到你的项目中：

```
your-project/
├── agent-error-feedback/           ← 放在这里
│   ├── src/aefs/pipeline.py
│   ├── src/aefs/hook_engine.py
│   └── ...
├── your-agent-definitions/
└── ...
```

所有脚本通过 `python -m agent-error-feedback.src.aefs.pipeline` 运行。

### 11.4 Agent 自报错误协议

Agent 执行出错时应立即写 JSON 到 `inbox/`：

```json
{
  "agent_type": "tutor",
  "error_tag": "[ToolCall]",
  "title": "简短的错误标题",
  "problem": "详细描述发生了什么问题",
  "root_cause": "根因分析",
  "solution": "怎么修复的",
  "generalization": "同类推广",
  "severity": 2,
  "timestamp": "2026-07-22T10:30:00",
  "source": "self-report"
}
```

文件命名：`YYYY-MM-DD_HHmmss_agentType_Tag.json`

触发条件：
- 工具调用报错
- 逻辑推导方向错误
- 同一问题被用户反复澄清 2 次以上
- 同一操作重试 3 次才成功

---

## 十二、更新日志

### [2.0.0] — 2026-07-22

#### 🚀 新增

**TEAL V2.0 — 终端错误自动检测层**
- **新增 `update_report()`**：修复后补充实际解决方案到已上报的错误报告
- **新增 `--update` CLI**：`python _terminal_monitor.py --update 文件名.json "解决方案"`
- **修复后标记**：`source` 字段从 `terminal-auto-detect` 变为 `+fixed`
- **修改历史追踪**：`_teal_meta.updated_at` / `update_count` 记录更新版本
- **`teal.cmd` 增强**：支持 `teal update 文件.json "方案"` 子命令

**Agent 自动错误检测协议 V2.0**
- **从手动自报升级为自动检测上报**：Agent 每次工具调用后自动检查 exit_code/stderr/工具错误
- **检测即上报**：错误出现后**先 teal 上报再修复**，确保错误不被遗忘
- **修复后更新**：`teal update` 写入实际解决方案，供 AEFS 提取生成预防规则
- **完整闭环**：上报 → 修复 → update → AEFS 处理 → 跨 session 知识继承

**严重度判定体系完整文档化**
- **三级划分**：1(小问题) / 2(中等) / 3(严重)
- **判定优先级**：stderr 模式匹配 → exit_code 映射 → 描述关键词 → 默认 2
- **exit_code 映射表正式化**：124(超时)=2、130(Ctrl+C)=1、137(OOM)=3、139(Segfault)=3 等
- **描述关键词表**：每个严重度对应触发词列表（如 OOM/Killed→3，超时/冲突→2）

#### 🔧 优化
- Agent 不再依赖用户发现错误——自动检测，立即上报
- 简化使用：`teal`（无描述兜底）/ `teal pip 超时`（一句话）/ `teal update`（修复后补充）
- 5 分钟去重窗口 + 每标签最多 3 次/session，无害警告自动过滤

---

### [1.0.0] — 2026-07-21

#### 🚀 新增

- **核心流水线** `src/aefs/pipeline.py`：五步完整闭环（扫描→四方分析→惩罚→质检→注入）
- **四方分析模块**：Qwen 完整性检查 + GLM 根因质检 + Kimi 标签审计 + DeepSeek 仲裁合成
- **惩罚机制**：3 分制递进扣分 + 权重阶梯(1.0×/1.5×/2.0×/3.0×)
- **质量门禁**：≥9.6 阈值 + 最多 3 轮迭代修订
- **知识注入**：自动生成预防规则并写入 `data/weight_injection.json`
- **跨 Agent 学习**：`src/aefs/propagator.py` — 通用标签 50% 权重传播
- **Hook 引擎**：`src/aefs/hook_engine.py` — 子 Agent 自读错题本 + PostToolUse 通知
- **双源错误收集**：自动上报 JSON + 手动记录 Markdown 双通道
- **审计日志**：每次运行的完整流水线记录写入 `data/audit_log.jsonl`
- **三级 API 降级**：Level 0/1/2 自适应，保护 API 配额

#### 🔧 优化

- 零外部依赖，仅使用 Python 3.12+ 标准库
- 模型不可用时自动降级，不阻塞流程
- 处理过的文件自动归档到 `inbox/archived/`

---

## 十三、许可证

[MIT License](LICENSE) — 自由使用、修改、分发，需保留版权声明。

---

<div align="center">
  <sub>Built with ❤️ for AI Agent reliability engineering</sub>
</div>
