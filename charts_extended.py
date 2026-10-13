"""전문 방송용 지표 차트 생성.

배경 차트 1장으로 반복하지 않도록, 같은 기간을 여러 각도로 보여주는
확장 지표 세트를 만든다. 전부 mplfinance 로 렌더.

생성물 (cache/<ticker>/):
    chart_price.png    캔들 + 거래량      (기세)
    chart_trend.png    추세선 + 이동평균   (방향)
    chart_momentum.png   RSI + MACD       (체력)
    chart_return.png   누적 수익률         (성과)
    chart_volatility.png 변동성 + 거래량비 (위험)
"""

from __future__ import annotations

from pathlib import Path

import config
from config import CACHE_DIR
from logger import log

_MPL_FONTS = [
    "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
    str(Path.home() / "Library/Fonts/NotoSansCJKkr-Regular.otf"),
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
]

_COLORS = {
    "up": "#FF3B30",
    "down": "#0A84FF",
    "accent": "#FFD60A",
    "grid": "#2A3550",
    "fg": "#F5F7FA",
    "dim": "#8FA3C8",
}


def _setup_font() -> str:
    import matplotlib.font_manager as fm

    for path in _MPL_FONTS:
        if Path(path).exists():
            try:
                fm.fontManager.addfont(path)
                return fm.FontProperties(fname=path).get_name()
            except Exception:
                continue
    return "AppleGothic"


def _base_rc(font: str, dpi: int) -> dict:
    return {
        "figure.dpi": dpi,
        "font.family": font,
        "font.sans-serif": [font, "Apple SD Gothic Neo"],
        "axes.unicode_minus": False,
        "axes.titlesize": 54,
        "axes.labelsize": 32,
        "xtick.labelsize": 26,
        "ytick.labelsize": 26,
        "legend.fontsize": 28,
        "text.color": _COLORS["fg"],
        "axes.labelcolor": _COLORS["dim"],
        "xtick.color": _COLORS["dim"],
        "ytick.color": _COLORS["dim"],
        "axes.edgecolor": _COLORS["grid"],
        "figure.facecolor": "none",
        "axes.facecolor": "none",
    }


def _save(fig, path: Path, dpi: int) -> str:
    import matplotlib.pyplot as plt

    fig.patch.set_alpha(0.0)
    path.parent.mkdir(parents=True, exist_ok=True)
    # bbox_inches 를 쓰면 4K 규격이 잘리므로 정확한 크기를 유지한다
    fig.savefig(path, dpi=dpi, transparent=True)
    plt.close(fig)
    return str(path)


def build_indicator_charts(hist, ticker: str, name: str, market: str = "KOSPI") -> list[str]:
    """확장 지표 세트를 생성한다. 실패해도 빈 목록을 돌려준다."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import pandas as pd

    try:
        import mplfinance as mpf
    except ImportError:
        log.warning("mplfinance 미설치 — 확장 차트 생략")
        return []

    if hist is None or len(hist) < 60:
        log.warning("%s 확장 차트: 데이터 부족", ticker)
        return []

    df = hist.copy()
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)

    rename = {"시가": "Open", "고가": "High", "저가": "Low", "종가": "Close", "거래량": "Volume"}
    missing = [k for k in rename if k not in df.columns]
    if missing:
        log.warning("%s 확장 차트: 컬럼 누락 %s", ticker, missing)
        return []
    df = df[list(rename)].rename(columns=rename)

    width, height = config.resolution()
    dpi = 100
    font = _setup_font()
    out_dir = CACHE_DIR / ticker
    paths: list[str] = []

    mpf_style = mpf.make_mpf_style(
        base_mpf_style="nightclouds",
        marketcolors=mpf.make_marketcolors(
            up=_COLORS["up"], down=_COLORS["down"], edge="inherit", wick="inherit", volume="in"
        ),
        gridcolor=_COLORS["grid"],
        figcolor="none",
        facecolor="none",
        rc=_base_rc(font, dpi),
    )

    with plt.rc_context(_base_rc(font, dpi)):
        # 1) 캔들 + 거래량
        try:
            fig, _ = mpf.plot(df, type="candlestick", volume=True, style=mpf_style,
                              title=f"{name} ({ticker}) · 가격",
                              figratio=(16, 9), figsize=(width / dpi, height / dpi),
                              returnfig=True)
            paths.append(_save(fig, out_dir / "chart_price.png", dpi))
        except Exception as exc:
            log.debug("%s 가격 차트 실패: %s", ticker, exc)

        # 2) 추세선 + 이동평균
        try:
            ma5 = df["Close"].rolling(5).mean()
            ma20 = df["Close"].rolling(20).mean()
            ma60 = df["Close"].rolling(60).mean()
            fig, _ = mpf.plot(df, type="line", style=mpf_style, volume=False,
                              mav=(5, 20, 60),
                              title=f"{name} ({ticker}) · 추세와 이동평균",
                              figratio=(16, 9), figsize=(width / dpi, height / dpi),
                              returnfig=True)
            paths.append(_save(fig, out_dir / "chart_trend.png", dpi))
        except Exception as exc:
            log.debug("%s 추세 차트 실패: %s", ticker, exc)

        # 3) RSI (체력)
        try:
            close = df["Close"]
            delta = close.diff()
            gain = delta.clip(lower=0).rolling(14).mean()
            loss = (-delta.clip(upper=0)).rolling(14).mean()
            rs = gain / loss.replace(0, float("nan"))
            rsi = 100 - (100 / (1 + rs))

            rsi_fig, (ax_r, ax_v) = plt.subplots(
                2, 1, figsize=(width / dpi, height / dpi),
                gridspec_kw={"height_ratios": [2.2, 1], "hspace": 0.06},
            )
            ax_r.plot(df.index, close, color=_COLORS["accent"], lw=2.5, label="종가")
            ax_r.fill_between(df.index, close, close.min() * 0.98, color=_COLORS["accent"], alpha=0.08)
            ax_r.set_title(f"{name} ({ticker}) · 가격 vs RSI", color=_COLORS["fg"],
                           fontsize=54, pad=24, loc="left")
            ax_r.legend(loc="upper left", facecolor="none", edgecolor="none", labelcolor=_COLORS["fg"])

            ax_v.plot(df.index, rsi, color="#BF5AF2", lw=2.2)
            ax_v.axhline(70, color=_COLORS["down"], ls="--", lw=1.6)
            ax_v.axhline(30, color=_COLORS["up"], ls="--", lw=1.6)
            ax_v.fill_between(df.index, 70, rsi, where=rsi >= 70, color=_COLORS["down"], alpha=0.25)
            ax_v.fill_between(df.index, 30, rsi, where=rsi <= 30, color=_COLORS["up"], alpha=0.25)
            ax_v.set_ylim(0, 100)
            ax_v.set_yticks([0, 30, 70, 100])
            ax_v.set_ylabel("RSI", color=_COLORS["dim"], labelpad=18)
            # 기준선 라벨을 축 바깥에 두어 tick 라벨과 겹치지 않게 한다
            ax_v.text(1.012, 0.70, "과매수 70", transform=ax_v.transAxes,
                      color=_COLORS["dim"], fontsize=24, va="center")
            ax_v.text(1.012, 0.30, "과매도 30", transform=ax_v.transAxes,
                      color=_COLORS["dim"], fontsize=24, va="center")

            for ax in (ax_r, ax_v):
                ax.grid(alpha=0.18, color=_COLORS["fg"])
                ax.tick_params(colors=_COLORS["dim"], labelsize=26)
                ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%m-%d"))
            paths.append(_save(rsi_fig, out_dir / "chart_momentum.png", dpi))
        except Exception as exc:
            log.debug("%s RSI 차트 실패: %s", ticker, exc)

        # 4) 누적 수익률
        try:
            ret = (df["Close"] / df["Close"].iloc[0] - 1) * 100
            vol_ma = df["Volume"].rolling(20).mean()

            fig2, (ax_a, ax_b) = plt.subplots(
                2, 1, figsize=(width / dpi, height / dpi),
                gridspec_kw={"height_ratios": [2, 1], "hspace": 0.08},
            )
            ax_a.plot(df.index, ret, color=_COLORS["up"] if ret.iloc[-1] >= 0 else _COLORS["down"], lw=2.8)
            ax_a.axhline(0, color=_COLORS["dim"], lw=1.4)
            ax_a.fill_between(df.index, ret, 0,
                              color=_COLORS["up"] if ret.iloc[-1] >= 0 else _COLORS["down"], alpha=0.14)
            ax_a.set_title(f"{name} ({ticker}) · 기간 수익률", color=_COLORS["fg"],
                           fontsize=54, pad=24, loc="left")
            ax_a.set_ylabel("수익률(%)", color=_COLORS["dim"])
            ax_a.text(df.index[-1], ret.iloc[-1], f"  {ret.iloc[-1]:+.0f}%",
                      color=_COLORS["accent"], fontsize=40, fontweight="bold", va="center")

            ax_b.bar(df.index, df["Volume"] / 1e6, width=1.6, color=_COLORS["dim"], alpha=0.55)
            ax_b.plot(df.index, vol_ma / 1e6, color=_COLORS["accent"], lw=2.2, label="20일 평균")
            ax_b.set_ylabel("거래량(백만주)", color=_COLORS["dim"])
            ax_b.legend(loc="upper left", facecolor="none", edgecolor="none", labelcolor=_COLORS["fg"])

            for ax in (ax_a, ax_b):
                ax.grid(alpha=0.18, color=_COLORS["fg"])
                ax.tick_params(colors=_COLORS["dim"], labelsize=26)
                ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%m-%d"))
            paths.append(_save(fig2, out_dir / "chart_return.png", dpi))
        except Exception as exc:
            log.debug("%s 수익률 차트 실패: %s", ticker, exc)

    if paths:
        log.info("확장 지표 차트 %d종 생성: %s", len(paths), ", ".join(Path(p).name for p in paths))
    return paths
