# 更新日志

## [2.0.0] — 2026-07-22

### 🚀 新增

#### TEAL V2.0 — 终端错误自动检测层
- **新增 `update_report()`**：修复后补充实际解决方案到已上报的错误报告
- **新增 `--update` CLI**：`python _terminal_monitor.py --update 文件名.json "解决方案"`
- **修复后标记**：`source` 字段从 `terminal-auto-detect` 变为 `+fixed`
- **修改历史追踪**：`_teal_meta.updated_at` / `update_count` 记录更新版本
- **`teal.cmd` 增强**：支持 `teal update 文件.json "方案"` 子命令

#### Agent 自动错误检测协议 V2.0
- **从手动自报升级为自动检测上报**：Agent 每次工具调用后自动检查 exit_code/stderr/工具错误
- **检测即上报**：错误出现后**先 teal 上报再修复**，确保错误不被遗忘
- **修复后更新**：`teal update` 写入实际解决方案，供 AEFS 提取生成预防规则
- **完整闭环**：上报 → 修复 → update → AEFS 处理 → 跨 session 知识继承

#### 严重度判定体系完整文档化
- **三级划分**：1(小问题) / 2(中等) / 3(严重)
- **判定优先级**：stderr 模式匹配 → exit_code 映射 → 描述关键词 → 默认 2
- **exit_code 映射表正式化**：124(超时)=2、130(Ctrl+C)=1、137(OOM)=3、139(Segfault)=3 等
- **描述关键词表**：每个严重度对应触发词列表（如 OOM/Killed→3，超时/冲突→2）

### 🔧 优化
- Agent 不再依赖用户发现错误——自动检测，立即上报
- 简化使用：`teal`（无描述兜底）/ `teal pip 超时`（一句话）/ `teal update`（修复后补充）
- 5 分钟去重窗口 + 每标签最多 3 次/session，无害警告自动过滤

---

## [1.0.0] — 2026-07-21

### 🚀 新增
- **核心流水线** `src/aefs/pipeline.py`：五步完整闭环（扫描→四方分析→惩罚→质检→注入）
- **四方分析模块**：Qwen 完整性检查 + GLM 根因质检 + Kimi 标签审计 + DeepSeek 仲裁合成
- **惩罚机制**：3 分制递进扣分 + 权重阶梯(1.0×/1.5×/2.0×/3.0×)
- **质量门禁**：≥9.6 阈值 + 最多 3 轮迭代修订
- **知识注入**：自动生成预防规则并写入 `data/weight_injection.json`
- **跨 Agent 学习**：`src/aefs/propagator.py` — 通用标签 50% 权重传播
- **Hook 引擎**：`src/aefs/hook_engine.py` — 子 Agent 自读错题本 + PostToolUse 通知
- **双源错误收集**：自动上报 JSON（inbox/） + 手动记录 Markdown 双通道
- **审计日志**：每次运行的完整流水线记录写入 `data/audit_log.jsonl`
- **三级 API 降级**：Level 0/1/2 自适应，保护 API 配额

### 🔧 优化
- 零外部依赖，仅使用 Python 3.12+ 标准库
- 模型不可用时自动降级，不阻塞流程
- 处理过的文件自动归档到 `inbox/archived/`
