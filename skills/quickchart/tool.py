from __future__ import annotations

import json
import logging
import urllib.parse

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def quickchart_generate(
    chart_type: str = "bar",
    labels: str = "A,B,C,D",
    data: str = "10,20,30,40",
    title: str = "",
) -> str:
    """Generate a chart image URL using QuickChart API.
    Returns a URL that can be embedded as an image.
    Args:
        chart_type: Chart type - bar, line, pie, doughnut, radar, polarArea (default: bar)
        labels: Comma-separated labels (e.g. '1월,2월,3월,4월')
        data: Comma-separated numeric values (e.g. '10,20,30,40')
        title: Optional chart title
    """
    try:
        label_list = [l.strip() for l in labels.split(",")]
        data_list = [float(d.strip()) for d in data.split(",")]

        chart_config = {
            "type": chart_type,
            "data": {
                "labels": label_list,
                "datasets": [{
                    "label": title or "Data",
                    "data": data_list,
                }],
            },
        }

        if title:
            chart_config["options"] = {
                "plugins": {"title": {"display": True, "text": title}},
            }

        config_json = json.dumps(chart_config)
        encoded = urllib.parse.quote(config_json)
        url = f"https://quickchart.io/chart?c={encoded}&w=600&h=400"

        return (
            f"📊 차트 생성 완료 ({chart_type})\n"
            f"제목: {title or '(없음)'}\n"
            f"데이터: {labels} → {data}\n"
            f"🔗 이미지 URL: {url}"
        )
    except Exception as e:
        logger.error("quickchart_generate failed: %s", e, exc_info=True)
        return f"차트 생성 실패: {e}"


def get_tools() -> list:
    return [quickchart_generate]
