# 更新日志

## [1.0.0] — 2026-07-22

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
