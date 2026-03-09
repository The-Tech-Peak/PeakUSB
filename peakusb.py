import sys
import os
import subprocess
import traceback


def enable_windows_dpi_awareness():
    if os.name != "nt":
        return

    try:
        import ctypes

        user32 = ctypes.windll.user32
        if hasattr(user32, "SetProcessDpiAwarenessContext"):
            DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)
            if user32.SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2):
                return
    except Exception:
        pass

    try:
        import ctypes

        shcore = ctypes.windll.shcore
        PROCESS_PER_MONITOR_DPI_AWARE = 2
        shcore.SetProcessDpiAwareness(PROCESS_PER_MONITOR_DPI_AWARE)
        return
    except Exception:
        pass

    try:
        import ctypes

        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def _get_windows_gui_python():
    exe = sys.executable
    if os.name != "nt":
        return exe
    if exe.lower().endswith("python.exe"):
        pythonw = exe[:-10] + "pythonw.exe"
        if os.path.exists(pythonw):
            return pythonw
    return exe


def check_and_elevate():
    if os.name != "nt":
        return

    if getattr(sys, "frozen", False):
        return

    try:
        import ctypes

        if ctypes.windll.shell32.IsUserAnAdmin():
            os.environ.pop("PEAKUSB_ELEVATING", None)
            return

        if os.environ.get("PEAKUSB_ELEVATING") == "1":
            raise RuntimeError("Elevation relaunch did not obtain administrator privileges.")

        work_dir = os.path.dirname(os.path.abspath(__file__))
        if getattr(sys, "frozen", False):
            params = subprocess.list2cmdline(sys.argv[1:])
        else:
            script_path = os.path.abspath(sys.argv[0])
            params = subprocess.list2cmdline([script_path] + sys.argv[1:])
        relaunch_exe = _get_windows_gui_python()
        os.environ["PEAKUSB_ELEVATING"] = "1"
        if getattr(sys, "frozen", False):
            os.environ["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        rc = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            relaunch_exe,
            params,
            work_dir,
            1,
        )
        if rc <= 32:
            raise RuntimeError(f"ShellExecuteW failed with code {rc}")
        sys.exit(0)
    except Exception as exc:
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(
                None,
                f"Could not start elevated app. {exc}",
                "PeakUSB Elevation Error",
                0x10,
            )
        except Exception:
            print(f"Elevation error: {exc}")
        sys.exit(1)


from peakusb.ui import run


def main():
    try:
        enable_windows_dpi_awareness()
        check_and_elevate()
        run()
    except Exception:
        err_text = traceback.format_exc()
        try:
            log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "peakusb_error.log")
            with open(log_path, "w", encoding="utf-8") as f:
                f.write(err_text)
        except Exception:
            log_path = "peakusb_error.log"

        if os.name == "nt":
            try:
                import ctypes

                ctypes.windll.user32.MessageBoxW(
                    None,
                    f"PeakUSB failed to start. See: {log_path}",
                    "PeakUSB Startup Error",
                    0x10,
                )
            except Exception:
                pass
        raise


if __name__ == "__main__":
    main()
