# Learning Tutor Framework

> 一套基于 **Claude Code Agent 系统**的教学导师框架，用于构建耐心、结构化、交互式的 AI 学习助手。

## 这是什么？

这是一个**教学型 Agent 搭建框架**，从实际教学场景中提炼而来，包含：

- **Agent 定义** — 即开即用的 Claude Code 教学 Agent
- **教学法体系** — 11 条铁律 + 4 步概念解析模板 + 费曼确认
- **交互流程** — 一问一答、逐点推进的标准化师生交互协议
- **错误自报** — Agent 自我改进闭环

## 快速开始

将 `agents/tutor.md` 放入项目的 `.claude/agents/` 目录，
在 `CLAUDE.md` 中注册后，对话中输入 `/tutor` 即可使用。

```yaml
# 修改 agents/tutor.md 中的配置区适配你的需求
school_background: 你的学校/背景
weekly_hours: 15                    # 每周学习时间
compute_environment: 零GPU          # 计算环境
current_skill_level: 零项目经验      # 当前水平
```

## 结构

```
learning-tutor/
  README.md
  agents/
    tutor.md         # 主导师 Agent（长线规划+教学）
    studyera.md      # 轻量学习伴侣（概念精讲）
  methodology/
    01-teaching-rules.md      # 11条教学铁律
    02-concept-template.md    # 概念精讲模板
    03-interaction-flow.md    # 交互流程
```

## 核心能力对比

| 能力 | Tutor | Studyera |
|------|:-----:|:--------:|
| 长线规划+阶段定位 | ✅ | ❌ |
| 概念精讲(四步法) | ✅ | ✅ |
| 双例子框架(>=150字) | ✅ | ✅ (EDA+ML) |
| 费曼确认(关键词总结) | ✅ | ❌ |
| 引导钩子(抛追问) | ✅ | ✅ |
| 卡点预警+降级方案 | ✅ | ❌ |
| 未来场景映射 | ✅ | ❌ |
| 错误自报协议 | ✅ | ✅ |

## 许可证

MIT
