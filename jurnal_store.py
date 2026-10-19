"""Formativ jurnal qeydlərinin GitHub-da davamlı saxlanması.

Məlumat `data/jurnal.json` faylında, `jurnal` filialında saxlanılır.
Bu filial deploy filialı (main) deyil — buna görə hər qeyd saxlananda
tətbiq yenidən qurulmur.
"""

import base64
import hashlib
import json
import time
import urllib.error
import urllib.request

API = "https://api.github.com"
DEFAULT_REPO = "Malanix666/sagird-statistikasi"
DEFAULT_BRANCH = "jurnal"
SOURCE_BRANCH = "main"
DEFAULT_PATH = "data/jurnal.json"


def _req(url, token, method="GET", body=None):
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "formativ-jurnal",
    }
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, (json.loads(raw) if raw.strip() else {})
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            payload = {}
        return exc.code, payload
    except Exception as exc:  # şəbəkə xətası
        return -1, {"message": str(exc)}


def serialize(store) -> list:
    """{(sinif, ad, tarix, period): deyər} -> JSON-a uyğun siyahı."""
    return [list(k) + [v] for k, v in sorted(store.items()) if v]


def deserialize(records) -> dict:
    out = {}
    for row in records or []:
        if len(row) == 5:
            out[(str(row[0]), str(row[1]), str(row[2]), int(row[3]))] = str(row[4])
    return out


def store_hash(store) -> str:
    payload = json.dumps(serialize(store), ensure_ascii=False)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def fetch(cfg):
    """GitHub-dan qeydləri oxu.

    -> siyahı (boş ola bilər) : fayl yoxdur / oxundu
    -> None : xəta (token, şəbəkə, icazə)
    """
    url = f"{API}/repos/{cfg['repo']}/contents/{cfg['path']}?ref={cfg['branch']}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {cfg['token']}",
            # raw media tipi: 1MB-dan böyük faylları da oxumağa imkan verir
            "Accept": "application/vnd.github.raw+json",
            "User-Agent": "formativ-jurnal",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return [] if exc.code == 404 else None
    except Exception:
        return None
    try:
        payload = json.loads(text)
    except Exception:
        return None
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and payload.get("encoding") == "base64" and payload.get("content"):
        # raw istənsə də GitHub obyekt forması qaytardısa
        try:
            inner = json.loads(base64.b64decode(payload["content"]).decode("utf-8"))
        except Exception:
            return None
        return inner if isinstance(inner, list) else []
    return None


def _ensure_branch(cfg) -> bool:
    token = cfg["token"]
    repo, branch = cfg["repo"], cfg["branch"]
    status, _ = _req(f"{API}/repos/{repo}/git/ref/heads/{branch}", token)
    if status == 200:
        return True
    if status != 404:
        return False
    status, payload = _req(f"{API}/repos/{repo}/git/ref/heads/{SOURCE_BRANCH}", token)
    if status != 200:
        return False
    sha = payload.get("object", {}).get("sha")
    if not sha:
        return False
    status, _ = _req(
        f"{API}/repos/{repo}/git/refs",
        token,
        method="POST",
        body={"ref": f"refs/heads/{branch}", "sha": sha},
    )
    return status in (200, 201)


def push(cfg, records) -> tuple:
    """Qeylləri GitHub-a yaz. -> (uğur, mesaj)"""
    token = cfg["token"]
    repo, branch, path = cfg["repo"], cfg["branch"], cfg["path"]
    if not _ensure_branch(cfg):
        return False, "GitHub filialı yaradıla bilmədi — token `contents: write` icazəsi alın"
    sha = None
    status, payload = _req(f"{API}/repos/{repo}/contents/{path}?ref={branch}", token)
    if status == 200:
        sha = payload.get("sha")
    elif status != 404:
        return False, f"Fayl oxunmadı (HTTP {status}): {payload.get('message', '')}"
    body = {
        "message": f"Formativ jurnal saxlanıldı — {time.strftime('%d.%m.%Y %H:%M')}",
        "content": base64.b64encode(
            json.dumps(records, ensure_ascii=False).encode("utf-8")
        ).decode("utf-8"),
        "branch": branch,
    }
    if sha:
        body["sha"] = sha
    status, payload = _req(
        f"{API}/repos/{repo}/contents/{path}", token, method="PUT", body=body
    )
    if status in (200, 201):
        return True, f"GitHub-a saxlanıldı (filial `{branch}`)"
    return False, f"Xəta (HTTP {status}): {payload.get('message', '')}"[:300]
