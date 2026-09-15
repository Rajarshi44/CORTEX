"""External data-source connectors. Importing the package registers every connector."""
from . import benchmarks, browser, courts, gleif, icij, indiagov, news, opensanctions, web  # noqa: F401
from .base import REGISTRY, Connector, FetchResult, SourceReport, cache, get_connector, iter_connectors

__all__ = ["REGISTRY", "Connector", "FetchResult", "SourceReport", "cache", "get_connector", "iter_connectors"]
