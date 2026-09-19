#!/usr/bin/env python3
"""공부판 드라이브 도우미 — 클라우드 루틴이 구글 드라이브 '학습시스템' 폴더의 파일을 읽고 쓴다.

사용법
  python3 drive.py get <이름>              파일 내용을 표준출력으로
  python3 drive.py put <이름> <로컬파일>    로컬 파일 내용으로 덮어쓰기 (없으면 만든다)
  python3 drive.py append <이름> <한줄>     파일 끝에 한 줄 덧붙이기 (없으면 만든다)
  python3 drive.py now                    현재 시각 epoch ms

환경변수 (비밀값은 이 파일에 넣지 않는다)
  GDRIVE_CLIENT_ID, GDRIVE_CLIENT_SECRET, GDRIVE_REFRESH_TOKEN
  GDRIVE_FOLDER  폴더 이름, 기본값 "학습시스템"
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://www.googleapis.com/drive/v3/files"
UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"


def _request(url, method="GET", data=None, headers=None):
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code} {method} {url}\n{e.read().decode('utf-8', 'replace')[:500]}")


def token():
    missing = [k for k in ("GDRIVE_CLIENT_ID", "GDRIVE_CLIENT_SECRET", "GDRIVE_REFRESH_TOKEN") if not os.environ.get(k)]
    if missing:
        sys.exit("환경변수 없음: " + ", ".join(missing))
    body = urllib.parse.urlencode({
        "client_id": os.environ["GDRIVE_CLIENT_ID"],
        "client_secret": os.environ["GDRIVE_CLIENT_SECRET"],
        "refresh_token": os.environ["GDRIVE_REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    }).encode()
    return json.loads(_request("https://oauth2.googleapis.com/token", "POST", body))["access_token"]


def _q(s):
    return s.replace("\\", "\\\\").replace("'", "\\'")


def find(auth, query):
    url = API + "?" + urllib.parse.urlencode({
        "q": query, "fields": "files(id,name,mimeType)", "orderBy": "modifiedTime desc", "pageSize": "10",
    })
    return json.loads(_request(url, headers=auth))["files"]


def folder_id(auth):
    name = os.environ.get("GDRIVE_FOLDER", "학습시스템")
    hits = find(auth, f"name='{_q(name)}' and mimeType='application/vnd.google-apps.folder' and trashed=false")
    if not hits:
        sys.exit(f"드라이브에 '{name}' 폴더가 없음")
    return hits[0]["id"]


def file_in(auth, folder, name):
    hits = find(auth, f"'{folder}' in parents and name='{_q(name)}' and trashed=false")
    return hits[0] if hits else None


def read(auth, f):
    if f["mimeType"].startswith("application/vnd.google-apps."):
        url = f"{API}/{f['id']}/export?mimeType=text%2Fplain"
    else:
        url = f"{API}/{f['id']}?alt=media"
    return _request(url, headers=auth).decode("utf-8-sig")


def write(auth, folder, name, text):
    data = text.encode("utf-8")
    mime = "application/json" if name.endswith(".json") else "text/plain"
    f = file_in(auth, folder, name)
    if f is None:
        meta = json.dumps({"name": name, "parents": [folder], "mimeType": mime}).encode()
        created = json.loads(_request(API + "?fields=id", "POST", meta, {**auth, "Content-Type": "application/json"}))
        fid = created["id"]
    else:
        fid = f["id"]
    _request(f"{UPLOAD}/{fid}?uploadType=media", "PATCH", data, {**auth, "Content-Type": mime + "; charset=utf-8"})


def main(argv):
    if not argv:
        sys.exit(__doc__)
    cmd = argv[0]
    if cmd == "now":
        print(int(time.time() * 1000))
        return
    auth = {"Authorization": "Bearer " + token()}
    folder = folder_id(auth)
    if cmd == "get" and len(argv) == 2:
        f = file_in(auth, folder, argv[1])
        if f is None:
            sys.exit(f"파일 없음: {argv[1]}")
        sys.stdout.write(read(auth, f))
    elif cmd == "put" and len(argv) == 3:
        with open(argv[2], encoding="utf-8") as fh:
            write(auth, folder, argv[1], fh.read())
        print(f"덮어씀: {argv[1]}")
    elif cmd == "append" and len(argv) == 3:
        f = file_in(auth, folder, argv[1])
        old = read(auth, f) if f else ""
        if old and not old.endswith("\n"):
            old += "\n"
        write(auth, folder, argv[1], old + argv[2].rstrip("\n") + "\n")
        print(f"덧붙임: {argv[1]}")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
