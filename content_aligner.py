import numpy as np
from typing import List, Tuple, Optional
from config import Config


class ContentAligner:
    def __init__(self):
        self._embedding_model = None
        self._slide_embeddings: Optional[np.ndarray] = None
        self._slide_texts: List[str] = []
        self._last_page = 1

    def _load_embedding_model(self):
        if self._embedding_model is None:
            if Config.OPENAI_API_KEY:
                self._embedding_model = "openai"
            else:
                from sentence_transformers import SentenceTransformer
                self._embedding_model = SentenceTransformer(Config.EMBEDDING_MODEL)
        return self._embedding_model

    def _get_embeddings(self, texts: List[str]) -> np.ndarray:
        model = self._load_embedding_model()
        if model == "openai":
            from openai import OpenAI
            client = OpenAI(
                api_key=Config.OPENAI_API_KEY,
                base_url=Config.OPENAI_BASE_URL
            )
            all_embeds = []
            batch_size = 5
            for i in range(0, len(texts), batch_size):
                # 对输入文本进行硬截断，防止单页课件文字过多导致 token 超出限制 (bge-m3 限制通常在 512~8192 tokens，保守截断到 1500 字符)
                batch = [t[:1500] if isinstance(t, str) else t for t in texts[i:i + batch_size]]
                response = client.embeddings.create(
                    model=Config.EMBEDDING_MODEL,
                    input=batch
                )
                all_embeds.extend([d.embedding for d in response.data])
            return np.array(all_embeds)
        else:
            return model.encode(texts, show_progress_bar=False)

    def index_slides(self, slide_texts: List[str]):
        self._slide_texts = slide_texts
        if not slide_texts:
            self._slide_embeddings = np.empty((0, 0))
            return
        self._slide_embeddings = self._get_embeddings(slide_texts)
        self._last_page = 1

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> np.ndarray:
        if a.ndim == 1:
            a = a.reshape(1, -1)
        if b.ndim == 1:
            b = b.reshape(1, -1)
        a_norm = a / (np.linalg.norm(a, axis=1, keepdims=True) + 1e-8)
        b_norm = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-8)
        return a_norm @ b_norm.T

    def find_best_match(self, transcript_text: str,
                        continuity_bias: float = 0.15) -> Tuple[int, float]:
        if self._slide_embeddings is None or len(self._slide_texts) == 0:
            return 1, 0.0

        query_emb = self._get_embeddings([transcript_text])
        sims = self._cosine_similarity(query_emb, self._slide_embeddings)[0]

        if len(sims) > 1 and continuity_bias > 0:
            num_slides = len(sims)
            page_indices = np.arange(num_slides)
            last_idx = self._last_page - 1
            distance = np.abs(page_indices - last_idx)
            max_dist = num_slides - 1 if num_slides > 1 else 1
            bias = (1 - distance / max_dist) * continuity_bias
            scores = sims + bias
        else:
            scores = sims

        best_idx = int(np.argmax(scores))
        best_page = best_idx + 1
        best_score = float(sims[best_idx])

        self._last_page = best_page
        return best_page, best_score

    def find_top_matches(self, transcript_text: str,
                         top_k: int = 3) -> List[Tuple[int, float]]:
        if self._slide_embeddings is None or len(self._slide_texts) == 0:
            return []

        query_emb = self._get_embeddings([transcript_text])
        sims = self._cosine_similarity(query_emb, self._slide_embeddings)[0]

        top_indices = np.argsort(sims)[::-1][:top_k]
        return [(int(idx) + 1, float(sims[idx])) for idx in top_indices]
