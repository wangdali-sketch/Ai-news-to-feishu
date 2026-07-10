"""AI 前沿信息雷达的多来源采集器。"""

from .arxiv_collector import collect_arxiv
from .github_collector import collect_github
from .manual_link_collector import collect_manual_links
from .rss_collector import collect_rss
from .social_collector import collect_social
from .web_collector import collect_web_sources

__all__ = [
    "collect_arxiv",
    "collect_github",
    "collect_manual_links",
    "collect_rss",
    "collect_social",
    "collect_web_sources",
]
