"""분기 수익성 시계열을 텔레그램용 PNG로 렌더링합니다."""
from io import BytesIO
from threading import Lock

import matplotlib
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.ticker import FuncFormatter

from config import PROFIT_CHART_FONT

_render_lock = Lock()


def render_profit_chart(company: str, rows: list[dict]) -> BytesIO:
    """매출·영업이익, 이익률, 전년 동기 성장률 그래프를 PNG로 반환합니다."""
    # matplotlib의 전역 폰트 설정과 동시 렌더링을 같은 잠금으로 보호합니다.
    with _render_lock, matplotlib.rc_context({'font.family': PROFIT_CHART_FONT, 'axes.unicode_minus': False}):
        fig = Figure(figsize=(12, 10), dpi=140, facecolor='#f5f7fb')
        FigureCanvasAgg(fig)
        axes = fig.subplots(3, 1, sharex=True, gridspec_kw={'height_ratios': [1.4, 1, 1]})
        x = list(range(len(rows)))

        def values(key: str, scale: float = 1) -> list[float]:
            return [row[key] / scale if row.get(key) is not None else float('nan') for row in rows]

        # 매출과 영업이익의 규모 차이를 이중 축 대신 독립 막대로 명확히 표시합니다.
        axes[0].bar([i - .2 for i in x], values('revenue', 1e8), width=.38, color='#4169e1', label='매출액')
        axes[0].bar([i + .2 for i in x], values('operating_income', 1e8), width=.38, color='#0eaa8a', label='영업이익')
        axes[0].set_ylabel('금액 (억원)')
        axes[0].yaxis.set_major_formatter(FuncFormatter(lambda v, _: f'{v:,.0f}'))
        axes[0].legend(loc='upper left', frameon=False, ncol=2)
        for ax, key, title, color in (
            (axes[1], 'operating_margin', '영업이익률 (%)', '#0eaa8a'),
            (axes[2], 'revenue_yoy', '매출 성장률 / YoY (%)', '#8054ce'),
        ):
            ys = values(key)
            ax.plot(x, ys, color=color, marker='o', linewidth=2)
            ax.set_ylabel(title)
            for i, value in enumerate(ys):
                if value == value:
                    ax.annotate(f'{value:.1f}', (i, value), xytext=(0, 7), textcoords='offset points', ha='center', fontsize=8)
            if all(value != value for value in ys):
                ax.text(.5, .5, '데이터 부족', transform=ax.transAxes, ha='center', color='#687386')
            ax.margins(y=.25)
        for ax in axes:
            ax.set_facecolor('white')
            ax.axhline(0, color='#929baa', linewidth=.7)
            ax.grid(axis='y', alpha=.2)
            ax.set_axisbelow(True)
            ax.spines[['top', 'right']].set_visible(False)
        axes[-1].set_xticks(x, [r['label'].replace(' ', '\n') for r in rows], fontsize=9)
        fig.suptitle(f'{company} | 최근 3년 분기별 수익성·성장성', fontsize=19, fontweight='bold', y=.98)
        fig.text(.07, .025, '출처: DART | 4분기 = 연간 - 3분기 누적 | 빈 구간 = 데이터 부족 (0이 아님)', fontsize=9, color='#687386')
        fig.subplots_adjust(left=.11, right=.97, top=.93, bottom=.09, hspace=.18)
        image = BytesIO()
        image.name = 'quarterly-profit.png'
        fig.savefig(image, format='png', facecolor=fig.get_facecolor())
        image.seek(0)
        return image
