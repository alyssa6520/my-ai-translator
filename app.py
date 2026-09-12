import os
import sys
import tempfile
import threading
import time
from datetime import datetime

import streamlit as st
from streamlit import session_state as ss

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
from slide_parser import SlideParser
from audio_transcriber import AudioTranscriber
from translator import Translator
from content_aligner import ContentAligner
from storage import StorageManager

st.set_page_config(
    page_title="🎓 同声传译学习助手",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .main-header { text-align: center; padding: 1rem 0; }
    .transcript-box { border: 1px solid #e0e0e0; border-radius: 8px; padding: 12px; margin: 8px 0; }
    .original-text { color: #555; font-size: 0.95rem; margin-bottom: 4px; }
    .translated-text { color: #1f77b4; font-size: 1.05rem; font-weight: 500; }
    .page-tag { display: inline-block; background: #ff9800; color: white; padding: 2px 10px; 
                border-radius: 12px; font-size: 0.8rem; margin-right: 8px; }
    .slide-title { font-weight: 600; color: #333; }
    .timestamp { font-size: 0.75rem; color: #999; }
    .sidebar-nav { padding: 10px 0; }
    .nav-item { padding: 10px 15px; border-radius: 8px; margin: 4px 0; cursor: pointer; }
    .nav-item:hover { background: #f0f2f6; }
    .nav-active { background: #1f77b4; color: white !important; }
    .recording-dot { display: inline-block; width: 12px; height: 12px; 
                     background: #e74c3c; border-radius: 50%; 
                     animation: pulse 1.5s infinite; margin-right: 8px; }
    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.4; }
    }
    .review-card { border-left: 4px solid #1f77b4; padding-left: 15px; margin: 15px 0; }
</style>
""", unsafe_allow_html=True)


def get_storage():
    if "storage" not in ss:
        ss.storage = StorageManager()
    return ss.storage


def get_parser():
    if "parser" not in ss:
        ss.parser = SlideParser()
    return ss.parser


def get_translator():
    if "translator" not in ss:
        ss.translator = Translator()
    return ss.translator


def get_aligner():
    if "aligner" not in ss:
        ss.aligner = ContentAligner()
    return ss.aligner


def get_transcriber():
    if "transcriber" not in ss:
        ss.transcriber = AudioTranscriber(use_api=True)
    return ss.transcriber


def render_sidebar():
    with st.sidebar:
        st.markdown("### 🎓 同声传译学习助手")
        st.markdown("---")

        page = st.radio(
            "导航",
            ["🏠 主页", "📚 上课模式", "📖 复习模式", "⚙️ 设置"],
            label_visibility="collapsed"
        )

        st.markdown("---")

        if "current_course_id" in ss and ss.current_course_id:
            storage = get_storage()
            course = storage.get_course(ss.current_course_id)
            if course:
                st.markdown(f"**当前课程**: {course.name}")
                st.markdown(f"📑 {len(course.slides)} 页课件")
                st.markdown(f"💬 {len(course.transcripts)} 条记录")
                if st.button("🔓 退出课程", use_container_width=True):
                    ss.current_course_id = None
                    ss.current_course = None
                    st.rerun()

        st.markdown("---")
        st.markdown("💡 **提示**: 先配置 API Key，再上传课件开始上课")

        nav_map = {
            "🏠 主页": "home",
            "📚 上课模式": "class",
            "📖 复习模式": "review",
            "⚙️ 设置": "settings",
        }
        return nav_map.get(page, "home")


def render_home():
    st.markdown('<div class="main-header"><h1>🎓 同声传译学习助手</h1></div>', unsafe_allow_html=True)
    st.markdown("<p style='text-align:center;color:#666;margin-bottom:2rem;'>"
                "上传课件 → 实时录音转写翻译 → 自动对齐课件页面 → 随时复习回放</p>",
                unsafe_allow_html=True)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown("### 📄 步骤 1")
        st.info("上传课件 (PDF/PPTX)")
    with col2:
        st.markdown("### 🎙️ 步骤 2")
        st.info("开始上课，实时录音")
    with col3:
        st.markdown("### 🌐 步骤 3")
        st.info("自动转写+翻译+对齐页面")
    with col4:
        st.markdown("### 📖 步骤 4")
        st.info("随时复习，回顾讲解")

    st.markdown("---")

    storage = get_storage()
    courses = storage.list_courses()

    col_l, col_r = st.columns([2, 1])

    with col_r:
        st.markdown("#### ➕ 创建新课程")
        course_name = st.text_input("课程名称", placeholder="例如：机器学习 第3讲")
        uploaded_file = st.file_uploader("上传课件", type=["pdf", "pptx", "ppt"])
        if st.button("🚀 创建并进入课程", use_container_width=True, type="primary"):
            if not course_name.strip():
                st.error("请输入课程名称")
            elif not uploaded_file:
                st.error("请上传课件文件")
            else:
                with tempfile.NamedTemporaryFile(delete=False,
                                                  suffix=os.path.splitext(uploaded_file.name)[1]) as tf:
                    tf.write(uploaded_file.getvalue())
                    temp_path = tf.name
                try:
                    parser = get_parser()
                    slides = parser.parse_file(temp_path)
                    slides_data = [s.to_dict() for s in slides]
                    course = storage.create_course(course_name.strip(), temp_path, slides_data)
                    ss.current_course_id = course.id
                    ss.current_course = course

                    aligner = get_aligner()
                    aligner.index_slides(parser.get_all_texts(slides))
                    ss.current_slides = slides

                    get_translator().clear_history()

                    st.success(f"✅ 课程创建成功！共 {len(slides)} 页课件")
                    time.sleep(1)
                    ss.current_page = "class"
                    st.rerun()
                finally:
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)

    with col_l:
        st.markdown("#### 📚 我的课程")
        if not courses:
            st.info("还没有课程，先创建一个吧！")
        else:
            for course in courses:
                with st.container():
                    c1, c2, c3 = st.columns([3, 1, 1])
                    with c1:
                        st.markdown(f"**{course.name}**")
                        st.markdown(
                            f"<span class='timestamp'>更新于 {course.updated_at[:16].replace('T', ' ')}  "
                            f"| 📑 {len(course.slides)} 页 | 💬 {len(course.transcripts)} 条</span>",
                            unsafe_allow_html=True
                        )
                    with c2:
                        if st.button("📖 复习", key=f"rev_{course.id}", use_container_width=True):
                            ss.current_course_id = course.id
                            ss.current_course = course
                            ss.current_slides = [s for s in course.slides]
                            ss.current_page = "review"
                            st.rerun()
                    with c3:
                        if st.button("🎙️ 继续上课", key=f"class_{course.id}", use_container_width=True):
                            ss.current_course_id = course.id
                            ss.current_course = course
                            ss.current_slides = [s for s in course.slides]
                            parser = get_parser()
                            slide_texts = [f"{s.get('title', '')} {s.get('content', '')}" for s in course.slides]
                            get_aligner().index_slides(slide_texts)
                            ss.current_page = "class"
                            st.rerun()
                    st.markdown("---")


def render_class():
    st.markdown('<h2 style="margin-bottom:1rem;">📚 上课模式</h2>', unsafe_allow_html=True)

    if "current_course_id" not in ss or not ss.current_course_id:
        st.warning("请先从主页选择或创建课程")
        if st.button("🏠 返回主页"):
            ss.current_page = "home"
            st.rerun()
        return

    storage = get_storage()
    course = storage.get_course(ss.current_course_id)
    if not course:
        st.error("课程不存在")
        ss.current_course_id = None
        st.rerun()
        return

    if "pending_transcripts" not in ss:
        ss.pending_transcripts = []
    if "class_log" not in ss:
        ss.class_log = list(course.transcripts)

    # 准备处理函数，所有录音方式（浏览器/上传/服务器）都走同一个处理逻辑
    transcriber = get_transcriber()
    aligner = get_aligner()
    translator = get_translator()
    slides = ss.current_slides

    def process_audio_bytes(audio_bytes: bytes, ext: str = ".wav"):
        """通用音频处理：保存临时文件 -> 转写 -> 翻译 -> 对齐 -> 入库 -> 展示"""
        if not audio_bytes or len(audio_bytes) < 100:
            return
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tf:
            tf.write(audio_bytes)
            temp_path = tf.name
        try:
            st.info(f"正在处理音频文件：{temp_path}，大小：{len(audio_bytes)} 字节...")
            text = transcriber.transcribe_file(temp_path)
            if not text or text.startswith("[转写失败]") or not text.strip():
                st.error(f"⚠️ 未能识别出有效文字：{text}")
                return
            text = text.strip()

            slide_page, confidence = aligner.find_best_match(text)
            slide_idx = slide_page - 1
            slide_ctx = ""
            slide_title = f"第 {slide_page} 页"
            if 0 <= slide_idx < len(slides):
                s = slides[slide_idx]
                slide_ctx = s.get("content", "") if isinstance(s, dict) else s.content
                slide_title = s.get("title", slide_title) if isinstance(s, dict) else s.title
            translated = translator.translate(text, slide_context=slide_ctx)
            segment = storage.create_segment(
                original=text,
                translated=translated,
                slide_page=slide_page,
                confidence=round(confidence, 3),
                slide_title=slide_title
            )
            storage.add_transcript(course.id, segment)
            ss.class_log.append(segment.to_dict())
            st.success(f"✅ 已识别并翻译：匹配 {slide_title} ({confidence:.0%})")
            with st.expander("查看详情"):
                st.markdown(f"🇬🇧 **原文**：{text}")
                st.markdown(f"🇨🇳 **译文**：{translated}")
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    col_ctl, col_info = st.columns([3, 2])

    with col_ctl:
        st.markdown("#### 🎙️ 流式同声传译")
        st.caption("💡 录完一段后，按钮会自动重置并准备好录下一段，实现分段连续同传。")
        
        # 恢复使用官方绝对稳定、不会消失的麦克风按钮
        audio_val = st.audio_input(
            "🎤 点击开始说话，停止后立即识别",
            key=f"audio_input_{ss.get('audio_key_counter', 0)}" # 动态 key，每次识别完强制刷新组件
        )
        
        if audio_val is not None:
            audio_bytes = audio_val.getvalue()
            audio_hash = hash(audio_bytes)
            if "last_realtime_hash" not in ss or ss.last_realtime_hash != audio_hash:
                ss.last_realtime_hash = audio_hash
                st.toast("⚡ 接收到音频，正在处理...", icon="⏳")
                process_audio_bytes(audio_bytes, ext=".wav")
                # 核心魔法：识别完成后，将 key 计数器 +1，这样网页刷新时麦克风组件会完全重置，立刻可以录下一句！
                ss.audio_key_counter = ss.get('audio_key_counter', 0) + 1
                st.rerun()
                
        st.markdown("---")
        # 方案 2：文件上传兜底（可以是已经录好的 mp3/wav/m4a 讲课录音）
        st.markdown("#### 📤 方案 2：上传录音文件（批量识别）")
        uploaded_audio = st.file_uploader(
            "上传已录好的音频文件 (wav / mp3 / webm / m4a / flac)",
            type=["wav", "mp3", "webm", "m4a", "flac", "ogg"],
        )
        if uploaded_audio is not None:
            st.audio(uploaded_audio)
            if st.button("🔍 识别并翻译这个文件", type="primary"):
                ext = os.path.splitext(uploaded_audio.name)[1] or ".wav"
                process_audio_bytes(uploaded_audio.getvalue(), ext=ext)
                st.rerun()

        # 方案 3：保留服务器本机录音（仅适合在这台电脑本机打开网页时用）
        with st.expander("🔧 方案 3：高级 - 服务器本机录音 (仅本机可用)", expanded=False):
            if "is_recording" not in ss:
                ss.is_recording = False
            if not ss.is_recording:
                if st.button("🔴 启动服务器本机录音", type="secondary", use_container_width=True):
                    ss.is_recording = True

                    def on_text(text):
                        slide_page, confidence = aligner.find_best_match(text)
                        slide_idx = slide_page - 1
                        slide_ctx = ""
                        slide_title = f"第 {slide_page} 页"
                        if 0 <= slide_idx < len(slides):
                            s = slides[slide_idx]
                            slide_ctx = s.get("content", "") if isinstance(s, dict) else s.content
                            slide_title = s.get("title", slide_title) if isinstance(s, dict) else s.title
                        translated = translator.translate(text, slide_context=slide_ctx)
                        segment = storage.create_segment(
                            original=text,
                            translated=translated,
                            slide_page=slide_page,
                            confidence=round(confidence, 3),
                            slide_title=slide_title
                        )
                        storage.add_transcript(course.id, segment)
                        ss.class_log.append(segment.to_dict())

                    def on_mic_error(err_msg):
                        st.toast(f"❌ {err_msg}", icon="❌")
                        ss.is_recording = False

                    transcriber.on_error = on_mic_error
                    transcriber.start_recording(on_transcribe=on_text, chunk_seconds=chunk_sec)
                    st.rerun()
            else:
                if st.button("⏹️ 停止服务器录音", type="secondary", use_container_width=True):
                    transcriber.stop_recording()
                    ss.is_recording = False
                    st.rerun()
                st.markdown('<span class="recording-dot"></span>服务器录音中...', unsafe_allow_html=True)

        st.markdown("---")

        st.markdown("#### 💬 实时记录")
        if not ss.class_log:
            st.info("还没有记录，开始录音试试吧！（手机上记得点「允许麦克风权限」哦）")
        else:
            for seg in reversed(ss.class_log):
                with st.container():
                    st.markdown(
                        f"<span class='page-tag'>第 {seg['slide_page']} 页</span>"
                        f"<span class='slide-title'>{seg['slide_title']}</span> "
                        f"<span class='timestamp'>{seg['timestamp']} "
                        f"(匹配度 {seg['confidence']:.0%})</span>",
                        unsafe_allow_html=True
                    )
                    st.markdown(f"<div class='original-text'>🇬🇧 {seg['original']}</div>",
                                unsafe_allow_html=True)
                    st.markdown(f"<div class='translated-text'>🇨🇳 {seg['translated']}</div>",
                                unsafe_allow_html=True)
                    st.markdown("---")

    with col_info:
        st.markdown("#### 📑 课件概览")
        if "current_slide_idx" not in ss:
            ss.current_slide_idx = 0

        slides = ss.current_slides
        total = len(slides)
        if total > 0:
            ss.current_slide_idx = st.slider("跳转到第 X 页", 1, total,
                                             ss.current_slide_idx + 1) - 1
            s = slides[ss.current_slide_idx]
            # 兼容字典和对象两种情况
            page_num = s.get('page_num') if isinstance(s, dict) else s.page_num
            title = s.get('title', '') if isinstance(s, dict) else s.title
            content = s.get('content', '') if isinstance(s, dict) else s.content
            
            with st.expander(f"📄 第 {page_num} 页 - {title}", expanded=True):
                st.markdown(f"**标题**：{title}")
                st.markdown(f"**内容**：\n{content[:800]}")
                if len(content) > 800:
                    st.markdown("...(内容过长，已截断)")

            st.markdown("#### 📌 本页讲解记录")
            page_segs = [t for t in ss.class_log if t["slide_page"] == page_num]
            if not page_segs:
                st.caption("当前页还没有讲解记录")
            else:
                for seg in page_segs:
                    st.markdown(
                        f"<div class='review-card'><b>{seg['timestamp']}</b><br>"
                        f"<i>原文：{seg['original']}</i><br>"
                        f"<b style='color:#1f77b4;'>译文：{seg['translated']}</b></div>",
                        unsafe_allow_html=True
                    )


def render_review():
    st.markdown('<h2 style="margin-bottom:1rem;">📖 复习模式</h2>', unsafe_allow_html=True)

    if "current_course_id" not in ss or not ss.current_course_id:
        st.warning("请先从主页选择课程")
        if st.button("🏠 返回主页"):
            ss.current_page = "home"
            st.rerun()
        return

    storage = get_storage()
    course = storage.get_course(ss.current_course_id)
    if not course:
        st.error("课程不存在")
        ss.current_course_id = None
        st.rerun()
        return

    st.markdown(f"### 📘 {course.name}")
    st.markdown(
        f"<span class='timestamp'>创建于 {course.created_at[:16].replace('T', ' ')} | "
        f"📑 {len(course.slides)} 页 | 💬 {len(course.transcripts)} 条讲解记录</span>",
        unsafe_allow_html=True
    )

    st.markdown("---")

    view_mode = st.radio("复习模式", ["📄 逐页复习", "📋 全部记录"], horizontal=True)

    if view_mode == "📄 逐页复习":
        slides = course.slides
        total = len(slides)
        if total == 0:
            st.info("该课程没有课件内容")
            return

        col1, col2 = st.columns([1, 4])
        with col1:
            page_num = st.number_input("页码", 1, total, 1) - 1
        with col2:
            st.markdown(f"#### 进度：{page_num + 1} / {total}")
            st.progress((page_num + 1) / total)

        s = slides[page_num]
        s_page_num = s.get('page_num') if isinstance(s, dict) else s.page_num
        s_title = s.get('title', '') if isinstance(s, dict) else s.title
        s_content = s.get('content', '') if isinstance(s, dict) else s.content
        s_full_text = s.get('full_text', s_content) if isinstance(s, dict) else s.full_text
        
        page_transcripts = storage.get_transcripts_by_page(course.id, s_page_num)

        col_content, col_chat = st.columns([3, 2])

        with col_content:
            with st.container(border=True):
                st.markdown(f"### 📄 第 {s_page_num} 页：{s_title}")
                st.markdown(s_full_text)

            st.markdown("#### 🎙️ 老师讲解记录")
            if not page_transcripts:
                st.info("这一页还没有讲解记录")
            else:
                for t in sorted(page_transcripts, key=lambda x: x["timestamp"]):
                    st.markdown(
                        f"<div class='transcript-box'>"
                        f"<span class='timestamp'>⏰ {t['timestamp']}</span><br>"
                        f"<div class='original-text'>🇬🇧 {t['original']}</div>"
                        f"<div class='translated-text'>🇨🇳 {t['translated']}</div>"
                        f"</div>",
                        unsafe_allow_html=True
                    )

        with col_chat:
            st.markdown("#### 🤖 AI 问答助手")
            st.caption("关于这页课件有问题？随时问我！")

            if "review_chat_history" not in ss:
                ss.review_chat_history = []

            for msg in ss.review_chat_history:
                with st.chat_message(msg["role"]):
                    st.write(msg["content"])

            user_q = st.chat_input("关于这页内容有什么疑问？")
            if user_q:
                ss.review_chat_history.append({"role": "user", "content": user_q})
                with st.chat_message("user"):
                    st.write(user_q)

                ctx = f"课件第 {s_page_num} 页标题：{s_title}\n内容：{s_content}\n\n"
                if page_transcripts:
                    ctx += "老师讲解：\n"
                    for t in page_transcripts[-5:]:
                        ctx += f"- {t['original']}\n  翻译：{t['translated']}\n"

                with st.chat_message("assistant"):
                    if Config.OPENAI_API_KEY:
                        try:
                            from openai import OpenAI
                            client = OpenAI(
                                api_key=Config.OPENAI_API_KEY,
                                base_url=Config.OPENAI_BASE_URL
                            )
                            resp = client.chat.completions.create(
                                model=Config.OPENAI_MODEL,
                                messages=[
                                    {"role": "system",
                                     "content": "你是一位耐心的教学助手。根据课件内容和老师的讲解，"
                                                "回答学生的疑问。如果信息不足，请坦诚说明。"
                                                "回答要清晰易懂，必要时举例说明。"},
                                    {"role": "user",
                                     "content": f"参考信息：\n{ctx[:2000]}\n\n学生问题：{user_q}"}
                                ],
                                temperature=0.5
                            )
                            answer = resp.choices[0].message.content
                            st.write(answer)
                            ss.review_chat_history.append({"role": "assistant", "content": answer})
                        except Exception as e:
                            st.error(f"回答出错: {e}")
                    else:
                        st.info("请先配置 OpenAI API Key 才能使用问答功能")

    else:
        st.markdown("#### 📋 全部讲解记录")
        if not course.transcripts:
            st.info("该课程还没有讲解记录")
        else:
            sorted_trans = sorted(course.transcripts, key=lambda x: x["timestamp"])
            for t in sorted_trans:
                with st.expander(
                    f"📄 第 {t['slide_page']} 页 | {t['slide_title']} | ⏰ {t['timestamp']}"
                ):
                    col_o, col_t = st.columns(2)
                    with col_o:
                        st.markdown("**原文 (Original)**")
                        st.info(t["original"])
                    with col_t:
                        st.markdown("**译文 (Translation)**")
                        st.success(t["translated"])
                    st.caption(f"匹配度：{t['confidence']:.0%}")

            st.markdown("---")
            st.markdown("#### 📊 统计")
            page_counts = {}
            for t in course.transcripts:
                p = t["slide_page"]
                page_counts[p] = page_counts.get(p, 0) + 1

            if page_counts:
                st.bar_chart(page_counts)


def render_settings():
    st.markdown('<h2 style="margin-bottom:1rem;">⚙️ 设置</h2>', unsafe_allow_html=True)

    st.markdown("#### 🔑 API 配置")
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

    current_key = Config.OPENAI_API_KEY
    if current_key:
        masked = current_key[:6] + "****" + current_key[-4:] if len(current_key) > 12 else "已配置"
        st.success(f"✅ OpenAI API Key: {masked}")
    else:
        st.warning("⚠️ OpenAI API Key 尚未配置")

    api_key = st.text_input("OpenAI API Key",
                            value=current_key,
                            type="password",
                            placeholder="sk-...")
    base_url = st.text_input("API Base URL",
                             value=Config.OPENAI_BASE_URL,
                             placeholder="https://api.openai.com/v1")
    model = st.text_input("模型", value=Config.OPENAI_MODEL)

    st.markdown("#### 🌐 语言设置")
    col_s, col_t = st.columns(2)
    with col_s:
        source_lang = st.text_input("源语言 (老师讲的语言)", value=Config.SOURCE_LANGUAGE)
    with col_t:
        target_lang = st.text_input("目标语言 (翻译为)", value=Config.TARGET_LANGUAGE)

    if st.button("💾 保存配置", type="primary"):
        lines = [
            f'OPENAI_API_KEY={api_key.strip()}\n',
            f'OPENAI_BASE_URL={base_url.strip()}\n',
            f'OPENAI_MODEL={model.strip()}\n',
            f'WHISPER_MODEL={Config.WHISPER_MODEL}\n',
            f'EMBEDDING_MODEL={Config.EMBEDDING_MODEL}\n',
            f'SOURCE_LANGUAGE={source_lang.strip()}\n',
            f'TARGET_LANGUAGE={target_lang.strip()}\n',
        ]
        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        st.success("✅ 配置已保存！重新加载页面以生效")
        time.sleep(1)
        st.rerun()

    st.markdown("---")
    st.markdown("#### 📁 数据管理")
    storage = get_storage()
    courses = storage.list_courses()
    st.markdown(f"共有 **{len(courses)}** 门课程，**{sum(len(c.transcripts) for c in courses)}** 条记录")

    if st.button("🧹 清理所有数据", type="secondary"):
        for c in courses:
            storage.delete_course(c.id)
        st.warning("所有数据已清理")
        time.sleep(1)
        st.rerun()


import base64
import streamlit.components.v1 as components

# 注册自定义流式音频组件
realtime_audio_path = os.path.join(os.path.dirname(__file__), "realtime_audio")
realtime_audio_component = components.declare_component("realtime_audio", path=realtime_audio_path)


def main():
    if "current_page" not in ss:
        ss.current_page = "home"

    page = render_sidebar()

    if ss.current_page != page:
        ss.current_page = page

    if ss.current_page == "home":
        render_home()
    elif ss.current_page == "class":
        render_class()
    elif ss.current_page == "review":
        render_review()
    elif ss.current_page == "settings":
        render_settings()


if __name__ == "__main__":
    main()
