__version__ = "0.1.0"


def main():
	import os
	import traceback

	try:
		from .ui import run

		run()
	except Exception:
		err_text = traceback.format_exc()
		log_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "peakusb_error.log")
		try:
			with open(log_path, "w", encoding="utf-8") as f:
				f.write(err_text)
		except Exception:
			pass

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
