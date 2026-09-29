"""seeSRT 桌面入口：后台启动 FastAPI 服务，用 pywebview 原生窗口承载前端。

开发/打包通用：
- 开发模式：  python run.py
- 打包模式：  PyInstaller 以本文件为入口，双击生成的 exe 运行。
"""

import base64
import sys
import threading
import time
import traceback
import urllib.request
from pathlib import Path

import uvicorn
import webview

from app.main import app

HOST = "127.0.0.1"
PORT = 8877
URL = f"http://{HOST}:{PORT}/"

_SERVE_ERROR = None


def _error_log_path() -> Path:
    """错误日志位置：打包后写 exe 同级，开发时写源码目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "seeSRT_error.log"
    return Path(__file__).resolve().parent / "seeSRT_error.log"


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
    """在后台线程运行 FastAPI 服务，捕获并记录启动异常。"""
    global _SERVE_ERROR
    try:
        uvicorn.run(app, host=HOST, port=PORT, log_level="warning")
    except Exception:
        _SERVE_ERROR = traceback.format_exc()
        try:
            _error_log_path().write_text(_SERVE_ERROR, encoding="utf-8")
        except Exception:
            pass


def _show_error(message: str) -> None:
    """用系统消息框显示错误（打包为 GUI 应用时无控制台可打印）。"""
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, message, "seeSRT 启动失败", 0x10)
    except Exception:
        pass


class Api:
    """暴露给前端（pywebview js_api）的本地保存能力。

    WebView2 内核默认不触发浏览器式 blob 下载，故改为弹出系统「保存文件」
    对话框，由 Python 直接写入用户选择的位置（浏览器模式仍用原 blob 下载兜底）。
    """

    def _save_dialog(self, filename: str):
        window = webview.windows[0]
        return window.create_file_dialog(
            webview.FileDialog.SAVE, save_filename=filename
        )

    def save_text(self, filename: str, content: str) -> dict:
        """保存文本文件（SRT）。"""
        result = self._save_dialog(filename)
        if not result:
            return {"ok": False, "canceled": True}
        try:
            with open(result[0], "w", encoding="utf-8", newline="\n") as f:
                f.write(content)
            return {"ok": True, "path": result[0]}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def save_bytes(self, filename: str, content_b64: str) -> dict:
        """保存二进制文件（zip），内容以 base64 传输。"""
        result = self._save_dialog(filename)
        if not result:
            return {"ok": False, "canceled": True}
        try:
            data = base64.b64decode(content_b64)
            with open(result[0], "wb") as f:
                f.write(data)
            return {"ok": True, "path": result[0]}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}


def main() -> None:
    threading.Thread(target=_serve, daemon=True).start()
    if not _wait_ready():
        detail = _SERVE_ERROR or "未知原因"
        _show_error(
            "seeSRT 服务启动失败。\n\n"
            "常见原因：\n"
            "  1) 缺少 VC++ 运行库（请用最新安装包重新安装）\n"
            "  2) 端口 8877 被占用\n\n"
            f"详细信息：\n{detail}"
        )
        raise RuntimeError(f"seeSRT 服务启动失败，详见 {_error_log_path()}")
    webview.create_window(
        "seeSRT · 字幕智能纠错",
        URL,
        width=1280,
        height=860,
        min_size=(960, 640),
        js_api=Api(),
    )
    webview.start()


if __name__ == "__main__":
    main()
