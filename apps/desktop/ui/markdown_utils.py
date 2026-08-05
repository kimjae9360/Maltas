"""study_window.py와 main_window.py가 공통으로 쓰는 마크다운 후처리 헬퍼.

문제 지문/이론 설명은 markdown 패키지로 HTML을 만든 뒤 QTextBrowser에 그대로 보여주는데,
그 중 인라인 코드(백틱)만 클릭하면 클립보드로 복사되는 기능을 두 창 모두에 붙이기 위해
로직을 한 곳에 모았다."""
import html as html_mod
import re
from urllib.parse import quote, unquote

# 인라인 코드(`text`)만 매칭하고 블록 코드(<pre><code>...)는 건너뛴다 — fenced_code 확장을 쓰면
# 블록 코드는 항상 <pre><code>가 붙어서 나오므로, 바로 앞에 <pre>가 없는 <code>만 인라인이다.
_INLINE_CODE_RE = re.compile(r'(?<!<pre>)<code>(.*?)</code>', re.S)


def make_code_copyable(html):
    """실제 시험처럼 파일명·컬럼명 등을 오타 없이 붙여넣을 수 있도록, 지문 안의 인라인
    코드(백틱)를 클릭하면 클립보드로 복사되는 링크로 감싼다. QTextBrowser는 <a href>만
    클릭 이벤트(anchorClicked)를 주므로, href에 "copy:<url인코딩된 원문>"을 실어 보낸다."""
    def _replace(m):
        inner_html = m.group(1)
        plain_text = html_mod.unescape(re.sub(r'<[^>]+>', '', inner_html))
        href = quote(plain_text, safe='')
        return (f'<a href="copy:{href}" title="클릭하면 복사됩니다" '
                f'style="text-decoration:none; color:inherit;"><code>{inner_html}</code></a>')
    return _INLINE_CODE_RE.sub(_replace, html)


def extract_copy_text(anchor_url):
    """anchorClicked가 준 QUrl(문자열 변환됨)에서 copy: 접두어를 걷어내고 복사할 원문을 돌려준다.
    copy: 링크가 아니면(예: 일반 외부 링크) None을 돌려준다."""
    href = anchor_url.toString() if hasattr(anchor_url, "toString") else str(anchor_url)
    if not href.startswith("copy:"):
        return None
    return unquote(href[len("copy:"):])
