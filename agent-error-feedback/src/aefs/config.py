"""
AEFS 配置模块
================
集中管理所有常量和路径配置。
"""
import os

# ── 项目根目录探测 ──────────────────────────────────────
# __file__ = .../src/aefs/config.py → PROJECT_ROOT = .../agent-error-feedback/
_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
DATA_DIR = os.path.join(_PROJECT_ROOT, "data")
PROTOCOLS_DIR = os.path.join(_PROJECT_ROOT, "protocols")
INBOX_DIR = os.path.join(_PROJECT_ROOT, "inbox")
INBOX_ARCHIVE_DIR = os.path.join(INBOX_DIR, "archived")
EXAMPLES_DIR = os.path.join(_PROJECT_ROOT, "examples")

# ── 数据文件路径 ─────────────────────────────────────────
PENALTY_FILE = os.path.join(DATA_DIR, "penalty_tracker.json")
INJECTION_FILE = os.path.join(DATA_DIR, "weight_injection.json")
AUDIT_LOG = os.path.join(DATA_DIR, "audit_log.jsonl")

# ── API 配置（环境变量） ────────────────────────────────
QWEN_KEY = os.environ.get("QWEN_API_KEY", "")
GLM_KEY = os.environ.get("GLM_API_KEY", "")
KIMI_KEY = os.environ.get("KIMI_API_KEY", "")
KIMI_URL = os.environ.get("KIMI_BASE_URL", "https://api.moonshot.cn/v1").rstrip("/")

# ── 质检门禁 ────────────────────────────────────────────
QUALITY_THRESHOLD = 9.6      # 通过阈值
MAX_ITERATIONS = 3           # 最大迭代轮次

# ── 惩罚机制 ────────────────────────────────────────────
PENALTY_INIT = 3             # 初始分数
PENALTY_DEDUCT = 1           # 每次扣分
PENALTY_DEDUCT_SEVERE = 2    # 严重错误（severity=3）扣分

# ── 权重阶梯 ────────────────────────────────────────────
# 扣光次数 → 权重倍率
WEIGHT_TABLE = [1.0, 1.5, 2.0, 3.0]

# ── 标签系统 ────────────────────────────────────────────
TAG_SYSTEM = [
    "Config", "ToolCall", "Python", "Git", "Permission",
    "Communication", "Knowledge", "Method", "Env", "Model",
]

# ── 已知 Agent 类型 ─────────────────────────────────────
ALL_AGENTS = ["tutor", "studyera", "explore", "plan", "claude"]

# ── 跨 Agent 传播 — 通用 vs 特有标签 ────────────────────
UNIVERSAL_TAGS = {
    "ToolCall": True,
    "Communication": True,
    "Knowledge": True,
    "Permission": True,
    "Python": True,
    "Git": True,
    "Env": True,
}

AGENT_SPECIFIC_TAGS = {
    "Method": True,
    "Config": True,
    "Model": True,
}


def get_project_root() -> str:
    """返回项目根目录路径"""
    return _PROJECT_ROOT
