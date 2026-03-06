import sys
import os
import subprocess
import traceback


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

    try:
        import ctypes

        if ctypes.windll.shell32.IsUserAnAdmin():
            return

        work_dir = os.path.dirname(os.path.abspath(__file__))
        params = subprocess.list2cmdline(["-m", "peakusb"])
        relaunch_exe = _get_windows_gui_python()
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
