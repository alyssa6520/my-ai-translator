import os
import tempfile
import queue
import threading
import time
from typing import Optional, Callable
import numpy as np
from config import Config


class AudioTranscriber:
    LOCAL_STT_INSTALL_CMD = (
        "如需使用本地 Whisper 转写（省 API token），请运行：\n"
        "  pip install openai-whisper>=1.1.10 torch torchaudio pydub\n"
        "或单独安装：pip install -r requirements-local-stt.txt"
    )

    def __init__(self, use_api: bool = True):
        self.use_api = use_api
        self._whisper_model = None
        self._local_stt_unavailable = False
        self._recording = False
        self._audio_queue = queue.Queue()
        self._record_thread = None
        self._transcribe_thread = None

    def _load_whisper_model(self):
        if self._whisper_model is None:
            try:
                import whisper
            except ImportError as e:
                self._local_stt_unavailable = True
                raise RuntimeError(
                    f"本地 Whisper 模型未安装。\n{self.LOCAL_STT_INSTALL_CMD}"
                ) from e
            self._whisper_model = whisper.load_model(Config.WHISPER_MODEL)
        return self._whisper_model

    def transcribe_file(self, audio_path: str, language: Optional[str] = None) -> str:
        api_available = bool(self.use_api and Config.OPENAI_API_KEY)
        local_available = not self._local_stt_unavailable

        last_err = None
        if api_available:
            try:
                return self._transcribe_with_api(audio_path, language)
            except Exception as e:
                last_err = e
                print(f"[转写] API 模式失败: {e}")

        if local_available:
            try:
                return self._transcribe_with_local(audio_path, language)
            except Exception as e:
                last_err = e
                print(f"[转写] 本地模式失败: {e}")

        msg = str(last_err) if last_err else "未配置可用的转写方式"
        if not api_available and not local_available:
            msg = (
                "既没有可用的 OpenAI API Key，也未安装本地 Whisper。\n"
                "二选一即可：\n"
                "  A) 在 设置 或 .env 中配置 OPENAI_API_KEY\n"
                f"  B) {self.LOCAL_STT_INSTALL_CMD}"
            )
        return f"[转写失败] {msg}"

    def _transcribe_with_api(self, audio_path: str, language: Optional[str]) -> str:
        # SiliconFlow 语音识别不支持 OpenAI 的 openai 库，必须用 Requests 直连
        import requests
        url = f"{Config.OPENAI_BASE_URL}/audio/transcriptions"
        headers = {"Authorization": f"Bearer {Config.OPENAI_API_KEY}"}
        
        # Streamlit audio_input 可能会产生 mp4 / webm 格式，必须在 filename 里体现
        # 否则 SiliconFlow 可能会报错 400 不支持的文件类型
        ext = os.path.splitext(audio_path)[1] or ".wav"
        filename = f"audio{ext}"

        with open(audio_path, "rb") as f:
            files = {"file": (filename, f, "audio/wav")}
            data = {"model": Config.WHISPER_MODEL}
            # SiliconFlow API
            response = requests.post(url, headers=headers, files=files, data=data)
            
        if response.status_code == 200:
            return response.json().get("text", "")
        else:
            raise Exception(f"API Error {response.status_code}: {response.text}")

    def _transcribe_with_local(self, audio_path: str, language: Optional[str]) -> str:
        model = self._load_whisper_model()
        kwargs = {"fp16": False}
        if language:
            kwargs["language"] = language
        result = model.transcribe(audio_path, **kwargs)
        return result["text"]

    def start_recording(self, on_transcribe: Optional[Callable[[str], None]] = None,
                        chunk_seconds: int = 5):
        if self._recording:
            return
        self._recording = True
        self._audio_queue.queue.clear()

        try:
            import sounddevice as sd
        except ImportError:
            raise RuntimeError("请先安装 sounddevice: pip install sounddevice")

        def callback(indata, frames, time_info, status):
            if status:
                pass
            self._audio_queue.put(indata.copy())

        def record_loop():
            try:
                stream = sd.InputStream(
                    channels=1,
                    samplerate=Config.SAMPLE_RATE,
                    dtype='int16',
                    blocksize=Config.SAMPLE_RATE // 10,
                    callback=callback
                )
                stream.start()
                try:
                    while self._recording:
                        time.sleep(0.1)
                finally:
                    stream.stop()
            except Exception as e:
                error_msg = str(e)
                print(f"[录音错误] 无法打开麦克风: {error_msg}")
                self._recording = False
                if hasattr(self, 'on_error') and self.on_error:
                    self.on_error(f"服务器本机麦克风错误: {error_msg}")

        def transcribe_loop():
            buffer = []
            accumulated = 0
            import soundfile as sf
            while self._recording:
                try:
                    data = self._audio_queue.get(timeout=0.5)
                    buffer.append(data)
                    accumulated += len(data)

                    if accumulated >= Config.SAMPLE_RATE * chunk_seconds:
                        audio_data = np.concatenate(buffer, axis=0)
                        buffer = []
                        accumulated = 0

                        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tf:
                            temp_path = tf.name
                        try:
                            sf.write(temp_path, audio_data, Config.SAMPLE_RATE)
                            text = self.transcribe_file(temp_path)
                            if text.strip() and on_transcribe:
                                on_transcribe(text.strip())
                        except Exception as e:
                            print(f"转写块失败: {e}")
                        finally:
                            if os.path.exists(temp_path):
                                os.unlink(temp_path)
                except queue.Empty:
                    continue

            if buffer:
                audio_data = np.concatenate(buffer, axis=0)
                import soundfile as sf
                with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tf:
                    temp_path = tf.name
                try:
                    sf.write(temp_path, audio_data, Config.SAMPLE_RATE)
                    text = self.transcribe_file(temp_path)
                    if text.strip() and on_transcribe:
                        on_transcribe(text.strip())
                except Exception as e:
                    print(f"转写最后块失败: {e}")
                finally:
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)

        self._record_thread = threading.Thread(target=record_loop, daemon=True)
        self._transcribe_thread = threading.Thread(target=transcribe_loop, daemon=True)
        self._record_thread.start()
        self._transcribe_thread.start()

    def stop_recording(self):
        self._recording = False
        if self._record_thread:
            self._record_thread.join(timeout=2)
        if self._transcribe_thread:
            self._transcribe_thread.join(timeout=5)
