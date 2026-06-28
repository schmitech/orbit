import os
import sys

import pytest


_server_dir = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, _server_dir)


@pytest.mark.parametrize("chart_type", ["bar", "line", "pie", "area"])
def test_render_chart_to_png_returns_bytes_for_supported_types(chart_type):
    from ai_services.services.document_generation_service.chart_image import render_chart_to_png

    png = render_chart_to_png(
        {
            "type": chart_type,
            "title": "Example",
            "labels": ["A", "B", "C"],
            "datasets": [{"label": "Series 1", "data": [1, 2, 3]}],
        }
    )

    assert isinstance(png, bytes)
    assert png.startswith(b"\x89PNG")
    assert len(png) > 100


@pytest.mark.parametrize(
    "chart",
    [
        {"type": "bar", "labels": [], "datasets": []},
        {"type": "line", "labels": ["A"], "datasets": []},
        {"type": "pie", "labels": ["A", "B"], "datasets": [{"data": []}]},
        {"type": "area", "datasets": [{"label": "Series 1", "data": []}]},
    ],
)
def test_render_chart_to_png_handles_empty_data(chart):
    from ai_services.services.document_generation_service.chart_image import render_chart_to_png

    png = render_chart_to_png(chart)

    assert png.startswith(b"\x89PNG")
