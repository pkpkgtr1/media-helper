"""短剧站点：黄果（SSR + AES 封面）与野果（加密 JSON API），以及两者共用的订阅管理器。"""
from .huangguo import Client as HuangguoClient
from .huangguo import HuangguoError
from .manager import SOURCES, HuangguoManager, make_client, source_label
from .yeguo import Client as YeguoClient

__all__ = ["HuangguoClient", "HuangguoError", "YeguoClient", "HuangguoManager",
           "SOURCES", "make_client", "source_label"]
