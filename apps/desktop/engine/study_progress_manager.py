import json
import threading
from datetime import datetime
from pathlib import Path


class StudyProgressManager:
    """학습 모드 전용 진행상황 저장/복구.

    SessionManager(모의고사)와 동일한 영속화 메커니즘(원자적 tmp write, 디바운스 저장,
    주기 저장)을 쓰지만 스키마는 다릅니다 — 타이머/점수 대신 섹션 진행도와 오답 리스트를 추적합니다.
    파일명은 "study_" 접두사를 써서 모의고사 세션 파일과 섞이지 않게 합니다.
    """

    def __init__(self, sessions_dir="sessions"):
        self.sessions_dir = Path(sessions_dir)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

        self.session_data = {}
        self.session_file = None

        self._auto_save_timer = None
        self._debounce_timer = None

        self._lock = threading.RLock()
        self.generation = 0

    def create_new_session(self, chapter_id):
        with self._lock:
            now = datetime.now()
            timestamp = now.strftime("%Y%m%d_%H%M%S")
            self.session_file = self.sessions_dir / f"study_{chapter_id}_{timestamp}.json"
            self.generation += 1

            self.session_data = {
                "chapter_id": chapter_id,
                "started_at": now.isoformat(),
                "current_section_no": 1,
                "practice_code_by_id": {},
                "practice_results_by_id": {},
                "wrong_practice_ids": [],
                "revealed_practice_ids": [],
                "completed_sections": [],
                "is_completed": False,
            }
            self._save_to_disk()

    def load_session(self, session_filepath):
        with self._lock:
            with open(session_filepath, 'r', encoding='utf-8') as f:
                self.session_data = json.load(f)
            self.session_file = Path(session_filepath)
            self.generation += 1

    def get_generation(self):
        with self._lock:
            return self.generation

    def find_unfinished_sessions(self, chapter_id=None):
        unfinished = []
        for p in self.sessions_dir.glob("study_*.json"):
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if data.get("is_completed", False):
                    continue
                if chapter_id is not None and data.get("chapter_id") != chapter_id:
                    continue
                unfinished.append(p)
            except Exception:
                pass
        return sorted(unfinished, key=lambda x: x.stat().st_mtime, reverse=True)

    def update_state(self, current_section_no=None, code_updates=None):
        with self._lock:
            if current_section_no is not None:
                self.session_data["current_section_no"] = current_section_no
            if code_updates:
                for practice_id, code in code_updates.items():
                    self.session_data["practice_code_by_id"][practice_id] = code

    def record_result(self, practice_id, is_correct, revealed_answer=False):
        """practice_id 형식: "<section_no>-<practice_no>" (예: "1-1")."""
        with self._lock:
            existing = self.session_data["practice_results_by_id"].get(practice_id, {})
            attempts = existing.get("attempts", 0) + 1
            self.session_data["practice_results_by_id"][practice_id] = {
                "is_correct": is_correct,
                "attempts": attempts,
                "revealed_answer": revealed_answer,
            }
            wrong_ids = self.session_data["wrong_practice_ids"]
            solved_independently = is_correct and not revealed_answer
            if solved_independently and practice_id in wrong_ids:
                wrong_ids.remove(practice_id)
            elif not solved_independently and practice_id not in wrong_ids:
                wrong_ids.append(practice_id)

    def is_revealed(self, practice_id):
        with self._lock:
            return practice_id in self.session_data.get("revealed_practice_ids", [])

    def mark_revealed(self, practice_id):
        with self._lock:
            ids = self.session_data.setdefault("revealed_practice_ids", [])
            if practice_id not in ids:
                ids.append(practice_id)

    def update_practice_result_only(self, practice_id, is_correct):
        """복습 모드 재도전 결과만 기록합니다 (record_result와 달리 wrong_practice_ids를
        건드리지 않음 — 복습 모드는 정답 시 remove_from_wrong_list로 명시적으로 빼줍니다)."""
        with self._lock:
            existing = self.session_data["practice_results_by_id"].get(practice_id, {})
            attempts = existing.get("attempts", 0) + 1
            revealed = existing.get("revealed_answer", False)
            self.session_data["practice_results_by_id"][practice_id] = {
                "is_correct": is_correct,
                "attempts": attempts,
                "revealed_answer": revealed,
            }

    def remove_from_wrong_list(self, practice_id):
        with self._lock:
            ids = self.session_data.get("wrong_practice_ids", [])
            if practice_id in ids:
                ids.remove(practice_id)

    def ensure_in_wrong_list(self, practice_id):
        with self._lock:
            ids = self.session_data.setdefault("wrong_practice_ids", [])
            if practice_id not in ids:
                ids.append(practice_id)

    def mark_section_completed(self, section_no):
        with self._lock:
            if section_no not in self.session_data["completed_sections"]:
                self.session_data["completed_sections"].append(section_no)

    def mark_chapter_completed(self):
        with self._lock:
            self.session_data["is_completed"] = True

    def _save_to_disk(self):
        if not self.session_file:
            return
        temp_file = self.session_file.with_suffix('.tmp')
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(self.session_data, f, ensure_ascii=False, indent=2)
        temp_file.replace(self.session_file)

    def save_now(self):
        with self._lock:
            self._save_to_disk()

    def start_auto_save(self, interval=60.0):
        self.stop_auto_save()

        def _auto_save():
            self.save_now()
            self._auto_save_timer = threading.Timer(interval, _auto_save)
            self._auto_save_timer.daemon = True
            self._auto_save_timer.start()

        self._auto_save_timer = threading.Timer(interval, _auto_save)
        self._auto_save_timer.daemon = True
        self._auto_save_timer.start()

    def stop_auto_save(self):
        if self._auto_save_timer:
            self._auto_save_timer.cancel()
            self._auto_save_timer = None

    def on_code_changed(self, practice_id, new_code):
        self.update_state(code_updates={practice_id: new_code})

        if self._debounce_timer:
            self._debounce_timer.cancel()

        def _debounce_save():
            self.save_now()

        self._debounce_timer = threading.Timer(5.0, _debounce_save)
        self._debounce_timer.daemon = True
        self._debounce_timer.start()

    def stop_all(self):
        self.stop_auto_save()
        if self._debounce_timer:
            self._debounce_timer.cancel()

    def get_data(self):
        with self._lock:
            return dict(self.session_data)
