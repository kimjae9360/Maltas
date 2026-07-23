import io
import sys
import threading
import traceback
import contextlib
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

class TimeoutException(Exception):
    pass

def _globaltrace(frame, event, arg):
    if event == 'call':
        return _localtrace
    return None

def _localtrace(frame, event, arg):
    if getattr(threading.current_thread(), "kill_received", False):
        raise TimeoutException("Execution timed out (30s limit).")
    return _localtrace

class CodeExecutor:
    """
    이유 (타임아웃 구현 방식):
    multiprocessing을 사용하면 무한루프 종료는 쉽지만, 생성된 matplotlib Figure 객체나 
    복잡한 pandas DataFrame(namespace)을 UI 프로세스와 공유(pickling)하는 것이 매우 까다롭습니다.
    따라서 동일 메모리(프로세스)를 공유하면서 무한루프를 끊을 수 있도록, 
    threading과 sys.settrace()를 이용한 타임아웃 방식을 선택했습니다. 
    (Windows에서는 signal.SIGALRM이 지원되지 않아 trace 기반 중단 사용)
    """
    def __init__(self, setup_code, working_dir=None):
        self.setup_code = setup_code
        self.working_dir = working_dir
        self.on_plot_callback = None
        self.on_console_callback = None
        
    def run_problem(self, problem_no, current_code, all_problems_up_to_here, timeout=30.0):
        namespace = {}
        stdout_capture = io.StringIO()
        
        def _mock_show(*args, **kwargs):
            if self.on_plot_callback:
                fig = plt.gcf()
                self.on_plot_callback(fig)
            plt.clf()
            
        original_show = plt.show
        plt.show = _mock_show
        
        code_blocks = [self.setup_code]
        for p_no in sorted(all_problems_up_to_here.keys(), key=int):
            if int(p_no) < problem_no:
                code_blocks.append(all_problems_up_to_here[p_no])
        
        code_blocks.append(current_code)
        full_code = "\n".join(code_blocks)
        
        result_container = {"error": None, "completed": False}
        
        def target():
            sys.settrace(_globaltrace)
            threading.current_thread().kill_received = False
            try:
                with contextlib.redirect_stdout(stdout_capture), contextlib.redirect_stderr(stdout_capture):
                    original_cwd = os.getcwd()
                    if self.working_dir:
                        os.chdir(self.working_dir)
                    try:
                        exec(full_code, namespace)
                        result_container["completed"] = True
                    finally:
                        if self.working_dir:
                            os.chdir(original_cwd)
            except TimeoutException as e:
                result_container["error"] = str(e)
                print(f"\n[Timeout Error] {str(e)}", file=stdout_capture)
            except Exception as e:
                result_container["error"] = traceback.format_exc()
                print(f"\n[Error]\n{result_container['error']}", file=stdout_capture)
            finally:
                sys.settrace(None)
                
        # daemon=True: settrace 기반 타임아웃은 C-level 대기/블로킹 호출은 끊지 못하므로,
        # 정말 못 끝나는 스레드가 생겨도 앱 종료 시 프로세스가 그것 때문에 남아있지 않게 합니다.
        t = threading.Thread(target=target, daemon=True)
        t.start()
        
        t.join(timeout)
        
        if t.is_alive():
            t.kill_received = True
            t.join(1.0)
            if t.is_alive():
                result_container["error"] = "Critical: Could not terminate thread."
                print("\n[Critical Timeout Error] Could not terminate thread.", file=stdout_capture)
                
        plt.show = original_show
        plt.close('all')
        
        output_text = stdout_capture.getvalue()
        if self.on_console_callback and output_text:
            self.on_console_callback(output_text)
            
        return namespace, output_text, result_container["error"]
