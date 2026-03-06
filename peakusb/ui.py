import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk
import threading
import os
import sys
from . import backend


def _resource_path(*parts):
    if getattr(sys, "frozen", False):
        base_dir = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, *parts)


class SimpleSection(tk.LabelFrame):
    def __init__(self, parent, text="", **kwargs):
        super().__init__(
            parent,
            text=text,
            font=("Segoe UI", 10, "bold"),
            fg="#2c3e50",
            bg="#f5f5f5",
            relief="solid",
            borderwidth=1,
            padx=10,
            pady=8,
        )
        self.content = self


class PeakUSBApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self._set_windows_app_id()
        self.title("PeakUSB")
        self._set_app_icon()

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        bg_color = "#f5f5f5"
        self.configure(bg=bg_color)

        style.configure("Action.TButton", font=("Segoe UI", 9), padding=6)
        style.configure("TCombobox", font=("Segoe UI", 9))
        style.configure("TEntry", font=("Segoe UI", 9))
        style.configure("TLabel", font=("Segoe UI", 9), background="#f5f5f5")
        style.configure("TCheckbutton", font=("Segoe UI", 9), background="#f5f5f5")
        style.configure("TProgressbar", thickness=20)

        self.iso_path = tk.StringVar()
        self.device = tk.StringVar()
        self.fs_type = tk.StringVar(value="NTFS")
        self.partition_scheme = tk.StringVar(value="MBR")
        self.target_system = tk.StringVar(value="BIOS")
        self.volume_label = tk.StringVar(value="PEAKUSB")

        self.verify_checksum = tk.BooleanVar(value=False)
        self.quick_format = tk.BooleanVar(value=True)
        self.secure_erase = tk.BooleanVar(value=False)
        self.check_bad_blocks = tk.BooleanVar(value=False)
        self.force_unmount = tk.BooleanVar(value=False)
        self.set_bootable = tk.BooleanVar(value=False)
        self.eject_after = tk.BooleanVar(value=False)
        self.create_persistent = tk.BooleanVar(value=False)
        self.advanced_expanded = tk.BooleanVar(value=False)

        progress_frame = tk.Frame(self, bg=bg_color)
        progress_frame.pack(fill=tk.X, padx=10, pady=10, side=tk.TOP)

        self.progress_text = tk.Label(
            progress_frame,
            text="Ready",
            bg=bg_color,
            fg="#2c3e50",
            font=("Segoe UI", 10),
        )
        self.progress_text.pack(pady=(0, 5))

        self.progress_bar = ttk.Progressbar(progress_frame, maximum=100, mode="determinate")
        self.progress_bar.pack(fill=tk.X)
        self.progress_bar["value"] = 0

        main_frame = tk.Frame(self, bg=bg_color)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=0, side=tk.TOP)
        self.main_frame = main_frame

        self.create_widgets(main_frame)
        self.refresh_devices()

        btn_section = tk.Frame(self, bg=bg_color, height=55)
        btn_section.pack(fill=tk.X, padx=5, pady=(0, 5), side=tk.BOTTOM)
        btn_section.pack_propagate(False)

        btn_spacer = tk.Frame(btn_section, bg=bg_color)
        btn_spacer.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)

        self.start_btn = ttk.Button(
            btn_section,
            text="Start",
            command=self.start_process,
            style="Action.TButton",
            width=10,
        )
        self.start_btn.pack(side=tk.LEFT, padx=5, pady=5)

        self.quit_btn = ttk.Button(
            btn_section,
            text="Quit",
            command=self.quit,
            style="Action.TButton",
            width=10,
        )
        self.quit_btn.pack(side=tk.LEFT, padx=5, pady=5)

        self.update_idletasks()
        self.resizable(False, False)
        self.center_window()
        self.collapsed_size = (self.winfo_width(), self.winfo_height())
        self.expanded_size = (self.collapsed_size[0], self.collapsed_size[1] + 230)

    def _set_windows_app_id(self):
        if os.name != "nt":
            return
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PeakUSB.App")
        except Exception:
            pass

    def _set_app_icon(self):
        png_icon = _resource_path("icon", "logo.png")
        ico_icon = _resource_path("icon", "logo.ico")

        try:
            if os.path.exists(png_icon):
                self._icon_image = tk.PhotoImage(file=png_icon)
                self.iconphoto(True, self._icon_image)
                return
        except Exception:
            pass

        try:
            if os.path.exists(ico_icon):
                self.iconbitmap(ico_icon)
        except Exception:
            pass

    def center_window(self):
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        ws = self.winfo_screenwidth()
        hs = self.winfo_screenheight()
        x = (ws // 2) - (w // 2)
        y = (hs // 2) - (h // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def create_widgets(self, parent):
        iso_section = SimpleSection(parent, text="Source Image")
        iso_section.pack(fill=tk.X, expand=False, pady=5)

        iso_container = iso_section.content
        iso_container.columnconfigure(1, weight=1)
        ttk.Label(iso_container, text="ISO File:").grid(row=0, column=0, sticky="e", padx=6, pady=2)
        iso_entry = ttk.Entry(iso_container, textvariable=self.iso_path, width=30)
        iso_entry.grid(row=0, column=1, sticky="we", padx=6, pady=2)
        ttk.Button(
            iso_container,
            text="Browse",
            command=self.browse_iso,
            style="Action.TButton",
            width=10,
        ).grid(row=0, column=2, padx=6, pady=2)

        dev_section = SimpleSection(parent, text="Target USB Drive")
        dev_section.pack(fill=tk.X, expand=False, pady=5)

        dev_container = dev_section.content
        dev_container.columnconfigure(1, weight=1)
        ttk.Label(dev_container, text="Device:").grid(row=0, column=0, sticky="e", padx=6, pady=2)
        self.device_combo = ttk.Combobox(dev_container, textvariable=self.device, state="readonly", width=27)
        self.device_combo.grid(row=0, column=1, sticky="we", padx=6, pady=2)
        ttk.Button(
            dev_container,
            text="Refresh",
            command=self.refresh_devices,
            style="Action.TButton",
            width=10,
        ).grid(row=0, column=2, padx=6, pady=2)

        opt_section = SimpleSection(parent, text="Formatting Options")
        opt_section.pack(fill=tk.X, expand=False, pady=5)

        opt_container = opt_section.content
        opt_container.columnconfigure(1, weight=1)
        opt_container.columnconfigure(3, weight=1)
        opt_container.columnconfigure(5, weight=1)

        ttk.Label(opt_container, text="Filesystem:").grid(row=0, column=0, sticky="e", padx=4, pady=2)
        fs_combo = ttk.Combobox(
            opt_container,
            textvariable=self.fs_type,
            values=("FAT32", "NTFS", "EXFAT", "EXT4"),
            state="readonly",
            width=11,
        )
        fs_combo.grid(row=0, column=1, sticky="we", padx=4, pady=2)

        ttk.Label(opt_container, text="Partition:").grid(row=0, column=2, sticky="e", padx=4, pady=2)
        part_combo = ttk.Combobox(
            opt_container,
            textvariable=self.partition_scheme,
            values=("MBR", "GPT"),
            state="readonly",
            width=6,
        )
        part_combo.grid(row=0, column=3, sticky="we", padx=4, pady=2)

        ttk.Label(opt_container, text="Target:").grid(row=0, column=4, sticky="e", padx=4, pady=2)
        target_combo = ttk.Combobox(
            opt_container,
            textvariable=self.target_system,
            values=("BIOS", "UEFI"),
            state="readonly",
            width=6,
        )
        target_combo.grid(row=0, column=5, sticky="we", padx=4, pady=2)

        ttk.Label(opt_container, text="Volume Label:").grid(row=1, column=0, sticky="e", padx=4, pady=2)
        label_entry = ttk.Entry(opt_container, textvariable=self.volume_label, width=20)
        label_entry.grid(row=1, column=1, columnspan=2, sticky="we", padx=4, pady=2)

        adv_section = SimpleSection(parent, text="Advanced")
        adv_section.pack(fill=tk.X, expand=False, pady=5)

        adv_container = adv_section.content

        header_frame = tk.Frame(adv_container, bg="#f5f5f5")
        header_frame.pack(fill=tk.X, padx=6, pady=2)

        self.expand_btn = tk.Button(
            header_frame,
            text="▼ Show All Settings",
            command=self.toggle_advanced,
            bg="#e8f4f8",
            fg="#0078d4",
            font=("Segoe UI", 9, "underline"),
            relief="flat",
            padx=0,
            pady=0,
            cursor="hand2",
            activebackground="#e8f4f8",
            activeforeground="#0078d4",
        )
        self.expand_btn.pack(anchor="w")

        self.advanced_frame = tk.Frame(adv_container, bg="#f5f5f5")
        self.advanced_frame.pack(fill=tk.X, padx=6, pady=0)

        options_col = tk.Frame(self.advanced_frame, bg="#f5f5f5")
        options_col.pack(fill=tk.X, expand=True)

        ttk.Checkbutton(
            options_col,
            text="Verify checksum after writing",
            variable=self.verify_checksum,
        ).pack(
            anchor="w", padx=6, pady=2
        )
        ttk.Checkbutton(
            options_col,
            text="Quick format (faster)",
            variable=self.quick_format,
        ).pack(
            anchor="w", padx=6, pady=2
        )
        ttk.Checkbutton(
            options_col,
            text="Secure erase (overwrite with zeros)",
            variable=self.secure_erase,
        ).pack(
            anchor="w", padx=6, pady=2
        )
        ttk.Checkbutton(
            options_col,
            text="Check for bad blocks",
            variable=self.check_bad_blocks,
        ).pack(
            anchor="w", padx=6, pady=2
        )

        ttk.Checkbutton(
            options_col,
            text="Force unmount before operation",
            variable=self.force_unmount,
        ).pack(
            anchor="w", padx=6, pady=2
        )
        ttk.Checkbutton(
            options_col,
            text="Set bootable flag",
            variable=self.set_bootable,
        ).pack(
            anchor="w", padx=6, pady=2
        )
        ttk.Checkbutton(
            options_col,
            text="Eject device after completion",
            variable=self.eject_after,
        ).pack(
            anchor="w", padx=6, pady=2
        )
        ttk.Checkbutton(
            options_col,
            text="Create persistent partition",
            variable=self.create_persistent,
        ).pack(
            anchor="w", padx=6, pady=2
        )

        self.advanced_frame.pack_forget()

    def browse_iso(self):
        path = filedialog.askopenfilename(
            title="Select ISO Image",
            filetypes=[("ISO files", "*.iso"), ("All files", "*")],
        )
        if path:
            self.iso_path.set(path)

    def refresh_devices(self):
        devices = backend.list_usb_devices()
        self.device_combo["values"] = devices
        if devices:
            self.device.set(devices[0])

    def toggle_advanced(self):
        if self.advanced_expanded.get():
            self.advanced_frame.pack_forget()
            self.expand_btn.config(text="▼ Show All Settings")
            self.advanced_expanded.set(False)
            self.geometry(f"{self.collapsed_size[0]}x{self.collapsed_size[1]}")
            self.center_window()
        else:
            self.advanced_frame.pack(fill=tk.X, padx=6, pady=5, after=self.expand_btn.master)
            self.expand_btn.config(text="▲ Hide Settings")
            self.advanced_expanded.set(True)
            self.geometry(f"{self.expanded_size[0]}x{self.expanded_size[1]}")
            self.center_window()

    def start_process(self):
        iso = self.iso_path.get()
        dev = self.device.get()
        if not iso or not dev:
            messagebox.showerror("Error", "ISO image and USB device must be selected.")
            return

        try:
            state = backend.ensure_windows_admin()
            if state == "relaunch":
                self.destroy()
                return
        except Exception as e:
            messagebox.showerror("Admin Required", str(e))
            return

        self.start_btn["state"] = "disabled"
        self.quit_btn["state"] = "disabled"

        self.progress_bar["value"] = 0
        self.progress_text.config(text="Preparing... 0%")

        thread = threading.Thread(target=self._run_process_thread, daemon=True)
        thread.start()

    def _run_process_thread(self):
        try:
            iso = self.iso_path.get()
            dev = self.device.get()

            fs = self.fs_type.get().lower()
            scheme = self.partition_scheme.get().lower()
            target = self.target_system.get().lower()
            label = self.volume_label.get()

            if self.force_unmount.get():
                self._update_status("Force unmounting device...")

            if self.secure_erase.get():
                self._update_status("Secure erasing device...")
                backend.secure_erase_device(dev)

            if self.check_bad_blocks.get():
                self._update_status("Checking for bad blocks...")

            self._update_status("Copying files to device...")
            backend.write_iso_to_device(iso, dev, scheme, progress_callback=self._update_progress_threadsafe)

            if self.create_persistent.get():
                self._update_status("Creating persistent partition...")

            if self.verify_checksum.get():
                self._update_status("Verifying...")
                checksum = backend.verify_checksum(iso)
                self.after(0, lambda: messagebox.showinfo("Verification", f"ISO checksum (SHA256): {checksum}"))

            if self.eject_after.get():
                self._update_status("Ejecting device...")

            self._update_status("Complete! 100%")
            self.after(0, lambda: self.progress_bar.config(value=100))
            self.after(0, lambda: messagebox.showinfo("Success", "ISO written to device successfully."))

            self.after(0, lambda: self.progress_bar.config(value=0))
            self.after(0, lambda: self.progress_text.config(text="Ready"))
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Error", str(e)))
            self.after(0, lambda: self.progress_bar.config(value=0))
            self.after(0, lambda: self.progress_text.config(text="Ready"))
        finally:
            self.after(0, lambda: self.start_btn.config(state="normal"))
            self.after(0, lambda: self.quit_btn.config(state="normal"))

    def _update_status(self, text):
        self.after(0, lambda: self.progress_text.config(text=text))

    def _update_progress_threadsafe(self, current, total):
        if total > 0:
            percent = int((current / total) * 100)
            self.after(0, lambda: self.progress_bar.config(value=percent))
            self.after(0, lambda: self.progress_text.config(text=f"Copying files... {percent}%"))

    def update_progress(self, current, total):
        if total > 0:
            percent = int((current / total) * 100)
            self.progress_bar["value"] = percent
            self.progress_text.config(text=f"Writing ISO... {percent}%")
            self.update()


def run():
    try:
        state = backend.ensure_windows_admin()
        if state == "relaunch":
            return
    except Exception as e:
        messagebox.showerror("Admin Required", str(e))
        return

    app = PeakUSBApp()
    app.mainloop()
