import os
import json
import time
import secrets
from typing import Optional, Dict, Any

PROJECT_DIR = os.getenv("PROJECT_DIR", "data/projects")

def ensure_dirs():
    os.makedirs(PROJECT_DIR, exist_ok=True)

def new_project_id() -> str:
    # short + shareable
    return secrets.token_urlsafe(8).replace("-", "").replace("_", "")[:12]

def project_path(project_id: str) -> str:
    safe = "".join([c for c in str(project_id) if c.isalnum()])
    return os.path.join(PROJECT_DIR, f"{safe}.json")

def save_project(project_id: str, payload: Dict[str, Any]) -> str:
    ensure_dirs()
    payload = dict(payload)
    payload["project_id"] = project_id
    payload["updated_at"] = int(time.time())
    p = project_path(project_id)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return p

def load_project(project_id: str) -> Optional[Dict[str, Any]]:
    ensure_dirs()
    p = project_path(project_id)
    if not os.path.exists(p):
        return None
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)

def list_projects(limit: int = 50) -> list:
    ensure_dirs()
    files = []
    for fn in os.listdir(PROJECT_DIR):
        if fn.endswith(".json"):
            full = os.path.join(PROJECT_DIR, fn)
            files.append((os.path.getmtime(full), fn[:-5]))
    files.sort(reverse=True)
    return [pid for _, pid in files[:limit]]
