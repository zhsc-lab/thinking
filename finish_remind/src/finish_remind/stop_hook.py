"""
Claude Code Stop Hook — 任务完成提示音 + 精简邮件通知。

由 .claude/settings.local.json 中的 hooks.Stop 触发。
从 DeepSeek 回复内容中智能提取本次任务核心主题，无需外部 API。
"""

import json
import os
import re
import smtplib
import sys
import winsound
from datetime import datetime
from email.header import Header
from email.mime.text import MIMEText


SMTP_HOST = "smtp.163.com"
SMTP_PORT = 465
SMTP_USER = "zhsc1622@163.com"
SMTP_PASS = os.environ.get("CLAUDE_NOTIFY_SMTP_PASS", "BYUSTtP2DMcYKSRV")
TO_ADDR = "zhsc1622@163.com"

EMAIL_ENABLED = bool(SMTP_PASS)


def play_sound() -> None:
    try:
        winsound.MessageBeep(winsound.MB_ICONASTERISK)
    except Exception:
        pass


def log(msg: str) -> None:
    try:
        log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
        log_path = os.path.join(log_dir, "hook.log")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{now}] {msg}\n")
    except Exception:
        pass


def _strip_markdown(text: str) -> str:
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'`[^`]+`', '', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'!\[([^\]]*)\]\([^)]+\)', '', text)
    text = re.sub(r'\|[\s-]+\|[\s-]+\|', '', text)
    text = re.sub(r'[*~#>`|]', '', text)  # 不删 _，避免 stop_notify → stopnotify
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


_BAD_TOPIC_PREFIXES = ('一个', '这个', '那个', '这些', '那些', '一些', '一种', '一下', '一次', '一遍')
_FILE_EXTS = ('.py', '.js', '.ts', '.json', '.md', '.txt', '.csv', '.png', '.jpg', '.yaml', '.yml', '.toml')


def _is_good_name(name: str) -> bool:
    name = name.strip()
    if len(name) < 2:
        return False
    if name.startswith(_BAD_TOPIC_PREFIXES):
        return False
    if name in ('搞定了', '完成了', '欧克', '好的', '嗯', '可以', '没问题', '行', '我来', '来'):
        return False
    return True


def _clean_name(name: str) -> str:
    name = name.strip()
    for ext in _FILE_EXTS:
        if name.endswith(ext):
            name = name[:-len(ext)]
            break
    name = name.strip()
    name = re.sub(r'[的\.\+\\\/\(\)（），,、。:：;；!！?？\s]+$', '', name)
    name = re.sub(r'\s+(吧|了|哦|啊|呢|吗|哈|呀|的|呗|嘛|么)$', '', name)
    return name.strip()


def _find_topic(text: str) -> str | None:
    if not text:
        return None
    clean = _strip_markdown(text)
    if not clean:
        return None

    log(f"FIND: clean[:160] = {clean[:160]!r}")

    # R0: 数字开头的项目名（99乘法表、408项目等）
    m = re.search(r'(?:^|[，,。.!！?？、；:：\s])(\d+[一-鿿A-Za-z0-9_\-]{1,14})', clean)
    if m:
        name = m.group(1)
        if _is_good_name(name) and 2 <= len(name) <= 16:
            log(f"FIND: R0 hit -> {name}")
            return name

    # R1: "X项目/功能/模块..."
    for sfx in ['项目', '功能', '模块', '系统', '工具', '脚本',
                '文件', '代码', '方案', '任务', '配置', '接口',
                '仓库', '分支', '版本']:
        idx = 0
        while True:
            idx = clean.find(sfx, idx)
            if idx < 1:
                break
            end = idx
            start = end
            for i in range(end - 1, max(-1, end - 9), -1):
                if i >= 0 and re.match(r'[一-鿿A-Za-z0-9_\-\.\+]', clean[i]):
                    start = i
                else:
                    break
            name = clean[start:end]
            if _is_good_name(name) and 2 <= len(name) <= 6:
                log(f"FIND: R1 hit -> {name}")
                return name
            idx = end + 1

    # lookahead 工具函数
    _la = (r'(?=[，,。.!！?？、；:：\n\r\s\)）的之是了和与或以及并但而'
           r'因为如果虽然但是对于以被把让将正在已经通过经过关于'
           r'针对在由从到向往按照据根据凭借用用以沿着顺朝着朝'
           r'）】」》〕》」】〕/\\\\]|$)')

    # R2: "修改/完成/重构/创建... + (了) + X"
    verbs1 = (r'(?:修改|完成|重构|创建|更新|删除|修复|添加|实现'
              r'|整理|优化|处理|编写|写成?|改成?|改为|调整'
              r'|增加|移除|迁移|部署|配置|设计|定义|搞定|写完|写好)')

    # 2a: 空格名（仅ASCII，如 "Stop Hook"）
    m = re.search(verbs1 + r'(?:了|过)?[：:\s]*((?:[A-Za-z0-9_\-\.\+]+ ?){1,2})' + _la, clean)
    if m:
        name = _clean_name(m.group(1).strip())
        if _is_good_name(name) and 2 <= len(name) <= 20:
            log(f"FIND: R2a hit -> {name}")
            return name

    # 2b: 无空格名（支持中英文）
    m = re.search(verbs1 + r'(?:了|过)?[：:\s]*([一-鿿A-Za-z0-9_\-\.\+]{2,16}?)' + _la, clean)
    if m:
        name = m.group(1).rstrip('的')
        if _is_good_name(name) and 2 <= len(name) <= 16:
            log(f"FIND: R2b hit -> {name}")
            return name

    # R3: "关于/针对/对于 X" | "在 X 中"
    m = re.search(
        r'(?:关于|针对|对于|在)[：:\s]*([一-鿿A-Za-z0-9_\-]{2,12})(?:的|中|上|方面|里|时|后|之前|之后)',
        clean)
    if m and _is_good_name(m.group(1)):
        log(f"FIND: R3 hit -> {m.group(1)}")
        return m.group(1)

    # R4: "学习/研究/理解... + (了) + X"
    verbs2 = r'(?:学习|研究|练习|训练|理解|掌握|搞懂|讲解|教学|了解|分析|设计|回顾|复习)'
    m = re.search(verbs2 + r'(?:了|过)?[：:\s]*([一-鿿A-Za-z0-9_\-\.\+]{2,16}?)' + _la, clean)
    if m:
        name = m.group(1).rstrip('的')
        if _is_good_name(name) and 2 <= len(name) <= 16:
            log(f"FIND: R4 hit -> {name}")
            return name

    # R5: "XXX总结/概要/方案/设计/代码..."
    for sfx in ['总结', '概要', '方案', '设计', '代码', '配置',
                '脚本', '实现', '更新', '修复', '版本', '修改']:
        m = re.search(r'([一-鿿A-Za-z0-9_\-]{2,12})' + sfx, clean)
        if m and _is_good_name(m.group(1)):
            log(f"FIND: R5 hit -> {m.group(1)}")
            return m.group(1)

    # R6: "这是/以下是/已完成... + X"
    verbs3 = r'(?:这是|这里是|以下是|上面的是|已完成|已完成的是|正在|已经)'
    m = re.search(verbs3 + r'[：:\s]*([一-鿿A-Za-z0-9_\-\.\+]{2,16}?)' + _la, clean)
    if m:
        name = m.group(1).rstrip('的')
        if _is_good_name(name) and 2 <= len(name) <= 16:
            log(f"FIND: R6 hit -> {name}")
            return name

    # R7: 前段提取
    cleaned = re.sub(
        r'^(?:好的?|嗯|可以|没问题|行|[oO][kK]|欧克|收到|明白|了解'
        r'|搞定了?|完成了|已修改|已更新|已添加'
        r'|来|现在|下面|接下来|首先|最后|然后|对了)'
        r'[，,、！!\.\s？?　]*', '', clean)
    seg = re.split(r'[，,。.!！?？、；:：\n\r]', cleaned, maxsplit=1)[0].strip()
    seg = re.sub(r'\s+(吧|了|哦|啊|呢|吗|哈|呀|的|呗|嘛|么)$', '', seg)
    if _is_good_name(seg) and 2 <= len(seg) <= 16:
        log(f"FIND: R7 hit -> {seg}")
        return seg

    # R8: 全文找第一个中/英文词
    for pat in [r'[一-鿿]{2,10}', r'[A-Za-z][A-Za-z0-9_\-\.]{1,15}']:
        m = re.search(pat, clean)
        if m and _is_good_name(m.group(0)):
            log(f"FIND: R8 hit -> {m.group(0)}")
            return m.group(0)

    log("FIND: no match")
    return None


def infer_project_name(last_message: str, fallback: str) -> str:
    if not last_message.strip():
        log("EXTRACT: empty message, use fallback")
        return fallback
    log(f"EXTRACT: msg[:200] = {last_message[:200]!r}")
    name = _find_topic(last_message)
    if name:
        name = _clean_name(name)
        log(f"EXTRACT: -> {name}")
        if _is_good_name(name) and 2 <= len(name) <= 20:
            log(f"EXTRACT: accepted -> {name}")
            return name
        log(f"EXTRACT: rejected ({name!r})")
    log("EXTRACT: no match, use fallback")
    return fallback


def send_email(subject: str, body: str) -> bool:
    if not EMAIL_ENABLED:
        return False
    msg = MIMEText(body, "plain", "utf-8")
    msg["From"] = SMTP_USER
    msg["To"] = TO_ADDR
    msg["Subject"] = Header(subject, "utf-8")
    for attempt in range(3):
        try:
            server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15)
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, [TO_ADDR], msg.as_string())
            server.quit()
            return True
        except Exception:
            if attempt < 2:
                import time
                time.sleep(5)
    return False


def main() -> None:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        data = {}
    if data.get("stop_hook_active"):
        print(json.dumps({"decision": "approve"}))
        return
    play_sound()
    if EMAIL_ENABLED:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        msg = data.get("last_assistant_message", "")[:2000]
        cwd = data.get("cwd", "")
        fb = os.path.basename(cwd.rstrip("/\\")) if cwd else "Claude Code"
        log(f"MAIN: cwd={cwd!r}, fb={fb!r}")
        log(f"MAIN: msg len={len(msg)}")
        pn = infer_project_name(msg, fb)
        send_email(f"[{pn}] 任务完成", f"项目：{pn}\n时间：{ts}\n")
        log(f"MAIN: email sent, project={pn}")
    print(json.dumps({"decision": "approve"}))


if __name__ == "__main__":
    main()
