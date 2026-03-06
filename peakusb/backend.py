import os
import sys
import platform
import subprocess
import time


def _get_windows_gui_python():
    exe = sys.executable
    if os.name != "nt":
        return exe
    if exe.lower().endswith("python.exe"):
        pythonw = exe[:-10] + "pythonw.exe"
        if os.path.exists(pythonw):
            return pythonw
    return exe


def ensure_windows_admin():
    if os.name != "nt":
        return "ok"

    import ctypes

    if ctypes.windll.shell32.IsUserAnAdmin():
        return "ok"

    work_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
        raise RuntimeError("Administrator privileges are required to access USB operations.")
    return "relaunch"


def list_usb_devices():
    system = platform.system()
    devices = []
    if system == "Windows":
        try:
            output = subprocess.check_output(
                ["wmic", "logicaldisk", "where", "drivetype=2", "get", "DeviceID,VolumeName,Size"],
                universal_newlines=True,
            )
            for line in output.splitlines()[1:]:
                if line.strip():
                    parts = line.split()
                    dev = parts[0]
                    devices.append(dev)
        except Exception:
            pass
    else:
        try:
            output = subprocess.check_output(
                ["lsblk", "-o", "NAME,SIZE,TRAN,TYPE,MOUNTPOINT"],
                universal_newlines=True,
            )
            for line in output.splitlines():
                if "usb" in line and "disk" in line:
                    devices.append(line.strip())
        except Exception:
            pass
    return devices


def format_device(device_path, fs_type="ntfs", label=None, quick_format=False):
    system = platform.system()
    fs_type_upper = fs_type.upper()

    if system == "Windows":
        drive_letter = device_path.strip(":").upper()
        try:
            label_param = f" -NewFileSystemLabel '{label}'" if label else ""
            quick_param = "" if quick_format else " -Full"
            cmd = [
                "powershell",
                "-Command",
                f"$vol = Get-Volume -DriveLetter {drive_letter} -ErrorAction SilentlyContinue; if ($vol) {{ $vol | Format-Volume -FileSystem {fs_type_upper}{label_param}{quick_param} -Confirm:$false -ErrorAction Stop }}",
            ]
            subprocess.check_call(cmd)
        except Exception as e:
            print(f"Warning: Could not format device {device_path}: {e}")
    else:
        cmd = ["sudo", "mkfs", "-t", fs_type, device_path]
        if label:
            cmd += ["-L", label]
        subprocess.check_call(cmd)


def secure_erase_device(device_path, progress_callback=None):
    system = platform.system()

    if system == "Windows":
        try:
            chunk_size = 1024 * 1024
            zero_chunk = b"\x00" * chunk_size
            with open(device_path, "r+b") as f:
                for i in range(1024):
                    f.write(zero_chunk)
                    if progress_callback:
                        progress_callback((i + 1) * chunk_size, 1024 * chunk_size)
        except Exception as e:
            print(f"Warning: Could not securely erase device {device_path}: {e}")
    else:
        try:
            subprocess.check_call(["sudo", "dd", "if=/dev/zero", "of=" + device_path, "bs=1M", "count=1024"])
        except Exception as e:
            print(f"Warning: Could not securely erase device {device_path}: {e}")


def clean_and_prepare_device(device_path):
    system = platform.system()
    
    if system == "Windows":
        drive_letter = device_path.strip(":").upper()
        
        try:
            diskpart_script = f"""
select disk {ord(drive_letter) - ord('A')}
clean
create partition primary
assign letter={drive_letter}
"""
            result = subprocess.run(
                ["powershell", "-Command", f"diskpart | {diskpart_script}"],
                capture_output=True,
                text=True,
                timeout=30
            )
        except Exception:
            pass
        
        try:
            time.sleep(1)
            cmd = [
                "powershell",
                "-Command",
                f"$vol = Get-Volume -DriveLetter {drive_letter} -ErrorAction SilentlyContinue; if ($vol) {{ $vol | Format-Volume -FileSystem NTFS -NewFileSystemLabel 'BOOTUSB' -Confirm:$false -ErrorAction SilentlyContinue; Start-Sleep -Milliseconds 500 }}",
            ]
            subprocess.run(cmd, capture_output=True, timeout=30)
        except Exception:
            pass


def write_iso_to_device(iso_path, device_path, scheme="mbr", progress_callback=None):
    system = platform.system()

    if system == "Windows":
        try:
            admin_state = ensure_windows_admin()
            if admin_state == "relaunch":
                raise Exception("Relaunching with Administrator privileges. Please use the elevated window.")

            mount_result = subprocess.run(
                [
                    "powershell",
                    "-Command",
                    f"$mount = Mount-DiskImage -ImagePath '{iso_path}' -PassThru; (Get-Volume -DiskImage $mount).DriveLetter",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            drive_letter = ""
            for line in mount_result.stdout.splitlines():
                candidate = line.strip()
                if candidate:
                    drive_letter = candidate

            iso_drive = f"{drive_letter}:\\" if drive_letter else ""
            usb_root = device_path if device_path.endswith("\\") else f"{device_path}\\"

            if not iso_drive:
                raise Exception("Failed to mount ISO")

            time.sleep(1)

            for attempt in range(10):
                time.sleep(1)
                if os.path.exists(iso_drive) and os.path.exists(usb_root):
                    try:
                        test_file = os.path.join(usb_root, ".peakusb_test")
                        with open(test_file, "w") as f:
                            f.write("test")
                        os.remove(test_file)
                        break
                    except Exception:
                        if attempt >= 9:
                            raise Exception(
                                f"USB drive {device_path} is not writable. Close any apps using the drive and try again."
                            )
                else:
                    if attempt >= 9:
                        if not os.path.exists(iso_drive):
                            raise Exception(f"ISO drive not accessible")
                        if not os.path.exists(usb_root):
                            raise Exception(f"USB drive {device_path} not accessible. Reconnect the drive and try again.")

            iso_src = iso_drive.rstrip("\\")
            usb_dst = usb_root.rstrip("\\")

            total_size = 0
            for root, dirs, files in os.walk(iso_src):
                for file in files:
                    filepath = os.path.join(root, file)
                    try:
                        total_size += os.path.getsize(filepath)
                    except Exception:
                        pass

            bytes_copied = 0
            for root, dirs, files in os.walk(iso_src):
                rel_path = os.path.relpath(root, iso_src)
                dest_dir = os.path.join(usb_dst, rel_path) if rel_path != "." else usb_dst

                os.makedirs(dest_dir, exist_ok=True)

                for file in files:
                    src_file = os.path.join(root, file)
                    dest_file = os.path.join(dest_dir, file)

                    for retry in range(3):
                        try:
                            if os.path.exists(dest_file):
                                os.chmod(dest_file, 0o666)
                        except Exception:
                            pass

                        try:
                            with open(src_file, "rb") as src:
                                with open(dest_file, "wb") as dst:
                                    while True:
                                        chunk = src.read(1024 * 1024)
                                        if not chunk:
                                            break
                                        dst.write(chunk)
                                        bytes_copied += len(chunk)
                                        if progress_callback and total_size > 0:
                                            progress_callback(bytes_copied, total_size)
                            break
                        except PermissionError:
                            if retry >= 2:
                                raise
                            time.sleep(1)

            subprocess.run(
                ["powershell", "-Command", f"Dismount-DiskImage -ImagePath '{iso_path}'"],
                capture_output=True,
            )

        except PermissionError as e:
            raise Exception(
                f"Permission denied while writing to {device_path}. Run PeakUSB as Administrator, close File Explorer/windows using the drive, and retry. Details: {e}"
            )
        except Exception as e:
            subprocess.run(
                ["powershell", "-Command", f"Dismount-DiskImage -ImagePath '{iso_path}'"],
                capture_output=True,
            )
            raise Exception(f"Error copying ISO contents: {e}")
    else:
        subprocess.check_call(["sudo", "dd", "if=" + iso_path, "of=" + device_path, "bs=4M", "status=progress", "conv=fsync"])


def create_partition_scheme(device_path, scheme="mbr", target="bios"):
    return


def verify_checksum(iso_path, algorithm="sha256"):
    import hashlib

    h = hashlib.new(algorithm)
    with open(iso_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def enable_persistence(device_path, size_mb):
    pass
