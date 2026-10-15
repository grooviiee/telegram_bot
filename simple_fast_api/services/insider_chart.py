"""확인된 내부자 매매 수량을 월별·연별 그래프로 표시합니다."""
from io import BytesIO

import matplotlib
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.ticker import FuncFormatter

from config import PROFIT_CHART_FONT
from services.profit_chart import CHART_RENDER_LOCK


def render_insider_chart(data: dict) -> BytesIO:
    """월별 매수·매도와 3개년 합계 그래프를 PNG로 반환합니다."""
    with CHART_RENDER_LOCK, matplotlib.rc_context({'font.family': PROFIT_CHART_FONT, 'axes.unicode_minus': False}):
        fig = Figure(figsize=(13, 9), dpi=140, facecolor='#f5f7fb')
        FigureCanvasAgg(fig)
        monthly, annual = data['monthly'], data['annual']
        axes = fig.subplots(2, 1, gridspec_kw={'height_ratios': [1.5, 1]})
        for ax, rows, labels in (
            (axes[0], monthly, [r['month'][2:] for r in monthly]),
            (axes[1], annual, [str(r['year']) + (' (진행 중)' if r['partial_year'] else '') for r in annual]),
        ):
            x = list(range(len(rows)))
            for side, offset, color, label in (('buy', -.2, '#0eaa8a', '매수'), ('sell', .2, '#ef6375', '매도')):
                values = [r[side] if r[side] is not None else float('nan') for r in rows]
                ax.bar([i + offset for i in x], values, width=.38, color=color, label=label)
                if rows is annual:
                    for i, value in enumerate(values):
                        if value == value:
                            ax.annotate(f'{value:,.0f}', (i + offset, value), xytext=(0, 5), textcoords='offset points', ha='center', fontsize=10)
            ax.set_xticks(x, labels, rotation=60 if rows is monthly else 0, fontsize=9)
            ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f'{value:,.0f}'))
            ax.set_ylabel('주식 수량 (주)')
            ax.grid(axis='y', alpha=.2)
            ax.set_axisbelow(True)
            ax.spines[['top', 'right']].set_visible(False)
            ax.set_facecolor('white')
            ax.legend(frameon=False, ncol=2)
            ax.margins(y=.2)
        title = '내부자 주식 매수·매도 추이'
        if not data['coverage_complete']:
            title += ' (일부 공시만 확인)'
        fig.suptitle(f"{data['company_name']} | {title}", fontsize=19, fontweight='bold', y=.98)
        fig.text(.1, .925, f"{data['start_date']} ~ {data['end_date']} · 거래일 기준 · 보통주/우선주 합산", fontsize=10)
        note = (f"DART 최종 공시 {data['filings_parsed']:,}/{data['filings_total']:,}건 확인 | 증여·상속·보상 등 제외 | 올해는 조회일까지 집계")
        if not data['coverage_complete']:
            note += '\n미확인 공시/행 존재: 표시 수량은 확인분만의 하한이며, 빈 구간은 0을 의미하지 않습니다.'
        fig.text(.1, .025, note, fontsize=9, color='#687386')
        fig.subplots_adjust(left=.12, right=.97, top=.89, bottom=.1, hspace=.5)
        image = BytesIO()
        image.name = 'insider-trend.png'
        fig.savefig(image, format='png', facecolor=fig.get_facecolor())
        image.seek(0)
        return image
