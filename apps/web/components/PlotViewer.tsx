// 채점 결과(RunResult/StudyRunResult)의 plots 필드 — worker.py가 plt.show()를 가로채서
// base64로 인코딩해둔 그래프 이미지들 — 를 화면에 그려주는 컴포넌트.
export function PlotViewer({ plots }: { plots: string[] }) {
  if (plots.length === 0) {
    return <p className="p-4 text-sm text-[var(--muted)]">실행하면 그래프가 여기에 표시됩니다.</p>;
  }
  return (
    <div className="flex flex-col gap-3 p-3">
      {plots.map((b64, i) => (
        // eslint-disable-next-line @next/next/no-img-element
        // Next.js는 보통 최적화된 <Image> 컴포넌트를 쓰라고 권장하지만, 여긴 매번 새로 생성되는
        // base64 데이터(파일이 아니라 메모리상의 문자열)라 그 최적화 대상이 아니라서 평범한
        // <img>를 그대로 쓴다. src="data:image/png;base64,...." 형태의 "data URL"은 별도
        // 네트워크 요청 없이, 문자열 자체에 이미지 데이터를 통째로 담아 바로 렌더링하는 방식.
        <img key={i} src={`data:image/png;base64,${b64}`} alt={`plot-${i}`} className="max-w-full rounded-lg border border-[var(--border)] bg-white" />
        // bg-white: matplotlib 그래프는 보통 배경이 투명하거나 흰색을 기대하고 그려지므로,
        // 다크 테마에서 그래프 뒤에 어두운 배경이 비치지 않도록 흰 배경을 강제로 깔아준다.
      ))}
    </div>
  );
}
