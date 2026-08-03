from typing import List, Optional

from .base import ScraperStrategy
from .facebook import FacebookScraper
from .instagram import InstagramScraper

# Order matters only in that the first match wins - with today's two
# strategies matching disjoint hostnames that never comes up, but a future
# catch-all strategy (e.g. generic Open Graph fallback for any site) should
# be appended last.
STRATEGIES: List[ScraperStrategy] = [
    InstagramScraper(),
    FacebookScraper(),
]


def find_strategy(url: str) -> Optional[ScraperStrategy]:
    for strategy in STRATEGIES:
        if strategy.matches(url):
            return strategy
    return None
