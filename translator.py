import json
from typing import List, Optional, Dict
from collections import deque
from config import Config


class Translator:
    def __init__(self, context_window: int = 10):
        self.context_window = context_window
        self._history: deque = deque(maxlen=context_window)
        self._glossary: Dict[str, str] = {}

    def set_glossary(self, glossary: Dict[str, str]):
        self._glossary = glossary

    def add_to_history(self, original: str, translated: str):
        self._history.append({"original": original, "translated": translated})

    def clear_history(self):
        self._history.clear()

    def _build_glossary_prompt(self) -> str:
        if not self._glossary:
            return ""
        items = "\n".join(f'- "{k}" => "{v}"' for k, v in self._glossary.items())
        return f"\n\n术语对照表（请严格遵守）：\n{items}"

    def _build_context_prompt(self) -> str:
        if not self._history:
            return ""
        lines = []
        for i, item in enumerate(self._history):
            lines.append(f"{i + 1}. 原文: {item['original']}\n   译文: {item['translated']}")
        return "\n\n上文上下文：\n" + "\n".join(lines)

    def translate(self, text: str, source_lang: Optional[str] = None,
                  target_lang: Optional[str] = None, slide_context: Optional[str] = None) -> str:
        if not text.strip():
            return ""

        source_lang = source_lang or Config.SOURCE_LANGUAGE
        target_lang = target_lang or Config.TARGET_LANGUAGE

        if source_lang.split("-")[0] == target_lang.split("-")[0]:
            return text

        if not Config.OPENAI_API_KEY:
            return f"[需要配置 OPENAI_API_KEY 来翻译] {text}"

        try:
            from openai import OpenAI
            client = OpenAI(
                api_key=Config.OPENAI_API_KEY,
                base_url=Config.OPENAI_BASE_URL
            )

            slide_prompt = ""
            if slide_context:
                slide_prompt = f"\n\n当前课件页内容参考（帮助理解语境）：\n{slide_context[:500]}"

            glossary_prompt = self._build_glossary_prompt()
            context_prompt = self._build_context_prompt()

            system_prompt = (
                f"You are a professional simultaneous interpreter for educational lectures. "
                f"Translate from {source_lang} to {target_lang}. "
                f"Requirements:\n"
                f"1. Keep the meaning accurate and natural in the target language\n"
                f"2. Preserve academic and technical terminology correctly\n"
                f"3. Maintain spoken-language fluency, not literal translation\n"
                f"4. Keep the translation concise, suitable for simultaneous interpretation\n"
                f"5. Output ONLY the translated text, no explanations or metadata"
                f"{glossary_prompt}"
                f"{context_prompt}"
                f"{slide_prompt}"
            )

            user_prompt = f"Translate the following text:\n\n{text}"

            response = client.chat.completions.create(
                model=Config.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=1000
            )

            result = response.choices[0].message.content.strip()
            self.add_to_history(text, result)
            return result
        except Exception as e:
            print(f"翻译失败: {e}")
            return f"[翻译失败: {e}] {text}"

    def translate_batch(self, texts: List[str], source_lang: Optional[str] = None,
                        target_lang: Optional[str] = None,
                        slide_contexts: Optional[List[Optional[str]]] = None) -> List[str]:
        results = []
        for i, text in enumerate(texts):
            ctx = slide_contexts[i] if slide_contexts and i < len(slide_contexts) else None
            results.append(self.translate(text, source_lang, target_lang, ctx))
        return results
