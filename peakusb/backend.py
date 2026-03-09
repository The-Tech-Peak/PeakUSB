import os
import sys
import platform
import subprocess
import time
import re


WINDOWS_FS_MAP = {
    "FAT32": "FAT32",
    "NTFS": "NTFS",
    "EXFAT": "exFAT",
    "REFS": "ReFS",
    "EXT4": None,
}

LINUX_FS_MAP = {
    "FAT16": "vfat",
    "FAT32": "vfat",
    "NTFS": "ntfs",
    "EXFAT": "exfat",
    "EXT2": "ext2",
    "EXT3": "ext3",
    "EXT4": "ext4",
    "XFS": "xfs",
    "BTRFS": "btrfs",
    "UDF": "udf",
}


def _ps_quoted(value):
    return value.replace("'", "''")


def get_supported_filesystems(system_name=None):
    system_name = system_name or platform.system()
    if system_name == "Windows":
        return list(WINDOWS_FS_MAP.keys())
    return list(LINUX_FS_MAP.keys())


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

    if getattr(sys, "frozen", False):
        if ctypes.windll.shell32.IsUserAnAdmin():
            return "ok"
        raise RuntimeError("Administrator privileges are required. Rebuild/run the EXE with UAC admin enabled.")

    if ctypes.windll.shell32.IsUserAnAdmin():
        os.environ.pop("PEAKUSB_ELEVATING", None)
        return "ok"

    if os.environ.get("PEAKUSB_ELEVATING") == "1":
        raise RuntimeError("Elevation relaunch did not obtain administrator privileges.")

    work_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
        raise RuntimeError("Administrator privileges are required to access USB operations.")
    return "relaunch"


def list_usb_devices():
    system = platform.system()
    devices = []
    if system == "Windows":
        try:
            output = subprocess.check_output(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Get-CimInstance Win32_LogicalDisk | Where-Object {$_.DriveType -eq 2} | Select-Object -ExpandProperty DeviceID",
                ],
                universal_newlines=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            for line in output.splitlines():
                dev = line.strip()
                if dev and ":" in dev:
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
        if fs_type_upper not in WINDOWS_FS_MAP:
            supported = ", ".join(get_supported_filesystems("Windows"))
            raise ValueError(f"Filesystem '{fs_type_upper}' is not supported on Windows. Supported: {supported}")

        if fs_type_upper == "EXT4":
            raise ValueError(
                "EXT4 is selectable, but Windows cannot natively format USB drives as EXT4 with built-in tools. "
                "Use NTFS/EXFAT on Windows, or run PeakUSB on Linux for EXT4 formatting."
            )

        drive_letter = device_path.strip().rstrip("\\/").strip(":").upper()
        if not drive_letter or len(drive_letter) != 1 or not drive_letter.isalpha():
            raise ValueError(f"Invalid Windows drive letter: {device_path}")

        windows_fs = WINDOWS_FS_MAP[fs_type_upper]
        safe_label = _ps_quoted(label[:32]) if label else ""
        label_param = f" -NewFileSystemLabel '{safe_label}'" if safe_label else ""
        quick_param = "" if quick_format else " -Full"
        ps_cmd = (
            f"$vol = Get-Volume -DriveLetter {drive_letter} -ErrorAction SilentlyContinue; "
            f"if ($vol) {{ "
            f"$vol | Format-Volume -FileSystem {windows_fs}{label_param}{quick_param} -Confirm:$false -Force -ErrorAction Stop | Out-Null "
            f"}} else {{ throw 'Target volume not found.' }}"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode == 0:
            return

        format_args = ["format", f"{drive_letter}:", f"/FS:{windows_fs}", "/X", "/Y"]
        if quick_format:
            format_args.append("/Q")
        if safe_label:
            format_args.append(f"/V:{safe_label}")

        fallback = subprocess.run(
            format_args,
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
            shell=True,
        )
        if fallback.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            fb_detail = (fallback.stderr or fallback.stdout or "").strip()
            raise RuntimeError(
                "Failed to format target device. "
                f"Format-Volume error: {detail or 'unknown'}; format.exe error: {fb_detail or 'unknown'}"
            )
    else:
        if fs_type_upper not in LINUX_FS_MAP:
            supported = ", ".join(get_supported_filesystems())
            raise ValueError(f"Filesystem '{fs_type_upper}' is not supported on this platform. Supported: {supported}")

        linux_fs = LINUX_FS_MAP[fs_type_upper]
        cmd = ["sudo", "mkfs", "-t", linux_fs, device_path]
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
                timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW,
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
            subprocess.run(cmd, capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
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
                creationflags=subprocess.CREATE_NO_WINDOW,
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
                creationflags=subprocess.CREATE_NO_WINDOW,
            )

        except PermissionError as e:
            raise Exception(
                f"Permission denied while writing to {device_path}. Run PeakUSB as Administrator, close File Explorer/windows using the drive, and retry. Details: {e}"
            )
        except Exception as e:
            subprocess.run(
                ["powershell", "-Command", f"Dismount-DiskImage -ImagePath '{iso_path}'"],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            raise Exception(f"Error copying ISO contents: {e}")
    else:
        subprocess.check_call(["sudo", "dd", "if=" + iso_path, "of=" + device_path, "bs=4M", "status=progress", "conv=fsync"])


def is_windows_to_go_compatible_iso(iso_path):
    if platform.system() != "Windows":
        return False

    if not iso_path.lower().endswith(".iso"):
        return False

    quoted_iso_path = _ps_quoted(os.path.abspath(iso_path))
    script = f"""
$imgPath = '{quoted_iso_path}'
$mounted = $false
try {{
    $mount = Mount-DiskImage -ImagePath $imgPath -PassThru -ErrorAction Stop
    $mounted = $true
    $letter = (Get-Volume -DiskImage $mount | Select-Object -First 1 -ExpandProperty DriveLetter)
    if (-not $letter) {{
        Write-Output '0'
        exit 0
    }}

    $root = "${{letter}}:\\"
    $hasInstaller = (Test-Path (Join-Path $root 'sources\\install.wim')) -or (Test-Path (Join-Path $root 'sources\\install.esd'))
    $hasBootFiles = (Test-Path (Join-Path $root 'bootmgr')) -or (Test-Path (Join-Path $root 'efi\\boot\\bootx64.efi'))

    if ($hasInstaller -and $hasBootFiles) {{
        Write-Output '1'
    }} else {{
        Write-Output '0'
    }}
}}
finally {{
    if ($mounted) {{
        Dismount-DiskImage -ImagePath $imgPath -ErrorAction SilentlyContinue | Out-Null
    }}
}}
"""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return "1" in result.stdout.split()


def create_partition_scheme(device_path, scheme="mbr", target="bios"):
    return


def verify_checksum(iso_path, algorithm="sha256"):
    import hashlib

    h = hashlib.new(algorithm)
    with open(iso_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize_checksum(value):
    if not value:
        return ""
    return re.sub(r"[^0-9a-fA-F]", "", value).lower()


def load_expected_checksum(checksum_file_path):
    with open(checksum_file_path, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()

    sha256_matches = re.findall(r"\b[0-9a-fA-F]{64}\b", text)
    if sha256_matches:
        return sha256_matches[0].lower()

    raise ValueError("No SHA256 checksum was found in the selected file.")


def enable_persistence(device_path, size_mb, label="PERSISTENT"):
    if platform.system() != "Windows":
        raise NotImplementedError("Persistent partition creation is currently implemented for Windows only.")

    drive_letter = device_path.strip(":").strip("\\/").upper()
    if not drive_letter:
        raise ValueError("Invalid device path for persistence creation.")

    if size_mb < 1024:
        raise ValueError("Persistent partition size must be at least 1024 MB.")

    safe_label = _ps_quoted(label[:32])
    script = f"""
$drive = '{drive_letter}'
$sizeBytes = {int(size_mb)} * 1MB
$part = Get-Partition -DriveLetter $drive -ErrorAction Stop
$supported = Get-PartitionSupportedSize -DiskNumber $part.DiskNumber -PartitionNumber $part.PartitionNumber -ErrorAction Stop
$targetSize = $part.Size - $sizeBytes

if ($targetSize -lt $supported.SizeMin) {{
    throw "Not enough free space to create a persistent partition of {int(size_mb)} MB."
}}

Resize-Partition -DiskNumber $part.DiskNumber -PartitionNumber $part.PartitionNumber -Size $targetSize -ErrorAction Stop | Out-Null
Start-Sleep -Seconds 1
$newPart = New-Partition -DiskNumber $part.DiskNumber -UseMaximumSize -AssignDriveLetter -ErrorAction Stop
$newDrive = $newPart.DriveLetter
if (-not $newDrive) {{
    $newDrive = (Get-Volume -Partition $newPart | Select-Object -First 1 -ExpandProperty DriveLetter)
}}

if (-not $newDrive) {{
    throw 'Failed to assign drive letter to persistent partition.'
}}

Format-Volume -DriveLetter $newDrive -FileSystem NTFS -NewFileSystemLabel '{safe_label}' -Confirm:$false -ErrorAction Stop | Out-Null
Write-Output $newDrive
"""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip()
        detail = stderr or stdout or "unknown error"
        raise RuntimeError(f"Failed to create persistent partition: {detail}")

    created_drive = (result.stdout or "").strip()
    return created_drive
