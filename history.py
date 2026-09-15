# -*- coding: utf-8 -*-
"""
会话历史存储：把每次同传的双语记录持久化到 data/history/<session_id>.json

设计：
- 一个"会话"= 用户点一次开始到停止之间的所有 transcript
- 每条 transcript 处理完立即追加落盘（增量小文件写入，几 KB 级，够快）
- 线程安全：WebSocket worker 在线程池里调用 add_segment，需要锁
"""
import os
import json
import uuid
import threading
from datetime import datetime
from typing import List, Dict, Optional

from config import Config


class HistoryManager:
    def __init__(self):
        self.history_dir = os.path.join(Config.DATA_DIR, "history")
        os.makedirs(self.history_dir, exist_ok=True)
        self._lock = threading.Lock()

    # ---------- 内部 ----------
    def _path(self, session_id: str) -> str:
        return os.path.join(self.history_dir, f"{session_id}.json")

    def _load(self, session_id: str) -> Optional[Dict]:
        path = self._path(session_id)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def _save(self, data: Dict):
        with open(self._path(data["id"]), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ---------- 会话生命周期 ----------
    def create_session(self) -> Dict:
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
        data = {
            "id": session_id,
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "ended_at": None,
            "segments": [],
        }
        with self._lock:
            self._save(data)
        return data

    def end_session(self, session_id: str) -> bool:
        with self._lock:
            data = self._load(session_id)
            if not data:
                return False
            data["ended_at"] = datetime.now().isoformat(timespec="seconds")
            self._save(data)
            return True

    def add_segment(self, session_id: str, segment: Dict) -> bool:
        """把一条双语 transcript 追加进会话文件，立即落盘"""
        if not session_id:
            return False
        with self._lock:
            data = self._load(session_id)
            if not data:
                return False
            data["segments"].append(segment)
            self._save(data)
            return True

    # ---------- 查询 / 删除 ----------
    def list_sessions(self) -> List[Dict]:
        out: List[Dict] = []
        if not os.path.isdir(self.history_dir):
            return out
        for fn in os.listdir(self.history_dir):
            if not fn.endswith(".json"):
                continue
            data = self._load(fn[:-5])
            if not data:
                continue
            segs = data.get("segments", [])
            preview = ""
            for s in segs:
                if s.get("original"):
                    preview = s["original"][:50]
                    break
            out.append({
                "id": data["id"],
                "started_at": data.get("started_at", ""),
                "ended_at": data.get("ended_at"),
                "count": len(segs),
                "preview": preview,
            })
        out.sort(key=lambda x: x["started_at"], reverse=True)
        return out

    def get_session(self, session_id: str) -> Optional[Dict]:
        return self._load(session_id)

    def delete_session(self, session_id: str) -> bool:
        # 会话 id 只允许 [A-Za-z0-9_]，防止路径穿越
        if not session_id.replace("_", "").isalnum():
            return False
        path = self._path(session_id)
        if not os.path.exists(path):
            return False
        try:
            os.remove(path)
        except OSError:
            # 兜底：某些环境 os.remove 被限制（如回收站不可用），
            # 则移入 _trash 子目录，效果等同从历史中消失
            trash_dir = os.path.join(self.history_dir, "_trash")
            os.makedirs(trash_dir, exist_ok=True)
            try:
                os.replace(path, os.path.join(trash_dir, os.path.basename(path)))
            except OSError:
                return False
        return True

    # ---------- 导出 ----------
    def export_markdown(self, session_id: str) -> Optional[str]:
        data = self._load(session_id)
        if not data:
            return None
        lines = [
            "# 同传记录 " + data["id"],
            "",
            f"- 开始时间：{data.get('started_at', '')}",
            f"- 结束时间：{data.get('ended_at') or '（未结束）'}",
            f"- 共 {len(data.get('segments', []))} 段",
            "",
            "---",
            "",
        ]
        for s in data.get("segments", []):
            head = f"### [{s.get('timestamp', '')}]"
            if s.get("slide_page"):
                title = s.get("slide_title") or ""
                head += f" 课件第 {s['slide_page']} 页 {('· ' + title) if title else ''}"
            lines.append(head)
            lines.append("")
            lines.append(f"**EN** {s.get('original', '')}")
            lines.append("")
            lines.append(f"**中文** {s.get('translated', '')}")
            lines.append("")
        return "\n".join(lines)
