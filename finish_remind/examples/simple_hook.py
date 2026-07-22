"""
极简版 Stop Hook — 只有提示音，没有邮件、没有主题提取。

适合只想听到任务完成提示音、不想配置邮箱的用户。

用法：
    1. 将此文件放在任意位置
    2. 在 .claude/settings.local.json 中配置：

    {
      "hooks": {
        "Stop": "python path/to/simple_hook.py"
      }
    }
"""

import json
import sys
import winsound


def main() -> None:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        data = {}

    # 防止无限循环
    if data.get("stop_hook_active"):
        print(json.dumps({"decision": "approve"}))
        return

    # 播放提示音
    winsound.MessageBeep(winsound.MB_ICONASTERISK)

    # 放行
    print(json.dumps({"decision": "approve"}))


if __name__ == "__main__":
    main()
