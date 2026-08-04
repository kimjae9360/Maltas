import pytest
import sys
import os
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.code_executor import CodeExecutor

def test_sequential_execution():
    setup_code = "a = 10"
    executor = CodeExecutor(setup_code)
    
    # Problem 1 creates variable b
    all_problems = {1: "b = a + 5"}
    namespace, output, err = executor.run_problem(1, "b = a + 5", {1: "b = a + 5"})
    assert err is None
    assert namespace["b"] == 15
    
    # Problem 2 references variable b from problem 1
    namespace2, output2, err2 = executor.run_problem(2, "c = b * 2", all_problems)
    assert err2 is None
    assert namespace2["c"] == 30

def test_sequential_execution_double_digit_order():
    # 세션에서 넘어오는 code_by_problem은 JSON을 거치며 항상 문자열 키가 됩니다.
    # "10"이 "2"보다 사전식으로 앞에 오는 버그가 있으면 실행 순서가 뒤섞여
    # order 리스트가 오름차순이 아니게 됩니다. (덧셈처럼 교환법칙이 성립하는
    # 연산으로는 이 버그를 못 잡으므로 append로 순서 자체를 기록해서 검증합니다.)
    setup_code = "order = []"
    executor = CodeExecutor(setup_code)

    all_problems = {}
    for i in range(1, 13):
        all_problems[str(i)] = f"order.append({i})"

    namespace, output, err = executor.run_problem(13, "order.append(13)", all_problems)
    assert err is None
    assert namespace["order"] == list(range(1, 14))

def test_infinite_loop_timeout():
    setup_code = ""
    executor = CodeExecutor(setup_code)
    
    start_time = time.time()
    # Using a 2-second timeout for testing to not wait 30 seconds
    namespace, output, err = executor.run_problem(1, "while True: pass", {}, timeout=2.0)
    elapsed = time.time() - start_time
    
    assert err is not None
    assert "Execution timed out" in err or "Execution timed out" in output
    assert elapsed < 4.0 # Should be killed shortly after 2 seconds

def test_plot_capture():
    setup_code = "import matplotlib.pyplot as plt\nimport seaborn as sns\nimport pandas as pd"
    executor = CodeExecutor(setup_code)
    
    captured_figs = []
    def mock_on_plot(fig):
        captured_figs.append(fig)
        
    executor.on_plot_callback = mock_on_plot
    
    code = "df = pd.DataFrame({'val': [1,2,3]})\nsns.histplot(df['val'])\nplt.show()"
    namespace, output, err = executor.run_problem(1, code, {})
    
    assert err is None
    assert len(captured_figs) == 1
    assert str(type(captured_figs[0])) == "<class 'matplotlib.figure.Figure'>"

if __name__ == "__main__":
    print("=== ?섎룞 ?쒓컖??罹≪쿂 ?뚯뒪??===")
    setup_code = "import matplotlib.pyplot as plt\nimport seaborn as sns\nimport pandas as pd"
    executor = CodeExecutor(setup_code)
    
    def manual_on_plot(fig):
        print(f"??肄쒕갚 ?몄텧 ?깃났! Figure 媛앹껜 罹≪쿂?? {fig}")
        print(f"??Figure ?ш린: {fig.get_size_inches()}, Axes 媛쒖닔: {len(fig.axes)}")
        
    executor.on_plot_callback = manual_on_plot
    
    code = "df = pd.DataFrame({'A': [1,2,3], 'B': [4,5,6]})\nsns.heatmap(df)\nplt.show()"
    print("肄붾뱶 ?ㅽ뻾 以?(sns.heatmap -> plt.show())...")
    ns, out, err = executor.run_problem(1, code, {})
    
    if err:
        print(f"???먮윭 諛쒖깮: {err}")
    else:
        print("???쒓컖??肄붾뱶 ?ㅽ뻾???먮윭 ?놁씠 ?꾨즺?섏뿀?듬땲??")
