# 🔔 Finish Remind

  > Claude Code 任务完成提示音 + 邮件通知 Hook

  当 Claude Code 任务执行完毕时，自动播放 Windows 系统提示音，并根据 Claude 的回复内容智能提取本次任务核心主题，发送精简邮件通知到指定邮箱。
  
  ## 功能

  - **🔊 提示音** — 任务完成时播放 Windows `MB_ICONASTERISK` 提示音
  - **📧 邮件通知** — 通过 163.com SMTP 发送任务完成通知
  - **🧠 智能主题提取** — 从 Claude 回复中自动提取本次任务核心主题（无需外部 API）
  - **🛡️ 防抖机制** — 30 秒内不重复发送邮件
  - **🔄 自动重试** — 邮件发送失败自动重试 3 次

  ## 快速开始

  ### 1. 安装

  ```bash
  cd thinking/finish_remind
  pip install -e .

  2. 配置 SMTP 授权码

  $env:CLAUDE_NOTIFY_SMTP_PASS = "你的授权码"

  3. 注册 Stop Hook

  在 .claude/settings.local.json 中添加：

  {
    "hooks": {
      "Stop": "python path/to/finish_remind/src/finish_remind/stop_hook.py"
    }
  }

  项目结构

  finish_remind/
  ├── README.md
  ├── CHANGELOG.md
  ├── LICENSE
  ├── pyproject.toml
  ├── .gitignore
  ├── src/finish_remind/
  │   ├── __init__.py
  │   └── stop_hook.py
  ├── examples/
  │   ├── install.json
  │   └── simple_hook.py
  └── data/

  许可证

  MIT
