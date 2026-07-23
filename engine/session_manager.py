import os
import json
import time
from datetime import datetime
import threading
from pathlib import Path

class SessionManager:
    def __init__(self, sessions_dir="sessions"):
        self.sessions_dir = Path(sessions_dir)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        
        self.session_data = {}
        self.session_file = None

        self._auto_save_timer = None
        self._debounce_timer = None

        self._lock = threading.RLock()
        # 세션이 새로 생성/교체될 때마다 증가하는 세대(generation) 번호. 백그라운드 채점
        # 스레드가 시작할 때의 세대를 기억해뒀다가, 결과를 기록하기 직전에 지금 세대와
        # 비교하면 "실행 중에 reset_exam()으로 세션이 통째로 바뀐" 상황을 감지할 수 있습니다.
        self.generation = 0

    def create_new_session(self, exam_id, time_limit_minutes=90):
        with self._lock:
            now = datetime.now()
            timestamp = now.strftime("%Y%m%d_%H%M%S")
            self.session_file = self.sessions_dir / f"{exam_id}_{timestamp}.json"
            self.generation += 1

            self.session_data = {
                "exam_id": exam_id,
                "started_at": now.isoformat(),
                "elapsed_seconds": 0,
                "time_limit_minutes": time_limit_minutes,
                "current_problem_no": 1,
                "code_by_problem": {},
                "graded_results": {},
                "is_submitted": False
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
            
    def find_unfinished_sessions(self):
        unfinished = []
        for p in self.sessions_dir.glob("*.json"):
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # is_submitted가 True면(정상적으로 시간초과/수동 제출로 끝난 시험) 항상 완료로 취급합니다.
                # elapsed_seconds만으로 판단하면, 시간초과로 자동제출될 때 마지막 경과시간이
                # 저장되지 않는 경로가 있어 제출된 시험도 영원히 "미완료"로 오분류될 수 있습니다.
                if data.get("is_submitted", False):
                    continue
                if data.get("elapsed_seconds", 0) < data.get("time_limit_minutes", 90) * 60:
                    unfinished.append(p)
            except Exception:
                pass
        return sorted(unfinished, key=lambda x: x.stat().st_mtime, reverse=True)
        
    def update_state(self, elapsed_seconds=None, current_problem_no=None, code_updates=None, graded_updates=None):
        with self._lock:
            if elapsed_seconds is not None:
                self.session_data["elapsed_seconds"] = elapsed_seconds
            if current_problem_no is not None:
                self.session_data["current_problem_no"] = current_problem_no
                
            if code_updates:
                for p_no, code in code_updates.items():
                    self.session_data["code_by_problem"][str(p_no)] = code
                    
            if graded_updates:
                for p_no, res in graded_updates.items():
                    self.session_data["graded_results"][str(p_no)] = res

    def record_graded_result(self, problem_no, computed_entry, expected_generation=None):
        """백그라운드 채점 스레드가 계산한 결과를 기록합니다.

        run_current_code()는 실행 시작 시점의 "정답 보기 사용" 여부를 스냅샷으로 들고 있다가
        실행이 끝난 뒤(최대 180초 뒤) 그 결과를 기록하는데, 그 사이에 사용자가 "정답 보기"를
        눌러버리면 스냅샷이 낡은 값이 되어 잠금이 덮어써질 수 있습니다. 그래서 실제 기록(쓰기)
        시점에 락 안에서 다시 한번 확인해, 이미 "정답 보기 사용"으로 잠긴 문제라면 새로 계산된
        결과를 무시하고 잠금을 그대로 유지합니다.

        expected_generation을 넘기면, 실행이 시작된 이후 reset_exam() 등으로 세션 자체가
        통째로 교체(create_new_session/load_session)되었는지도 함께 확인해서, 그런 경우
        이전 세션을 향한 낡은 채점 결과가 새 세션에 잘못 섞여 들어가는 것을 막습니다.
        """
        with self._lock:
            if expected_generation is not None and expected_generation != self.generation:
                return
            key = str(problem_no)
            existing = self.session_data["graded_results"].get(key)
            if existing and existing.get("note") == "정답 보기 사용":
                return
            self.session_data["graded_results"][key] = computed_entry

    def mark_submitted(self):
        with self._lock:
            self.session_data["is_submitted"] = True

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
            
    def on_code_changed(self, problem_no, new_code):
        self.update_state(code_updates={problem_no: new_code})
        
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
