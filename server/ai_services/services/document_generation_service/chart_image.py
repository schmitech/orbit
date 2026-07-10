"""Convert document chart specs to PNG images."""

import io
from numbers import Number
from typing import Any, Dict, Iterable, List

import matplotlib
import matplotlib.ticker as ticker

matplotlib.use("Agg")

# Logical layout DPI — controls figure proportions.
# Output pixel count = (width_px / _LAYOUT_DPI) * dpi  (see render_chart_to_png).
_LAYOUT_DPI = 96

COLORS = ["#6366f1", "#06b6d4", "#f59e0b", "#ec4899", "#10b981", "#8b5cf6", "#f97316"]


def _numeric_series(values: Iterable[Any], length: int) -> List[float]:
    series = []
    for value in list(values)[:length]:
        if isinstance(value, Number):
            series.append(float(value))
            continue
        try:
            series.append(float(value))
        except (TypeError, ValueError):
            series.append(0.0)
    while len(series) < length:
        series.append(0.0)
    return series


def _compact_formatter(x: float, _pos: int) -> str:
    """Format large axis tick values as compact strings (3.8M, 420K, etc.)."""
    if abs(x) >= 1_000_000:
        return f"{x / 1_000_000:.1f}M"
    if abs(x) >= 1_000:
        return f"{x / 1_000:.0f}K"
    return f"{x:g}"


def _apply_compact_formatter(ax) -> None:
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(_compact_formatter))


def _label_rotation(labels: List[str]) -> int:
    """Pick an x-axis label rotation that avoids overlap.

    Rotating only past 6 categories ignores label *length* — a handful of long
    labels (e.g. "United Kingdom", "United States") overlap horizontally just
    as easily as many short ones.
    """
    if len(labels) > 6:
        return 30
    avg_len = sum(len(label) for label in labels) / max(len(labels), 1)
    return 30 if avg_len > 8 else 0


def render_chart_to_png(
    chart: Dict[str, Any],
    width_px: int = 600,
    height_px: int = 350,
    dpi: int = 150,
) -> bytes:
    """Render a chart spec to PNG bytes using matplotlib.

    Output pixel dimensions = (width_px / _LAYOUT_DPI * dpi) × (height_px / _LAYOUT_DPI * dpi).
    Increasing dpi above _LAYOUT_DPI (96) produces a higher-resolution PNG suitable for
    embedding in PDF/DOCX/PPTX without pixelation.
    """
    import matplotlib.pyplot as plt

    chart_type = str(chart.get("type") or "bar").lower()
    title = str(chart.get("title") or "")
    labels = [str(label) for label in chart.get("labels") or []]
    raw_datasets = chart.get("datasets") or []
    datasets = [ds for ds in raw_datasets if isinstance(ds, dict)]

    figsize = (width_px / _LAYOUT_DPI, height_px / _LAYOUT_DPI)
    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)

    if not labels:
        max_len = max((len(ds.get("data") or []) for ds in datasets), default=0)
        labels = [str(idx + 1) for idx in range(max_len)]

    if not labels or not datasets:
        ax.text(0.5, 0.5, "No chart data", ha="center", va="center", transform=ax.transAxes)
        ax.set_xticks([])
        ax.set_yticks([])
    elif chart_type == "pie":
        data = _numeric_series(datasets[0].get("data") or [], len(labels))
        if sum(abs(v) for v in data) == 0:
            ax.text(0.5, 0.5, "No chart data", ha="center", va="center", transform=ax.transAxes)
            ax.set_xticks([])
            ax.set_yticks([])
        else:
            ax.pie(data, labels=labels, autopct="%1.1f%%", colors=COLORS[:len(data)])
    elif chart_type == "line":
        for idx, ds in enumerate(datasets):
            data = _numeric_series(ds.get("data") or [], len(labels))
            ax.plot(labels, data, label=ds.get("label"),
                    color=COLORS[idx % len(COLORS)], marker="o", linewidth=2)
        ax.legend()
        ax.grid(axis="y", linestyle="--", alpha=0.5)
        _apply_compact_formatter(ax)
    elif chart_type == "area":
        x_values = range(len(labels))
        for idx, ds in enumerate(datasets):
            data = _numeric_series(ds.get("data") or [], len(labels))
            ax.fill_between(x_values, data, alpha=0.4,
                            color=COLORS[idx % len(COLORS)], label=ds.get("label"))
            ax.plot(x_values, data, color=COLORS[idx % len(COLORS)], linewidth=2)
        ax.set_xticks(list(x_values))
        ax.set_xticklabels(labels)
        ax.legend()
        ax.grid(axis="y", linestyle="--", alpha=0.5)
        _apply_compact_formatter(ax)
    elif chart_type == "composed":
        _render_composed(ax, fig, labels, datasets)
    else:  # bar (default)
        _render_bar(ax, labels, datasets)

    if title:
        ax.set_title(title, fontsize=12, fontweight="bold", pad=10)

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def _render_bar(ax, labels: List[str], datasets: List[Dict[str, Any]]) -> None:
    n_datasets = len(datasets)
    n_labels = len(labels)
    bar_width = 0.8 / max(n_datasets, 1)
    x_values = range(n_labels)
    for idx, ds in enumerate(datasets):
        data = _numeric_series(ds.get("data") or [], n_labels)
        offsets = [i + idx * bar_width - (n_datasets - 1) * bar_width / 2 for i in x_values]
        ax.bar(offsets, data, width=bar_width * 0.9,
               label=ds.get("label"), color=COLORS[idx % len(COLORS)])
    ax.set_xticks(list(x_values))
    ax.set_xticklabels(labels, rotation=_label_rotation(labels), ha="right")
    if n_datasets > 1:
        ax.legend()
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    _apply_compact_formatter(ax)


def _render_composed(ax, fig, labels: List[str], datasets: List[Dict[str, Any]]) -> None:
    """Render a composed chart: mixed bar/line series with optional dual y-axes."""
    import matplotlib.pyplot as plt

    right_ds = [ds for ds in datasets if ds.get("yAxisId") == "right"]
    ax2 = ax.twinx() if right_ds else None

    n_bar_left = sum(
        1 for ds in datasets
        if ds.get("type", "bar") == "bar" and ds.get("yAxisId", "left") == "left"
    )
    bar_left_idx = 0

    x_positions = list(range(len(labels)))
    bar_width = 0.8 / max(n_bar_left, 1)

    for global_idx, ds in enumerate(datasets):
        series_type = str(ds.get("type") or "bar").lower()
        y_axis_id = str(ds.get("yAxisId") or "left").lower()
        target_ax = ax2 if (ax2 and y_axis_id == "right") else ax
        data = _numeric_series(ds.get("data") or [], len(labels))
        color = COLORS[global_idx % len(COLORS)]
        label_text = ds.get("label") or f"Series {global_idx + 1}"

        if series_type == "line":
            target_ax.plot(labels, data, label=label_text, color=color, marker="o", linewidth=2)
        else:  # bar
            offsets = [
                i + bar_left_idx * bar_width - (n_bar_left - 1) * bar_width / 2
                for i in x_positions
            ]
            target_ax.bar(offsets, data, width=bar_width * 0.9,
                          label=label_text, color=color)
            bar_left_idx += 1

    ax.set_xticks(x_positions)
    ax.set_xticklabels(labels, rotation=_label_rotation(labels), ha="right")
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    _apply_compact_formatter(ax)
    if ax2:
        _apply_compact_formatter(ax2)
        ax2.spines["top"].set_visible(False)

    # Merge legends from both axes into one
    handles, labs = ax.get_legend_handles_labels()
    if ax2:
        h2, l2 = ax2.get_legend_handles_labels()
        handles, labs = handles + h2, labs + l2
    if handles:
        ax.legend(handles, labs, loc="upper right")
