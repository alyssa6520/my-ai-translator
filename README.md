# Realtime Interpretation Tutor · 实时同声传译学习助手

> 基于 FastAPI + WebSocket 的实时中英同传字幕系统：边说边出双语字幕，并与课件内容语义对齐，自动定位当前讲解页码。

English-friendly EN→CN real-time interpretation tutor with slide-aware semantic alignment. Built with FastAPI, WebSocket streaming, and LLM-powered ASR/translation.

## ✨ 功能特性

- **实时同传字幕**：浏览器采集麦克风音频，WebSocket 流式上传，异步流水线处理，说话的同时滚动显示中英双语字幕
- **课件语义对齐**：上传 PPT/PDF 课件后，使用 `bge-m3` 向量模型将实时字幕与课件内容匹配，自动高亮当前讲解对应的页码，构建"听讲—对照"学习闭环
- **双通道 ASR 降级**：云端 ASR（SiliconFlow Qwen3-ASR）为主，本地 Whisper 兜底，云端服务不可用时自动切换，保障课堂不断联
- **课件解析**：支持 PPTX / PDF，逐页提取文本用于后续对齐
- **历史记录管理**：每次同传会话自动持久化，支持查看、导出、删除
- **公网访问部署**：通过 Cloudflare Tunnel 对外提供服务，手机等设备可直接访问

## 🏗 架构

```
 浏览器                     FastAPI 后端
┌──────────┐   WebSocket    ┌─────────────────────────────┐
│ 麦克风采集 │ ─────────────> │  /ws 音频分片接收             │
│ 字幕渲染  │ <───────────── │  异步 worker 流水线：          │
│ 课件面板  │   JSON 推送     │   ASR 转写 → 翻译 → 对齐      │
└──────────┘                │  bge-m3 语义对齐 → 页码定位    │
                            └─────────────────────────────┘
                                     │
                            ┌────────┴────────┐
                            │ 云端 ASR/LLM API │ ←失败时→ 本地 Whisper 兜底
                            └─────────────────┘
```

## 🛠 技术栈

| 层 | 技术 |
|---|---|
| Web 框架 | FastAPI + Uvicorn |
| 实时通信 | WebSocket（音频分片上行 / 字幕 JSON 下行） |
| 语音识别 | SiliconFlow Qwen3-ASR（云端）+ OpenAI Whisper（本地兜底） |
| 翻译 | Qwen2.5-7B-Instruct |
| 向量对齐 | BAAI/bge-m3 embedding + 余弦相似度 |
| 课件解析 | python-pptx / pypdf |
| 前端 | 原生 HTML/JS 单页应用 |
| 公网部署 | cloudflared (Cloudflare Tunnel) |

## 🚀 快速开始

```bash
# 1. 克隆
git clone https://github.com/alyssa6520/my-ai-translator.git
cd my-ai-translator

# 2. 安装依赖
python -m venv venv
venv\Scripts\pip install -r requirements.txt    # Windows
# source venv/bin/activate && pip install -r requirements.txt   # macOS/Linux

# 3. 配置环境变量
copy .env.example .env    # 填入你的 API Key

# 4. 启动
venv\Scripts\python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

浏览器打开 `http://localhost:8000` 即可使用。

## ⚙️ 环境变量

| 变量 | 说明 | 默认值 |
|---|---|---|
| `OPENAI_API_KEY` | LLM / ASR 服务密钥（兼容 OpenAI 协议的服务均可，如 SiliconFlow） | 必填 |
| `OPENAI_BASE_URL` | API 地址 | `https://api.openai.com/v1` |
| `OPENAI_MODEL` | 翻译模型 | `gpt-3.5-turbo` |
| `WHISPER_MODEL` | 本地兜底 Whisper 模型 | `base` |
| `EMBEDDING_MODEL` | 语义对齐向量模型 | `all-MiniLM-L6-v2` |
| `SOURCE_LANGUAGE` / `TARGET_LANGUAGE` | 源/目标语言 | `en` / `zh-CN` |

## 📡 API 一览

| 端点 | 方法 | 说明 |
|---|---|---|
| `/ws` | WebSocket | 音频分片上行，实时字幕/对齐结果下行 |
| `/api/upload-slides` | POST | 上传 PPTX/PDF 课件并解析 |
| `/api/status` | GET | 服务与模型状态 |
| `/api/history` | GET/POST/DELETE | 会话历史查询、导出、删除 |

## 📁 目录结构

```
├── app.py               # FastAPI 主应用：路由、WebSocket、异步流水线
├── audio_transcriber.py # ASR：云端 API + 本地 Whisper 双通道降级
├── translator.py        # LLM 翻译
├── content_aligner.py   # bge-m3 向量语义对齐（字幕↔课件页码）
├── slide_parser.py      # PPT/PDF 课件解析
├── history.py           # 会话历史持久化
├── config.py            # 配置（环境变量驱动）
├── static/index.html    # 前端单页应用
└── requirements.txt
```

## 📄 License

MIT
