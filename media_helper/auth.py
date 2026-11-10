"""本地登录：首次访问设置密码，之后用会话 Cookie 保持登录。

只依赖标准库：密码用 PBKDF2-HMAC-SHA256 加盐散列，会话令牌随机生成后放在
内存里（进程重启即失效，需要重新登录）。密码文件独立于 `settings.json`，
这样导出/导入设置不会把密码带出去。

本模块只管密码与令牌，不认识 HTTP；Cookie 的收发在 `server.py` 里。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import threading
import time
from datetime import datetime
from pathlib import Path

from .config import atomic_write

PASSWORD_FILE = "auth.json"
COOKIE_NAME = "mh_session"

ITERATIONS = 260_000
MIN_LENGTH = 6
MAX_LENGTH = 128
SESSION_TTL = 30 * 24 * 3600

# 同一来源连续失败太多次就先冷却，避免在局域网里被慢慢试出来。
MAX_FAILURES = 8
FAILURE_WINDOW = 300
LOCKOUT = 60


class AuthError(ValueError):
    """密码文件损坏或密码不合规。"""


def _digest(password, salt, iterations):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)


def check_password_policy(password):
    """返回规范化后的密码，不合规时抛 AuthError。"""
    if not isinstance(password, str):
        raise AuthError("密码必须是文本")
    if password != password.strip():
        raise AuthError("密码首尾不能有空格")
    if len(password) < MIN_LENGTH:
        raise AuthError(f"密码至少 {MIN_LENGTH} 位")
    if len(password) > MAX_LENGTH:
        raise AuthError(f"密码最多 {MAX_LENGTH} 位")
    return password


class AuthStore:
    """密码与登录会话的唯一入口；线程安全，可被多个请求共用。"""

    def __init__(self, state_dir, clock=time.monotonic):
        self.path = Path(state_dir) / PASSWORD_FILE
        self.lock = threading.RLock()
        self.clock = clock
        self._sessions = {}  # token -> 过期时刻
        self._failures = {}  # 来源 -> [失败时刻]
        self._record = None
        self._load()

    # ---------------------------------------------------------------- 密码

    def _load(self):
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            salt = bytes.fromhex(str(data["salt"]))
            digest = bytes.fromhex(str(data["hash"]))
            iterations = int(data.get("iterations") or ITERATIONS)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise AuthError(f"登录密码文件无法解析：{self.path}；"
                            f"可删除该文件后重新设置密码（{exc}）") from exc
        if not salt or not digest or iterations < 1000:
            raise AuthError(f"登录密码文件内容不完整：{self.path}；可删除该文件后重新设置密码")
        self._record = dict(salt=salt, digest=digest, iterations=iterations,
                            updatedAt=str(data.get("updatedAt") or ""))

    @property
    def has_password(self):
        return self._record is not None

    @property
    def updated_at(self):
        return self._record["updatedAt"] if self._record else ""

    def set_password(self, password):
        """写入新密码并让所有已登录会话失效（改密码后要求重新登录）。"""
        password = check_password_policy(password)
        salt = secrets.token_bytes(16)
        digest = _digest(password, salt, ITERATIONS)
        record = dict(salt=salt, digest=digest, iterations=ITERATIONS,
                      updatedAt=datetime.now().isoformat(timespec="seconds"))
        payload = json.dumps({"version": 1, "salt": salt.hex(), "hash": digest.hex(),
                              "iterations": ITERATIONS, "updatedAt": record["updatedAt"]},
                             ensure_ascii=False, indent=2).encode()
        with self.lock:
            atomic_write(self.path, payload)
            self._record = record
            self._sessions.clear()
            self._failures.clear()

    def verify(self, password):
        with self.lock:
            record = self._record
        if record is None:
            return False
        if not isinstance(password, str):
            return False
        try:
            candidate = _digest(password, record["salt"], record["iterations"])
        except (ValueError, TypeError):
            return False
        return hmac.compare_digest(candidate, record["digest"])

    # ---------------------------------------------------------------- 会话

    def issue(self):
        """生成一个新会话令牌，并顺带清掉已经过期的。"""
        token = secrets.token_urlsafe(32)
        now = self.clock()
        with self.lock:
            for value, expiry in list(self._sessions.items()):
                if expiry <= now:
                    self._sessions.pop(value, None)
            self._sessions[token] = now + SESSION_TTL
        return token

    def check(self, token):
        """令牌有效时顺手续期，避免用着用着被踢下线。"""
        if not token:
            return False
        now = self.clock()
        with self.lock:
            expiry = self._sessions.get(token)
            if expiry is None:
                return False
            if expiry <= now:
                self._sessions.pop(token, None)
                return False
            self._sessions[token] = now + SESSION_TTL
        return True

    def revoke(self, token):
        with self.lock:
            self._sessions.pop(token or "", None)

    def revoke_all(self):
        with self.lock:
            self._sessions.clear()

    @property
    def session_count(self):
        with self.lock:
            return len(self._sessions)

    # -------------------------------------------------------------- 失败冷却

    def blocked_for(self, key):
        """该来源还要等多少秒才能再试；0 表示可以试。"""
        now = self.clock()
        with self.lock:
            stamps = [value for value in self._failures.get(key, []) if now - value < FAILURE_WINDOW]
            if not stamps:
                self._failures.pop(key, None)
                return 0
            self._failures[key] = stamps
            if len(stamps) < MAX_FAILURES:
                return 0
            remaining = LOCKOUT - (now - stamps[-1])
            return int(remaining) + 1 if remaining > 0 else 0

    def note_failure(self, key):
        now = self.clock()
        with self.lock:
            stamps = [value for value in self._failures.get(key, []) if now - value < FAILURE_WINDOW]
            stamps.append(now)
            self._failures[key] = stamps

    def reset_failures(self, key):
        with self.lock:
            self._failures.pop(key, None)
