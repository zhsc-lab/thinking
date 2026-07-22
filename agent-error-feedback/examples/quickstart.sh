#!/usr/bin/env bash
# AEFS 快速上手示例
set -e

echo "=== AEFS 快速上手 ==="
echo ""

# 1. 查看状态
echo "1. 查看当前状态:"
python -m src.aefs.pipeline --status
echo ""

# 2. 查看某个 Agent 的错题本
echo "2. 查看 tutor 的错题本:"
python -m src.aefs.hook_engine tutor
echo ""

# 3. 将错误报告放入 inbox/（供 pipeline 处理）
echo "3. Agent 自报错误示例:"
echo '{
  "agent_type": "tutor",
  "error_tag": "[ToolCall]",
  "title": "示例错误",
  "problem": "Read 文件时路径错误",
  "root_cause": "使用了相对路径而非绝对路径",
  "solution": "改用 os.path.abspath() 获取绝对路径",
  "generalization": "所有文件操作前先检查路径是否为绝对路径",
  "severity": 2,
  "source": "self-report"
}' > inbox/example-report.json
echo "   -> 已写入 inbox/example-report.json"
echo ""

# 4. 运行 pipeline 处理
echo "4. 运行 pipeline 处理错误:"
python -m src.aefs.pipeline
