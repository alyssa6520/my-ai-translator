import os
import json
import uuid
import shutil
from datetime import datetime
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, asdict, field
from config import Config


@dataclass
class TranscriptSegment:
    id: str
    timestamp: str
    original: str
    translated: str
    slide_page: int
    confidence: float
    slide_title: str

    def to_dict(self):
        return asdict(self)


@dataclass
class Course:
    id: str
    name: str
    created_at: str
    updated_at: str
    slide_filename: str
    slide_path: str
    slides: List[Dict[str, Any]]
    transcripts: List[Dict[str, Any]]

    def to_dict(self):
        return asdict(self)


class StorageManager:
    def __init__(self):
        self.courses_dir = Config.COURSES_DIR
        self.audio_dir = Config.AUDIO_DIR
        self._ensure_dirs()

    def _ensure_dirs(self):
        os.makedirs(self.courses_dir, exist_ok=True)
        os.makedirs(self.audio_dir, exist_ok=True)

    def _course_path(self, course_id: str) -> str:
        return os.path.join(self.courses_dir, course_id)

    def _course_data_path(self, course_id: str) -> str:
        return os.path.join(self._course_path(course_id), "course.json")

    def _course_slides_dir(self, course_id: str) -> str:
        return os.path.join(self._course_path(course_id), "slides")

    def create_course(self, name: str, slide_file_path: str,
                      slides_data: List[Dict[str, Any]]) -> Course:
        course_id = uuid.uuid4().hex[:12]
        course_dir = self._course_path(course_id)
        os.makedirs(course_dir, exist_ok=True)
        slides_dir = self._course_slides_dir(course_id)
        os.makedirs(slides_dir, exist_ok=True)

        slide_filename = os.path.basename(slide_file_path)
        dest_slide_path = os.path.join(slides_dir, slide_filename)
        if slide_file_path != dest_slide_path:
            shutil.copy2(slide_file_path, dest_slide_path)

        now = datetime.now().isoformat()
        course = Course(
            id=course_id,
            name=name,
            created_at=now,
            updated_at=now,
            slide_filename=slide_filename,
            slide_path=dest_slide_path,
            slides=slides_data,
            transcripts=[]
        )
        self._save_course(course)
        return course

    def _save_course(self, course: Course):
        course.updated_at = datetime.now().isoformat()
        with open(self._course_data_path(course.id), "w", encoding="utf-8") as f:
            json.dump(course.to_dict(), f, ensure_ascii=False, indent=2)

    def get_course(self, course_id: str) -> Optional[Course]:
        path = self._course_data_path(course_id)
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return Course(**data)

    def list_courses(self) -> List[Course]:
        courses = []
        if not os.path.exists(self.courses_dir):
            return courses
        for cid in os.listdir(self.courses_dir):
            c = self.get_course(cid)
            if c:
                courses.append(c)
        courses.sort(key=lambda x: x.updated_at, reverse=True)
        return courses

    def add_transcript(self, course_id: str, segment: TranscriptSegment) -> bool:
        course = self.get_course(course_id)
        if not course:
            return False
        course.transcripts.append(segment.to_dict())
        self._save_course(course)
        return True

    def add_transcripts_batch(self, course_id: str,
                              segments: List[TranscriptSegment]) -> bool:
        course = self.get_course(course_id)
        if not course:
            return False
        for seg in segments:
            course.transcripts.append(seg.to_dict())
        self._save_course(course)
        return True

    def get_transcripts_by_page(self, course_id: str,
                                page_num: int) -> List[Dict[str, Any]]:
        course = self.get_course(course_id)
        if not course:
            return []
        return [t for t in course.transcripts if t.get("slide_page") == page_num]

    def delete_course(self, course_id: str) -> bool:
        path = self._course_path(course_id)
        if os.path.exists(path):
            shutil.rmtree(path)
            return True
        return False

    def create_segment(self, original: str, translated: str,
                       slide_page: int, confidence: float,
                       slide_title: str) -> TranscriptSegment:
        return TranscriptSegment(
            id=uuid.uuid4().hex[:8],
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            original=original,
            translated=translated,
            slide_page=slide_page,
            confidence=confidence,
            slide_title=slide_title
        )
