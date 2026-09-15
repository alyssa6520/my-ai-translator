# -*- coding: utf-8 -*-
"""
同声传译学习助手 - FastAPI + WebSocket 流式版

取代原 Streamlit 版本：
- 浏览器 getUserMedia 只获取一次麦克风，MediaRecorder 每 5 秒切片
- WebSocket 持久连接，音频二进制直推
- 后端 ThreadPoolExecutor 处理转写/翻译，不阻塞事件循环

启动：python app.py  或  uvicorn app:app --host 0.0.0.0 --port 8000
"""
import os
import sys
import json
import asyncio
import tempfile
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
from audio_transcriber import AudioTranscriber
from translator import Translator
from content_aligner import ContentAligner
from slide_parser import SlideParser
from history import HistoryManager

# =====================================================
# 初始化
# =====================================================
app = FastAPI(title="同声传译学习助手")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# 处理音频的线程池（Whisper API 调用会阻塞，必须放线程里）
executor = ThreadPoolExecutor(max_workers=8)

# 单用户全局单例
transcriber = AudioTranscriber(use_api=True)
translator = Translator()
aligner = ContentAligner()
slide_parser = SlideParser()
history = HistoryManager()

# 全局课件状态（单用户模式）
state = {
    "slides": [],        # list[dict]
    "course_name": "",
    "session_id": None,  # 当前同传会话 id（历史记录用）
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# =====================================================
# 工具函数
# =====================================================
def detect_audio_ext(data: bytes) -> str:
    """通过 magic bytes 自动识别音频格式（关键！MediaRecorder 产出的格式与浏览器相关）"""
    if len(data) < 12:
        return ".webm"
    if data[:4] == b"\x1a\x45\xdf\xa3":            # EBML / WebM
        return ".webm"
    if data[4:8] == b"ftyp":                        # MP4 / M4A
        return ".mp4"
    if data[:4] == b"OggS":                         # OGG
        return ".ogg"
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":  # WAV
        return ".wav"
    if data[:3] == b"ID3":                          # MP3
        return ".mp3"
    return ".webm"


def process_audio_sync(audio_bytes: bytes, ext: str) -> dict:
    """在线程池里执行：转写 → 对齐课件 → 翻译"""
    if not audio_bytes or len(audio_bytes) < 500:
        return {"error": "音频太短，已忽略"}

    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tf:
        tf.write(audio_bytes)
        temp_path = tf.name

    try:
        text = transcriber.transcribe_file(temp_path)
        if not text or text.startswith("[转写失败]"):
            return {"error": f"转写失败: {text}"}

        text = text.strip()
        if not text:
            return {"error": "未识别到有效内容"}

        # ---- 课件对齐（如果有课件） ----
        slide_page = None
        slide_title = ""
        confidence = 0.0
        slide_ctx = ""

        slides = state["slides"]
        if slides:
            try:
                page_num, conf = aligner.find_best_match(text)
                slide_page = page_num
                confidence = float(conf)
                idx = page_num - 1
                if 0 <= idx < len(slides):
                    s = slides[idx]
                    slide_title = s.get("title", f"第 {page_num} 页")
                    slide_ctx = s.get("content", "")
            except Exception as e:
                print(f"[对齐失败] {e}")

        # ---- 翻译 ----
        translated = translator.translate(text, slide_context=slide_ctx)

        return {
            "original": text,
            "translated": translated,
            "slide_page": slide_page,
            "slide_title": slide_title,
            "confidence": confidence,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
        }
    finally:
        try:
            os.unlink(temp_path)
        except Exception:
            pass


def parse_slides_sync(temp_path: str) -> list:
    """在线程池里执行：解析课件 + 构建向量索引（都是阻塞 IO/网络调用）"""
    slides = slide_parser.parse_file(temp_path)
    slides_data = [s.to_dict() for s in slides]
    aligner.index_slides(slide_parser.get_all_texts(slides))
    return slides_data


# =====================================================
# WebSocket：核心流式端点
# =====================================================
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    print("[WS] 客户端已连接")

    loop = asyncio.get_running_loop()
    audio_queue: asyncio.Queue = asyncio.Queue(maxsize=30)

    async def worker():
        """串行处理队列里的音频，保证结果按顺序返回"""
        while True:
            item = await audio_queue.get()
            if item is None:           # 哨兵：退出
                break

            audio_bytes, ext = item
            try:
                result = await loop.run_in_executor(
                    executor, process_audio_sync, audio_bytes, ext
                )
                if "error" in result:
                    await ws.send_text(json.dumps({
                        "type": "error", "message": result["error"]
                    }, ensure_ascii=False))
                else:
                    result["type"] = "transcript"
                    # ---- 自动保存到历史（双语记忆） ----
                    try:
                        seg = {k: v for k, v in result.items() if k != "type"}
                        if history.add_segment(state["session_id"], seg):
                            result["saved"] = True
                    except Exception as e:
                        print(f"[历史保存失败] {e}")
                    await ws.send_text(json.dumps(result, ensure_ascii=False))
            except Exception as e:
                print(f"[处理失败] {e}")
                try:
                    await ws.send_text(json.dumps({
                        "type": "error", "message": str(e)
                    }, ensure_ascii=False))
                except Exception:
                    pass
            finally:
                audio_queue.task_done()

    worker_task = asyncio.create_task(worker())

    try:
        while True:
            message = await ws.receive()

            if message["type"] == "websocket.disconnect":
                break

            # ---- 二进制帧：音频数据 ----
            if message.get("bytes"):
                data = message["bytes"]
                ext = detect_audio_ext(data)
                try:
                    audio_queue.put_nowait((data, ext))
                except asyncio.QueueFull:
                    print("[WS] 队列已满，丢弃一块音频")

            # ---- 文本帧：控制消息 ----
            elif message.get("text"):
                try:
                    msg = json.loads(message["text"])
                except json.JSONDecodeError:
                    continue

                mtype = msg.get("type")
                if mtype == "ping":
                    await ws.send_text(json.dumps({"type": "pong"}))
                elif mtype == "clear":
                    translator.clear_history()
                    await ws.send_text(json.dumps({"type": "cleared"}))
                elif mtype == "reset-slides":
                    state["slides"] = []
                    await ws.send_text(json.dumps({"type": "slides-cleared"}))
                elif mtype == "session-start":
                    # 开始一次同传会话（历史记忆）
                    sess = history.create_session()
                    state["session_id"] = sess["id"]
                    await ws.send_text(json.dumps({
                        "type": "session-started", "session_id": sess["id"]
                    }, ensure_ascii=False))
                elif mtype == "session-end":
                    if state["session_id"]:
                        history.end_session(state["session_id"])
                    await ws.send_text(json.dumps({"type": "session-ended"}))

    except WebSocketDisconnect:
        print("[WS] 客户端断开")
    except Exception as e:
        print(f"[WS] 错误: {e}")
    finally:
        # 让 worker 把队列里剩余的都处理完（最多 5 秒）
        try:
            await audio_queue.put(None)
            await asyncio.wait_for(worker_task, timeout=5.0)
        except Exception:
            worker_task.cancel()
        try:
            await ws.close()
        except Exception:
            pass


# =====================================================
# 课件上传（可选）
# =====================================================
@app.post("/api/upload-slides")
async def upload_slides(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in (".pdf", ".pptx", ".ppt"):
        return JSONResponse({"error": "只支持 PDF / PPTX 文件"}, status_code=400)

    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tf:
        tf.write(await file.read())
        temp_path = tf.name

    try:
        loop = asyncio.get_running_loop()
        # 解析 + embedding 索引都是阻塞调用，放线程池避免卡住事件循环
        slides_data = await loop.run_in_executor(executor, parse_slides_sync, temp_path)
        state["slides"] = slides_data

        return {
            "success": True,
            "count": len(slides_data),
            "slides": [
                {"page_num": s.get("page_num"), "title": s.get("title", "")}
                for s in slides_data
            ],
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    finally:
        try:
            os.unlink(temp_path)
        except Exception:
            pass


@app.get("/api/status")
async def status():
    return {
        "slides_loaded": len(state["slides"]),
        "api_configured": bool(Config.OPENAI_API_KEY),
        "model": Config.WHISPER_MODEL,
    }


# =====================================================
# 历史记录（双语记忆）
# =====================================================
@app.get("/api/history")
async def list_history():
    return {"sessions": history.list_sessions()}


@app.get("/api/history/{session_id}")
async def get_history(session_id: str):
    data = history.get_session(session_id)
    if not data:
        return JSONResponse({"error": "会话不存在"}, status_code=404)
    return data


@app.delete("/api/history/{session_id}")
async def delete_history(session_id: str):
    ok = history.delete_session(session_id)
    if not ok:
        return JSONResponse({"error": "删除失败（会话不存在或 id 非法）"}, status_code=404)
    return {"success": True}


@app.get("/api/history/{session_id}/export")
async def export_history(session_id: str):
    from fastapi.responses import Response
    md = history.export_markdown(session_id)
    if md is None:
        return JSONResponse({"error": "会话不存在"}, status_code=404)
    return Response(
        content=md,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{session_id}.md"'
        },
    )


# =====================================================
# 静态前端
# =====================================================
STATIC_DIR = os.path.join(BASE_DIR, "static")
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


# =====================================================
# 启动
# =====================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        ws_ping_interval=20,
        ws_ping_timeout=20,
    )
