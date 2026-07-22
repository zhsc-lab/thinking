# 更新日志

  ## [2.0.0] — 2026-07-22

  ### 🎉 首次发布为独立项目

  从 `my-project` 仓库中抽取 `stop_notify` hook 功能，重构为标准 Python 开源项目。

  ### ✨ 核心功能

  - 任务完成时播放 Windows 系统提示音
  - 通过 163.com SMTP 发送邮件通知
  - 智能主题提取引擎（R0–R8 九种正则模式）
  - 30 秒邮件防抖机制
  - 发送失败自动重试 3 次
  - 防止 Stop hook 无限循环的 `stop_hook_active` 开关