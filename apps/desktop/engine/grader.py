class Grader:
    def grade_problem(self, namespace, problem_spec):
        if problem_spec.get("manual_review", False) and not problem_spec.get("checks"):
            return True, "[본인이 직접 확인] 시각화 결과나 출력물을 직접 확인하세요."
            
        checks = problem_spec.get("checks", [])
        if not checks:
            return True, "✅ 정답입니다. (확인할 조건 없음)"
            
        for check in checks:
            var_name = check["var"]
            attr = check.get("attr", "")
            op = check.get("op", "eq")
            expected = check.get("expected")
            tolerance = check.get("tolerance", 1e-3)
            
            if var_name not in namespace:
                return False, f"❌ 변수 '{var_name}'를 찾을 수 없습니다."
                
            try:
                expr = f"{var_name}.{attr}" if attr else var_name
                actual = eval(expr, {}, namespace)
                
                if op == "eq":
                    # Convert to list for shape comparisons if necessary
                    if isinstance(actual, tuple) and isinstance(expected, list):
                        actual = list(actual)
                    if actual != expected:
                        return False, f"❌ '{expr}' 값이 일치하지 않습니다. (기대값: {expected}, 실제값: {actual})"
                elif op == "gte":
                    if not (actual >= expected):
                        return False, f"❌ '{expr}' 값이 {expected} 이상이어야 합니다. (실제값: {actual})"
                elif op == "lte":
                    if not (actual <= expected):
                        return False, f"❌ '{expr}' 값이 {expected} 이하여야 합니다. (실제값: {actual})"
                elif op == "close":
                    if not self._is_close(actual, expected, tolerance):
                        return False, f"❌ '{expr}' 값이 허용오차 내에 있지 않습니다. (기대값: {expected}, 실제값: {actual})"
                            
            except Exception as e:
                return False, f"❌ '{expr}' 평가 중 에러 발생: {str(e)}"
                
        return True, "✅ 정답입니다."

    @staticmethod
    def _is_close(actual, expected, tolerance):
        """숫자는 허용오차 내에서, 숫자로 변환할 수 없는 값(문자열 등)은 완전 일치로 비교합니다."""
        try:
            return abs(float(actual) - float(expected)) <= tolerance
        except (TypeError, ValueError):
            return actual == expected

    def report(self, results, total_points_v1):
        """
        results: list of tuples (question_no, points, is_correct)
        """
        if not results:
            return "아직 채점한 문제가 없습니다."
            
        earned_total = sum(p for _, p, c in results if c)
        
        pct = (earned_total / total_points_v1 * 100) if total_points_v1 else 0
        
        lines = []
        lines.append("\n=== 모의고사 채점 결과 ===")
        lines.append(f"획득 점수: {earned_total} / {total_points_v1} ({pct:.1f}%)")
        if pct >= 80:
            lines.append("결과: 합격 기준(80점) 통과! 실전 감각이 잘 잡혀 있습니다.")
        else:
            wrong = [q for q, p, c in results if not c]
            lines.append(f"결과: 합격 기준(80점) 미달. 틀린 문제: {wrong}")
            lines.append("해당 문제 번호의 이론을 다시 확인해보세요.")
            
        return "\n".join(lines)
