# 🧠 thinking

> zhsc-lab 的知识碎片合集

这个仓库存放多个独立的小项目/模块，每个都在自己的子目录中。

## 📦 项目列表

| 目录 | 说明 | 技术栈 |
|------|------|--------|
| [agent-error-feedback](./agent-error-feedback/) | 🤖 AI Agent 错误自动收集 → 四方分析 → 惩罚机制 → 质检门禁 → 知识注入闭环 | Python 3.12+ |
| [finish_remind](./finish_remind/) | 🔔 Claude Code 任务完成提示音 + 邮件通知 Hook | Python 3.10+ |
| [protocols/error-report.md](./agent-error-feedback/protocols/error-report.md) | 📋 错误上报协议 V2.0（自动检测 + 一句话上报 + 严重度分级） | Markdown |

## 使用方式

每个项目在各自目录内有独立的 `README.md` 和 `LICENSE`，clone 后进入对应目录即可：

```bash
git clone git@github.com:zhsc-lab/thinking.git
cd thinking/agent-error-feedback
```

---

<sub>📅 2026-07 · 持续更新</sub>
