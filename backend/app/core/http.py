"""HTTPS 信任集：保留 HTTPX 的 CA 配置，同时信任操作系统证书；不关闭校验。"""

import os
import ssl

import certifi


def tls_context() -> ssl.SSLContext:
    context = ssl.create_default_context(
        cafile=os.environ.get("SSL_CERT_FILE") or certifi.where(),
        capath=os.environ.get("SSL_CERT_DIR") or None,
    )
    context.load_default_certs()
    return context
