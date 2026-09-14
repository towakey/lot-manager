# -*- coding: utf-8 -*-

import hashlib
import json
import os
import re
import secrets
import tempfile
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SESSION_TTL_SECONDS = 12 * 60 * 60
TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{32,128}$")


def get_session_dir():
    path_hash = hashlib.sha256(SCRIPT_DIR.encode("utf-8")).hexdigest()[:16]
    return os.path.join(tempfile.gettempdir(), "lot-manager-" + path_hash)


def create_session(username):
    session_dir = get_session_dir()
    if not os.path.exists(session_dir):
        try:
            os.makedirs(session_dir, mode=0o700)
        except OSError:
            if not os.path.isdir(session_dir):
                raise

    now = int(time.time())
    for filename in os.listdir(session_dir):
        path = os.path.join(session_dir, filename)
        try:
            if os.path.getmtime(path) < now - SESSION_TTL_SECONDS:
                os.remove(path)
        except OSError:
            pass

    token = secrets.token_urlsafe(32)
    path = os.path.join(session_dir, token + ".json")
    data = json.dumps({
        "username": username,
        "expires_at": now + SESSION_TTL_SECONDS,
    })
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(data)
    return token


def validate_session(username, token):
    if not username or not TOKEN_PATTERN.match(token or ""):
        return False

    path = os.path.join(get_session_dir(), token + ".json")
    try:
        with open(path, mode="r") as f:
            data = json.load(f)
    except (IOError, OSError, ValueError):
        return False

    if data.get("username") != username:
        return False
    if data.get("expires_at", 0) < int(time.time()):
        try:
            os.remove(path)
        except OSError:
            pass
        return False
    return True
