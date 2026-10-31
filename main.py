import ctypes
import sys
from pathlib import Path
import webview
from src.api import AccountApi

APP_ID = "KeyVault.AccountManager.Desktop.1"


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def set_windows_app_icon(window_title: str, icon_path: Path) -> None:
    if sys.platform != "win32" or not icon_path.exists():
        return
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, window_title)
        if not hwnd:
            return
        IMAGE_ICON = 1
        LR_LOADFROMFILE = 0x00000010
        WM_SETICON = 0x0080
        ICON_SMALL = 0
        ICON_BIG = 1

        hicon_big = user32.LoadImageW(0, str(icon_path), IMAGE_ICON, 64, 64, LR_LOADFROMFILE)
        hicon_small = user32.LoadImageW(0, str(icon_path), IMAGE_ICON, 16, 16, LR_LOADFROMFILE)
        if hicon_big:
            user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, hicon_big)
        if hicon_small:
            user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon_small)
    except Exception:
        pass


def main() -> None:
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except Exception:
            pass

    base_dir = get_base_dir()
    data_dir = base_dir / "data"
    runtime_dir = data_dir / "runtime"
    web_dir = base_dir / "web"
    icon_path = web_dir / "icon.ico"

    data_dir.mkdir(parents=True, exist_ok=True)
    runtime_dir.mkdir(parents=True, exist_ok=True)

    api = AccountApi(data_dir=data_dir)

    if "--verify-init" in sys.argv:
        dash = api.get_dashboard()
        print(f"OK: data_dir={data_dir} total_accounts={dash['stats']['total']}")
        return

    title = "KeyVault · 账号管家 (Google & ChatGPT)"
    index_html = web_dir / "index.html"
    window = webview.create_window(
        title=title,
        url=str(index_html),
        js_api=api,
        width=1180,
        height=780,
        min_size=(860, 560),
        background_color="#0b1120",
        text_select=True,
    )

    window.events.shown += lambda: set_windows_app_icon(title, icon_path)

    webview.start(
        private_mode=False,
        storage_path=str(runtime_dir),
        debug=False,
    )


if __name__ == "__main__":
    main()
