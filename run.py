"""seeSRT 桌面入口：后台启动 FastAPI 服务，用 pywebview 原生窗口承载前端。

开发/打包通用：
- 开发模式：  python run.py
- 打包模式：  PyInstaller 以本文件为入口，双击生成的 exe 运行。
"""

import threading
import time
import urllib.request

import uvicorn
import webview

from app.main import app

HOST = "127.0.0.1"
PORT = 8877
URL = f"http://{HOST}:{PORT}/"


def _wait_ready(timeout: float = 20.0) -> bool:
    """等待后台服务就绪（轮询首页，直到可访问或超时）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(URL, timeout=0.5)
            return True
        except Exception:
            time.sleep(0.2)
    return False


def _serve() -> None:
    """在后台线程运行 FastAPI 服务。"""
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


def main() -> None:
    threading.Thread(target=_serve, daemon=True).start()
    if not _wait_ready():
        raise RuntimeError(
            f"seeSRT 服务启动超时，请确认端口 {PORT} 未被占用后重试"
        )
    webview.create_window(
        "seeSRT · 字幕智能纠错",
        URL,
        width=1280,
        height=860,
        min_size=(960, 640),
    )
    webview.start()


if __name__ == "__main__":
    main()
