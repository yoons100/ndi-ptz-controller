import ctypes
from ctypes import c_bool, c_char_p, c_int, c_uint32, c_float, c_void_p, POINTER, Structure, byref, c_int64, c_uint8
import json
import os
import queue
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

try:
    import numpy as np
    PREVIEW_NUMPY = True
except Exception:
    PREVIEW_NUMPY = False

try:
    from PIL import Image, ImageTk
    PREVIEW_PIL = True
except Exception:
    PREVIEW_PIL = False

try:
    from pythonosc.dispatcher import Dispatcher
    from pythonosc.osc_server import ThreadingOSCUDPServer
    OSC_AVAILABLE = True
except Exception:
    OSC_AVAILABLE = False

try:
    from pynput import keyboard
    PYNPUT_AVAILABLE = True
except Exception:
    PYNPUT_AVAILABLE = False

APP_NAME = "NDI PTZ Controller"

def get_app_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def get_runtime_extract_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent

CONFIG_PATH = get_app_base_dir() / "ndi_ptz_controller_config.json"
DEFAULT_OSC_PORT = 9000
MAX_CAMERAS = 4
PRESET_COUNT = 8


class NDIlib_source_t(Structure):
    _fields_ = [
        ("p_ndi_name", c_char_p),
        ("p_url_address", c_char_p),
    ]


class NDIlib_find_create_t(Structure):
    _fields_ = [
        ("show_local_sources", c_bool),
        ("p_groups", c_char_p),
        ("p_extra_ips", c_char_p),
    ]


class NDIlib_recv_create_v3_t(Structure):
    _fields_ = [
        ("source_to_connect_to", NDIlib_source_t),
        ("color_format", c_int),
        ("bandwidth", c_int),
        ("allow_video_fields", c_bool),
        ("p_ndi_name", c_char_p),
    ]


class NDIlib_video_frame_v2_t(Structure):
    _fields_ = [
        ("xres", c_int),
        ("yres", c_int),
        ("FourCC", c_int),
        ("frame_rate_N", c_int),
        ("frame_rate_D", c_int),
        ("picture_aspect_ratio", c_float),
        ("frame_format_type", c_int),
        ("timecode", c_int64),
        ("p_data", POINTER(c_uint8)),
        ("line_stride_in_bytes", c_int),
        ("p_metadata", c_char_p),
        ("timestamp", c_int64),
    ]


class NDIRuntimeError(RuntimeError):
    pass


class NDIWrapper:
    # Values used in official docs for recv_create_v3 options.
    RECV_COLOR_FASTEST = 100
    RECV_COLOR_BEST = 101
    FRAME_TYPE_NONE = 0
    FRAME_TYPE_VIDEO = 1
    FRAME_TYPE_AUDIO = 2
    FRAME_TYPE_METADATA = 3
    FRAME_TYPE_ERROR = 4
    FRAME_TYPE_STATUS_CHANGE = 100

    FOURCC_UYVY = 0x59565955
    FOURCC_UYVA = 0x41565955
    FOURCC_P216 = 0x36313250
    FOURCC_PA16 = 0x36314150
    FOURCC_YV12 = 0x32315659
    FOURCC_I420 = 0x30323449
    FOURCC_NV12 = 0x3231564E
    FOURCC_BGRA = 0x41524742
    FOURCC_BGRX = 0x58524742
    FOURCC_RGBA = 0x41424752
    FOURCC_RGBX = 0x58424752
    RECV_BW_METADATA_ONLY = -10
    RECV_BW_AUDIO_ONLY = 10
    RECV_BW_LOWEST = 0
    RECV_BW_HIGHEST = 100

    def __init__(self):
        self.lib = self._load_library()
        self._bind_functions()
        if not self.lib.NDIlib_initialize():
            raise NDIRuntimeError("NDIlib_initialize() failed")
        self.finder = None
        self.finder_lock = threading.Lock()
        self._ensure_finder()

    def _load_library(self):
        candidates = []
        env = os.environ.get("NDI_RUNTIME_DIR")
        if env:
            candidates.append(Path(env) / "Processing.NDI.Lib.x64.dll")

        app_base = get_app_base_dir()
        runtime_base = get_runtime_extract_dir()

        candidates.extend([
            runtime_base / "Processing.NDI.Lib.x64.dll",
            app_base / "Processing.NDI.Lib.x64.dll",
            Path.cwd() / "Processing.NDI.Lib.x64.dll",
            Path(__file__).resolve().parent / "Processing.NDI.Lib.x64.dll",
            Path(r"C:\Program Files\NDI\NDI 6 Runtime\v6\Processing.NDI.Lib.x64.dll"),
            Path(r"C:\Program Files\NDI\NDI 5 Runtime\v5\Processing.NDI.Lib.x64.dll"),
            Path(r"C:\Program Files\NDI\NDI 5 Runtime\Processing.NDI.Lib.x64.dll"),
            Path(r"C:\Program Files\NDI\Runtime\Processing.NDI.Lib.x64.dll"),
        ])

        seen = set()
        unique_candidates = []
        for path in candidates:
            key = str(path).lower()
            if key not in seen:
                seen.add(key)
                unique_candidates.append(path)

        for folder in [runtime_base, app_base]:
            try:
                if hasattr(os, "add_dll_directory") and folder.exists():
                    os.add_dll_directory(str(folder))
            except Exception:
                pass

        for path in unique_candidates:
            if path.exists():
                try:
                    return ctypes.WinDLL(str(path))
                except Exception:
                    pass

        try:
            return ctypes.WinDLL("Processing.NDI.Lib.x64.dll")
        except Exception as e:
            raise NDIRuntimeError(
                "Processing.NDI.Lib.x64.dll not found. Install NDI Runtime or place the DLL next to this .py file."
            ) from e

    def _bind_functions(self):
        L = self.lib
        L.NDIlib_initialize.restype = c_bool
        L.NDIlib_destroy.restype = None

        L.NDIlib_find_create_v2.argtypes = [POINTER(NDIlib_find_create_t)]
        L.NDIlib_find_create_v2.restype = c_void_p
        L.NDIlib_find_destroy.argtypes = [c_void_p]
        L.NDIlib_find_destroy.restype = None
        L.NDIlib_find_wait_for_sources.argtypes = [c_void_p, c_uint32]
        L.NDIlib_find_wait_for_sources.restype = c_bool
        L.NDIlib_find_get_current_sources.argtypes = [c_void_p, POINTER(c_uint32)]
        L.NDIlib_find_get_current_sources.restype = POINTER(NDIlib_source_t)

        L.NDIlib_recv_create_v3.argtypes = [POINTER(NDIlib_recv_create_v3_t)]
        L.NDIlib_recv_create_v3.restype = c_void_p
        L.NDIlib_recv_connect.argtypes = [c_void_p, POINTER(NDIlib_source_t)]
        L.NDIlib_recv_connect.restype = None
        L.NDIlib_recv_destroy.argtypes = [c_void_p]
        L.NDIlib_recv_destroy.restype = None
        L.NDIlib_recv_capture_v3.argtypes = [c_void_p, POINTER(NDIlib_video_frame_v2_t), c_void_p, c_void_p, c_uint32]
        L.NDIlib_recv_capture_v3.restype = c_int
        L.NDIlib_recv_free_video_v2.argtypes = [c_void_p, POINTER(NDIlib_video_frame_v2_t)]
        L.NDIlib_recv_free_video_v2.restype = None

        # PTZ control calls
        L.NDIlib_recv_ptz_pan_tilt_speed.argtypes = [c_void_p, c_float, c_float]
        L.NDIlib_recv_ptz_pan_tilt_speed.restype = c_bool
        L.NDIlib_recv_ptz_zoom_speed.argtypes = [c_void_p, c_float]
        L.NDIlib_recv_ptz_zoom_speed.restype = c_bool
        L.NDIlib_recv_ptz_store_preset.argtypes = [c_void_p, c_int]
        L.NDIlib_recv_ptz_store_preset.restype = c_bool
        L.NDIlib_recv_ptz_recall_preset.argtypes = [c_void_p, c_int, c_float]
        L.NDIlib_recv_ptz_recall_preset.restype = c_bool

    def _ensure_finder(self):
        with self.finder_lock:
            if self.finder:
                return
            cfg = NDIlib_find_create_t(True, None, None)
            self.finder = self.lib.NDIlib_find_create_v2(byref(cfg))
            if not self.finder:
                raise NDIRuntimeError("NDIlib_find_create_v2() failed")

    def wait_for_sources(self, timeout_ms=1000):
        with self.finder_lock:
            if self.finder:
                self.lib.NDIlib_find_wait_for_sources(self.finder, timeout_ms)

    def get_sources(self):
        self._ensure_finder()
        with self.finder_lock:
            count = c_uint32(0)
            ptr = self.lib.NDIlib_find_get_current_sources(self.finder, byref(count))
            out = []
            for i in range(count.value):
                src = ptr[i]
                name = src.p_ndi_name.decode("utf-8", errors="ignore") if src.p_ndi_name else ""
                url = src.p_url_address.decode("utf-8", errors="ignore") if src.p_url_address else ""
                out.append({"name": name, "url": url})
            return out

    def create_receiver(self, source_name: str, mode: str, receiver_name: str):
        bw = self.RECV_BW_LOWEST if mode == "speed" else self.RECV_BW_HIGHEST
        # Use BGRA-friendly output so the in-app preview can draw reliably.
        color = 0
        src = NDIlib_source_t(source_name.encode("utf-8"), None)
        cfg = NDIlib_recv_create_v3_t(src, color, bw, True, receiver_name.encode("utf-8"))
        recv = self.lib.NDIlib_recv_create_v3(byref(cfg))
        if not recv:
            raise NDIRuntimeError(f"Failed to create receiver for source: {source_name}")
        return recv

    def reconnect_receiver(self, recv_handle, source_name: str):
        src = NDIlib_source_t(source_name.encode("utf-8"), None)
        self.lib.NDIlib_recv_connect(recv_handle, byref(src))

    def destroy_receiver(self, recv_handle):
        if recv_handle:
            self.lib.NDIlib_recv_destroy(recv_handle)

    def capture_video_frame(self, recv_handle, timeout_ms=0):
        video = NDIlib_video_frame_v2_t()
        frame_type = self.lib.NDIlib_recv_capture_v3(recv_handle, byref(video), None, None, c_uint32(timeout_ms))
        return frame_type, video

    def free_video_frame(self, recv_handle, video_frame):
        self.lib.NDIlib_recv_free_video_v2(recv_handle, byref(video_frame))

    def ptz_pan_tilt_speed(self, recv_handle, pan_speed: float, tilt_speed: float) -> bool:
        return bool(self.lib.NDIlib_recv_ptz_pan_tilt_speed(recv_handle, c_float(pan_speed), c_float(tilt_speed)))

    def ptz_zoom_speed(self, recv_handle, zoom_speed: float) -> bool:
        return bool(self.lib.NDIlib_recv_ptz_zoom_speed(recv_handle, c_float(zoom_speed)))

    def ptz_store_preset(self, recv_handle, preset_index: int) -> bool:
        return bool(self.lib.NDIlib_recv_ptz_store_preset(recv_handle, int(preset_index)))

    def ptz_recall_preset(self, recv_handle, preset_index: int, speed: float = 1.0) -> bool:
        return bool(self.lib.NDIlib_recv_ptz_recall_preset(recv_handle, int(preset_index), c_float(speed)))

    def shutdown(self):
        with self.finder_lock:
            if self.finder:
                self.lib.NDIlib_find_destroy(self.finder)
                self.finder = None
        try:
            self.lib.NDIlib_destroy()
        except Exception:
            pass


@dataclass
class CameraConfig:
    source_name: str = ""
    mode: str = "speed"  # speed | quality
    speed_scale: float = 0.45
    preset_labels: list[str] = field(default_factory=lambda: ["" for _ in range(PRESET_COUNT)])


class CameraState:
    def __init__(self, cam_id: int, wrapper: NDIWrapper):
        self.cam_id = cam_id
        self.wrapper = wrapper
        self.cfg = CameraConfig()
        self.recv = None
        self.connected = False
        self.last_error = ""
        self.last_sources = []
        self.ptz_pan = 0.0
        self.ptz_tilt = 0.0
        self.ptz_zoom = 0.0
        self.lock = threading.Lock()
        self.preview_thread = None
        self.preview_running = False
        self.preview_frame = None
        self.preview_frame_size = (0, 0)
        self.preview_lock = threading.Lock()
        self.preview_error = ""

    def connect(self):
        with self.lock:
            if not self.cfg.source_name:
                self.connected = False
                return False, "No source selected"
            try:
                if self.recv:
                    self.wrapper.destroy_receiver(self.recv)
                    self.recv = None
                recv_name = f"{APP_NAME} CAM{self.cam_id}"
                self.recv = self.wrapper.create_receiver(self.cfg.source_name, self.cfg.mode, recv_name)
                self.connected = True
                self.last_error = ""
                return True, f"CAM{self.cam_id} connected: {self.cfg.source_name}"
            except Exception as e:
                self.connected = False
                self.last_error = str(e)
                return False, str(e)

    def disconnect(self):
        self.stop_preview()
        with self.lock:
            if self.recv:
                self.wrapper.destroy_receiver(self.recv)
                self.recv = None
            self.connected = False
            self.ptz_pan = self.ptz_tilt = self.ptz_zoom = 0.0
            self.preview_frame = None
            self.preview_frame_size = (0, 0)

    def set_mode(self, mode: str):
        self.cfg.mode = mode
        if self.cfg.source_name:
            return self.connect()
        return True, f"CAM{self.cam_id} mode set: {mode}"

    def send_ptz(self, pan=0.0, tilt=0.0, zoom=0.0):
        with self.lock:
            if not self.recv:
                return False, "Not connected"
            ok1 = self.wrapper.ptz_pan_tilt_speed(self.recv, pan, tilt)
            ok2 = self.wrapper.ptz_zoom_speed(self.recv, zoom)
            self.ptz_pan, self.ptz_tilt, self.ptz_zoom = pan, tilt, zoom
            if ok1 or ok2:
                return True, "PTZ sent"
            return False, "PTZ command rejected or camera does not expose PTZ capability yet"

    def store_preset(self, preset_index_zero_based: int):
        with self.lock:
            if not self.recv:
                return False, "Not connected"
            ok = self.wrapper.ptz_store_preset(self.recv, preset_index_zero_based)
            return ok, f"Store preset {preset_index_zero_based + 1}"

    def recall_preset(self, preset_index_zero_based: int):
        with self.lock:
            if not self.recv:
                return False, "Not connected"
            ok = self.wrapper.ptz_recall_preset(self.recv, preset_index_zero_based, 1.0)
            return ok, f"Recall preset {preset_index_zero_based + 1}"


    def start_preview(self):
        if not (PREVIEW_NUMPY and PREVIEW_PIL):
            return
        if self.preview_running:
            return
        if not self.recv:
            return
        self.preview_running = True
        self.preview_error = ""
        self.preview_thread = threading.Thread(target=self._preview_loop, daemon=True)
        self.preview_thread.start()

    def stop_preview(self):
        self.preview_running = False
        thread = self.preview_thread
        if thread and thread.is_alive():
            thread.join(timeout=0.4)
        self.preview_thread = None
        with self.preview_lock:
            self.preview_frame = None
            self.preview_frame_size = (0, 0)
            self.preview_error = ""

    def get_preview_frame(self):
        with self.preview_lock:
            frame = None if self.preview_frame is None else self.preview_frame.copy()
            size = self.preview_frame_size
            err = self.preview_error
        return frame, size, err

    def _preview_loop(self):
        while self.preview_running:
            recv = self.recv
            if not recv or not self.connected:
                with self.preview_lock:
                    self.preview_frame = None
                    self.preview_frame_size = (0, 0)
                    self.preview_error = "Preview idle"
                time.sleep(0.1)
                continue
            try:
                frame_type, video = self.wrapper.capture_video_frame(recv, 30)
                if frame_type != self.wrapper.FRAME_TYPE_VIDEO:
                    if frame_type == self.wrapper.FRAME_TYPE_ERROR:
                        with self.preview_lock:
                            self.preview_error = "Preview capture error"
                    time.sleep(0.01)
                    continue

                try:
                    w, h = int(video.xres), int(video.yres)
                    stride = int(video.line_stride_in_bytes)
                    if not video.p_data or w <= 0 or h <= 0 or stride <= 0:
                        with self.preview_lock:
                            self.preview_error = "Preview waiting..."
                        continue

                    total = stride * h
                    buf = ctypes.string_at(video.p_data, total)
                    arr = np.frombuffer(buf, dtype=np.uint8).reshape((h, stride))
                    pixel_bytes = arr[:, :w * 4].reshape((h, w, 4))

                    if video.FourCC in (self.wrapper.FOURCC_BGRA, self.wrapper.FOURCC_BGRX):
                        rgb = pixel_bytes[:, :, :3][:, :, ::-1]
                    elif video.FourCC in (self.wrapper.FOURCC_RGBA, self.wrapper.FOURCC_RGBX):
                        rgb = pixel_bytes[:, :, :3]
                    else:
                        with self.preview_lock:
                            self.preview_error = f"Unsupported preview format: {video.FourCC}"
                        continue

                    # Slightly larger buffer for cleaner in-app 16:9 preview while staying light.
                    target_w = 480
                    if w > target_w:
                        target_h = max(1, int(h * (target_w / w)))
                        img = Image.fromarray(rgb)
                        img = img.resize((target_w, target_h), Image.Resampling.BILINEAR)
                        rgb_small = np.array(img)
                    else:
                        rgb_small = rgb

                    with self.preview_lock:
                        self.preview_frame = rgb_small
                        self.preview_frame_size = (w, h)
                        self.preview_error = ""
                finally:
                    self.wrapper.free_video_frame(recv, video)
            except Exception as e:
                with self.preview_lock:
                    self.preview_error = str(e)
                time.sleep(0.05)


class OSCServerThread(threading.Thread):
    def __init__(self, app, port: int):
        super().__init__(daemon=True)
        self.app = app
        self.port = port
        self.server = None

    def run(self):
        if not OSC_AVAILABLE:
            return
        dispatcher = Dispatcher()
        dispatcher.map("/cam*/preset/*", self._wildcard_handler)
        dispatcher.map("/camera/*/preset/*", self._camera_handler)
        dispatcher.set_default_handler(self._default_handler)
        self.server = ThreadingOSCUDPServer(("0.0.0.0", self.port), dispatcher)
        self.app.threadsafe_log(f"OSC listening on UDP {self.port}")
        self.server.serve_forever()

    def _default_handler(self, address, *args):
        parts = [p for p in address.split("/") if p]
        self._dispatch(parts)

    def _wildcard_handler(self, address, *args):
        parts = [p for p in address.split("/") if p]
        self._dispatch(parts)

    def _camera_handler(self, address, *args):
        parts = [p for p in address.split("/") if p]
        self._dispatch(parts)

    def _dispatch(self, parts):
        try:
            if len(parts) == 3 and parts[0].startswith("cam") and parts[1] == "preset":
                cam = int(parts[0][3:])
                preset = int(parts[2])
                self.app.queue_action(lambda: self.app.recall_preset(cam, preset))
                return
            if len(parts) == 4 and parts[0] == "camera" and parts[2] == "preset":
                cam = int(parts[1])
                preset = int(parts[3])
                self.app.queue_action(lambda: self.app.recall_preset(cam, preset))
                return
        except Exception as e:
            self.app.threadsafe_log(f"OSC parse error: {'/'.join(parts)} ({e})")

    def stop(self):
        try:
            if self.server:
                self.server.shutdown()
                self.server.server_close()
        except Exception:
            pass


class GlobalKeyListener(threading.Thread):
    def __init__(self, app):
        super().__init__(daemon=True)
        self.app = app
        self.listener = None
        self.ctrl_down = False
        self.shift_down = False

    def run(self):
        if not PYNPUT_AVAILABLE:
            self.app.threadsafe_log("Global keyboard listener disabled (pynput not installed)")
            return

        def on_press(key):
            try:
                if key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
                    self.ctrl_down = True
                if key in (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r):
                    self.shift_down = True
                self.app.on_key_press(key, self.ctrl_down, self.shift_down)
            except Exception:
                pass

        def on_release(key):
            try:
                if key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
                    self.ctrl_down = False
                if key in (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r):
                    self.shift_down = False
                self.app.on_key_release(key)
            except Exception:
                pass

        self.listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self.listener.start()
        self.listener.join()

    def stop(self):
        try:
            if self.listener:
                self.listener.stop()
        except Exception:
            pass


class NDIControllerApp(tk.Tk):
    def __init__(self, wrapper: NDIWrapper):
        super().__init__()
        self.wrapper = wrapper
        self.title(APP_NAME)
        try:
            icon_candidates = [
                get_runtime_extract_dir() / "ndi.ico",
                get_app_base_dir() / "ndi.ico",
                Path.cwd() / "ndi.ico",
            ]
            for icon_path in icon_candidates:
                if icon_path.exists():
                    self.iconbitmap(str(icon_path))
                    break
        except Exception:
            pass
        self.geometry("1180x940")
        self.minsize(1100, 860)
        self.configure(bg="#1e1f22")
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.action_queue = queue.Queue()
        self.log_queue = queue.Queue()
        self.selected_cam = 1
        self.keys_down = set()
        self.osc_thread = None
        self.key_listener = None
        self.polling = True
        self.app_hotkeys_enabled = False
        self.hotkeys_temporarily_disabled = False
        self.all_preset_labels = ["" for _ in range(PRESET_COUNT)]
        self.auto_connect_retry_count = 0
        self.auto_connect_max_retries = 10

        self.cameras = [CameraState(i + 1, wrapper) for i in range(MAX_CAMERAS)]
        self.camera_ui = {}
        self.load_config()
        self._build_ui()
        self.after(50, self._drain_ui_queues)
        self.after(1000, self._source_refresh_tick)
        self.after(40, self._ptz_tick)
        self.after(50, self._preview_tick)
        self.start_background_services()
        self.after(1200, self._startup_auto_connect)
        self.threadsafe_log(f"Config path: {CONFIG_PATH}")
        self.threadsafe_log("App ready")

    def _build_ui(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TNotebook", background="#1e1f22")
        style.configure("TNotebook.Tab", padding=(10, 6))

        top = tk.Frame(self, bg="#1e1f22")
        top.pack(fill="x", padx=10, pady=8)

        self.status_label = tk.Label(
            top,
            text="Selected CAM1 | Arrow keys=PTZ | +/-=Zoom | 1~8=Preset | Ctrl+1~4=Select Camera",
            fg="#d7dae0",
            bg="#1e1f22",
            anchor="w",
        )
        self.status_label.pack(side="left", fill="x", expand=True)

        self.hotkey_label = tk.Label(top, text="Hotkeys: inactive", fg="#ffb86c", bg="#1e1f22")
        self.hotkey_label.pack(side="right", padx=(0, 12))

        self.osc_label = tk.Label(top, text="OSC: off", fg="#9aa0aa", bg="#1e1f22")
        self.osc_label.pack(side="right")

        content = tk.PanedWindow(self, orient="horizontal", sashrelief="flat", bg="#1e1f22")
        content.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        left = tk.Frame(content, bg="#1e1f22")
        right = tk.Frame(content, bg="#1e1f22")
        content.add(left, width=840, stretch="always")
        content.add(right, width=560)

        self.notebook = ttk.Notebook(left)
        self.notebook.pack(fill="both", expand=True)
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        for cam in self.cameras:
            tab = tk.Frame(self.notebook, bg="#2a2d31")
            self.notebook.add(tab, text=f"CAM {cam.cam_id}")
            self._build_camera_tab(tab, cam)

        right_top = tk.LabelFrame(right, text="Global", bg="#2a2d31", fg="#d7dae0")
        right_top.pack(fill="x", pady=(0, 8))

        osc_row = tk.Frame(right_top, bg="#2a2d31")
        osc_row.pack(fill="x", padx=8, pady=8)
        tk.Label(osc_row, text="OSC Port", bg="#2a2d31", fg="#d7dae0").pack(side="left")
        self.osc_port_var = tk.StringVar(value=str(DEFAULT_OSC_PORT))
        osc_entry = tk.Entry(osc_row, textvariable=self.osc_port_var, width=8)
        osc_entry.pack(side="left", padx=6)
        for seq in ("<Up>", "<Down>", "<Left>", "<Right>", "<KeyPress-plus>", "<KeyPress-equal>", "<KeyPress-minus>", "<KeyPress-KP_Add>", "<KeyPress-KP_Subtract>"):
            osc_entry.bind(seq, self._consume_hotkey_widget_event, add="+")
        for seq in ("<KeyRelease-Up>", "<KeyRelease-Down>", "<KeyRelease-Left>", "<KeyRelease-Right>", "<KeyRelease-plus>", "<KeyRelease-equal>", "<KeyRelease-minus>", "<KeyRelease-KP_Add>", "<KeyRelease-KP_Subtract>"):
            osc_entry.bind(seq, self._release_hotkey_widget_event, add="+")
        tk.Button(osc_row, text="Start OSC", command=self.restart_osc).pack(side="left", padx=4)
        tk.Button(osc_row, text="Stop OSC", command=self.stop_osc).pack(side="left", padx=4)

        all_preset_box = tk.LabelFrame(right_top, text="All Connected Cams: Preset Recall (Ctrl+Click=Rename)", bg="#2a2d31", fg="#d7dae0")
        all_preset_box.pack(fill="x", padx=8, pady=(0, 8))
        self.all_preset_buttons = []
        for i in range(PRESET_COUNT):
            b = tk.Button(
                all_preset_box,
                text=self._format_all_preset_button_text(i),
                width=9,
                height=3,
                justify="center",
                wraplength=84,
                command=lambda idx=i: self.recall_preset_all(idx + 1),
            )
            b.grid(row=0, column=i, padx=4, pady=8, sticky="nsew")
            b.bind("<Control-Button-1>", lambda e, idx=i: self.rename_all_preset(idx + 1))
            self.all_preset_buttons.append(b)
        for i in range(PRESET_COUNT):
            all_preset_box.grid_columnconfigure(i, weight=1)

        info = (
            "Keyboard\n"
            "Ctrl+1~4 : select camera\n"
            "1~8 : recall preset\n"
            "Shift+1~8 : store preset\n"
            "Arrow keys : pan/tilt\n"
            "+ / - : zoom\n\n"
            "OSC\n"
            "/cam1/preset/1\n"
            "/camera/2/preset/3"
        )
        tk.Label(right_top, text=info, justify="left", bg="#2a2d31", fg="#d7dae0").pack(fill="x", padx=8, pady=(0, 8))

        log_box = tk.LabelFrame(right, text="Log", bg="#2a2d31", fg="#d7dae0")
        log_box.pack(fill="both", expand=True)
        self.log_text = tk.Text(log_box, height=14, bg="#111317", fg="#d7dae0", insertbackground="#ffffff")
        self.log_text.pack(fill="both", expand=True, padx=6, pady=6)
        self.log_text.bind("<Key>", lambda e: "break")

        bottom = tk.Frame(self, bg="#1e1f22")
        bottom.pack(fill="x", padx=10, pady=(0, 10))
        tk.Button(bottom, text="Refresh Sources", command=self.manual_refresh_sources).pack(side="left")
        tk.Button(bottom, text="Save Config", command=self.save_config).pack(side="left", padx=6)
        tk.Button(bottom, text="Open NDI Studio Monitor", command=self.open_studio_monitor).pack(side="left")

    def _build_camera_tab(self, parent, cam: CameraState):
        root = tk.Frame(parent, bg="#2a2d31")
        root.pack(fill="both", expand=True, padx=12, pady=12)

        header = tk.Frame(root, bg="#2a2d31")
        header.pack(fill="x")
        select_btn = tk.Button(header, text=f"Select CAM{cam.cam_id}", command=lambda c=cam.cam_id: self.select_camera(c))
        select_btn.pack(side="left")
        status = tk.Label(header, text="● Disconnected", fg="#ff6b6b", bg="#2a2d31")
        status.pack(side="left", padx=10)

        src_row = tk.Frame(root, bg="#2a2d31")
        src_row.pack(fill="x", pady=(12, 8))
        tk.Label(src_row, text="NDI Source", bg="#2a2d31", fg="#d7dae0").pack(side="left")
        source_var = tk.StringVar(value=cam.cfg.source_name)
        source_combo = ttk.Combobox(src_row, textvariable=source_var, state="readonly", width=48)
        source_combo.pack(side="left", padx=8)
        for seq in ("<Up>", "<Down>", "<Left>", "<Right>", "<KeyPress-plus>", "<KeyPress-equal>", "<KeyPress-minus>", "<KeyPress-KP_Add>", "<KeyPress-KP_Subtract>"):
            source_combo.bind(seq, self._consume_hotkey_widget_event, add="+")
        for seq in ("<KeyRelease-Up>", "<KeyRelease-Down>", "<KeyRelease-Left>", "<KeyRelease-Right>", "<KeyRelease-plus>", "<KeyRelease-equal>", "<KeyRelease-minus>", "<KeyRelease-KP_Add>", "<KeyRelease-KP_Subtract>"):
            source_combo.bind(seq, self._release_hotkey_widget_event, add="+")
        tk.Button(src_row, text="Refresh", command=self.manual_refresh_sources).pack(side="left")
        tk.Button(src_row, text="Connect", command=lambda c=cam.cam_id: self.connect_camera(c)).pack(side="left", padx=4)
        tk.Button(src_row, text="Disconnect", command=lambda c=cam.cam_id: self.disconnect_camera(c)).pack(side="left")

        mode_row = tk.Frame(root, bg="#2a2d31")
        mode_row.pack(fill="x", pady=(2, 10))
        tk.Label(mode_row, text="Preview Mode", bg="#2a2d31", fg="#d7dae0").pack(side="left")
        mode_var = tk.StringVar(value=cam.cfg.mode)
        tk.Radiobutton(mode_row, text="Speed", variable=mode_var, value="speed", bg="#2a2d31", fg="#d7dae0", selectcolor="#2a2d31", command=lambda c=cam.cam_id: self.apply_mode(c)).pack(side="left", padx=(8, 0))
        tk.Radiobutton(mode_row, text="Quality", variable=mode_var, value="quality", bg="#2a2d31", fg="#d7dae0", selectcolor="#2a2d31", command=lambda c=cam.cam_id: self.apply_mode(c)).pack(side="left", padx=(8, 0))
        tk.Label(mode_row, text="PTZ Speed", bg="#2a2d31", fg="#d7dae0").pack(side="left", padx=(20, 4))
        speed_var = tk.DoubleVar(value=cam.cfg.speed_scale)
        tk.Scale(mode_row, variable=speed_var, from_=0.1, to=1.0, resolution=0.05, orient="horizontal", length=180, command=lambda _v, c=cam.cam_id: self.update_speed_scale(c)).pack(side="left")

        ptz_box = tk.LabelFrame(root, text="PTZ", bg="#2a2d31", fg="#d7dae0")
        ptz_box.pack(fill="x", pady=(8, 10))
        pad = tk.Frame(ptz_box, bg="#2a2d31")
        pad.pack(padx=20, pady=14)
        buttons = {}
        buttons['up'] = tk.Button(pad, text="↑", width=6, height=2)
        buttons['left'] = tk.Button(pad, text="←", width=6, height=2)
        buttons['stop'] = tk.Button(pad, text="STOP", width=8, height=2, command=lambda c=cam.cam_id: self.stop_camera(c))
        buttons['right'] = tk.Button(pad, text="→", width=6, height=2)
        buttons['down'] = tk.Button(pad, text="↓", width=6, height=2)
        buttons['zoom_in'] = tk.Button(pad, text="ZOOM +", width=8, height=2)
        buttons['zoom_out'] = tk.Button(pad, text="ZOOM -", width=8, height=2)
        buttons['up'].grid(row=0, column=1, padx=6, pady=6)
        buttons['left'].grid(row=1, column=0, padx=6, pady=6)
        buttons['stop'].grid(row=1, column=1, padx=6, pady=6)
        buttons['right'].grid(row=1, column=2, padx=6, pady=6)
        buttons['down'].grid(row=2, column=1, padx=6, pady=6)
        buttons['zoom_in'].grid(row=1, column=3, padx=(24, 6), pady=6)
        buttons['zoom_out'].grid(row=2, column=3, padx=(24, 6), pady=6)

        mapping = {
            'up': ('up', True), 'left': ('left', True), 'right': ('right', True),
            'down': ('down', True), 'zoom_in': ('zoom_in', True), 'zoom_out': ('zoom_out', True)
        }
        for name, btn in buttons.items():
            if name in mapping:
                action, is_press = mapping[name]
                btn.bind("<ButtonPress-1>", lambda e, c=cam.cam_id, a=action: self.handle_virtual_key(c, a, True))
                btn.bind("<ButtonRelease-1>", lambda e, c=cam.cam_id, a=action: self.handle_virtual_key(c, a, False))

        preset_box = tk.LabelFrame(root, text="Presets (Click=Recall, Shift+Click or RightClick=Store, Ctrl+Click=Rename)", bg="#2a2d31", fg="#d7dae0")
        preset_box.pack(fill="x", pady=(4, 10))
        preset_buttons = []
        for i in range(PRESET_COUNT):
            b = tk.Button(
                preset_box,
                text=self._format_preset_button_text(cam.cam_id, i),
                width=12,
                height=3,
                justify="center",
                wraplength=88,
                command=lambda idx=i, c=cam.cam_id: self.recall_preset(c, idx + 1),
            )
            b.grid(row=0, column=i, padx=4, pady=10, sticky="nsew")
            b.bind("<Button-3>", lambda e, idx=i, c=cam.cam_id: self.store_preset(c, idx + 1))
            b.bind("<Shift-Button-1>", lambda e, idx=i, c=cam.cam_id: self.store_preset(c, idx + 1))
            b.bind("<Control-Button-1>", lambda e, idx=i, c=cam.cam_id: self.rename_preset(c, idx + 1))
            preset_buttons.append(b)
        for i in range(PRESET_COUNT):
            preset_box.grid_columnconfigure(i, weight=1)


        # --- NDI Preview ---
        preview_box = tk.LabelFrame(root, text="NDI Preview", bg="#2a2d31", fg="#d7dae0")
        preview_box.pack(fill="x", pady=(10, 0))

        preview_stage = tk.Frame(preview_box, bg="#000000", width=480, height=270)
        preview_stage.pack(anchor="w", padx=10, pady=(10, 6))
        preview_stage.pack_propagate(False)

        preview_label = tk.Label(
            preview_stage,
            text="No Signal",
            bg="#000000",
            fg="#00ff00",
        )
        preview_label.place(relx=0.5, rely=0.5, anchor="center", width=480, height=270)

        preview_info = tk.Label(
            preview_box,
            text="16:9 in-app preview for monitoring.",
            bg="#2a2d31",
            fg="#9aa0aa",
            anchor="w",
            justify="left",
        )
        preview_info.pack(fill="x", padx=10, pady=(0, 6))

        note = tk.Label(
            root,
            text="Tip: Some NDI cameras expose PTZ capability a few seconds after connection. If PTZ seems dead right after connect, wait 2–5 seconds and try again.",
            bg="#2a2d31",
            fg="#9aa0aa",
            anchor="w",
            justify="left",
        )
        note.pack(fill="x", pady=(8, 0))

        preview_stage.bind("<Configure>", lambda e, c=cam.cam_id: self._on_preview_stage_configure(c))

        self.camera_ui[cam.cam_id] = {
            "status": status,
            "source_var": source_var,
            "source_combo": source_combo,
            "mode_var": mode_var,
            "speed_var": speed_var,
            "select_btn": select_btn,
            "preset_buttons": preset_buttons,
            "preview_stage": preview_stage,
            "preview_label": preview_label,
            "preview_info": preview_info,
            "preview_photo": None,
        }

        self.after(50, lambda c=cam.cam_id: self._update_preview_geometry(c))
        self.after(80, lambda c=cam.cam_id: self.refresh_preset_button_labels(c))


    def _update_preview_geometry(self, cam_id: int):
        ui = self.camera_ui.get(cam_id)
        if not ui:
            return
        stage = ui["preview_stage"]
        label = ui["preview_label"]
        try:
            stage_w = stage.winfo_width()
        except Exception:
            stage_w = 560
        if stage_w <= 1:
            stage_w = 480
        target_w = max(380, min(430, stage_w))
        target_h = max(236, int(target_w * 9 / 16))
        stage.configure(width=target_w, height=target_h)
        label.place_configure(width=target_w, height=target_h)

    def _on_preview_stage_configure(self, cam_id: int):
        self._update_preview_geometry(cam_id)

    def _prompt_for_label(self, title: str, current: str):
        self.hotkeys_temporarily_disabled = True
        if self.keys_down:
            self.keys_down.clear()
            try:
                self.stop_camera(self.selected_cam)
            except Exception:
                pass
        self._update_focus_state()
        try:
            value = simpledialog.askstring(APP_NAME, title, initialvalue=current, parent=self)
        finally:
            self.hotkeys_temporarily_disabled = False
            self._update_focus_state()
        return value

    def _format_all_preset_button_text(self, preset_idx_zero_based: int):
        while len(self.all_preset_labels) < PRESET_COUNT:
            self.all_preset_labels.append("")
        label = (self.all_preset_labels[preset_idx_zero_based] or "").strip()
        return f"{preset_idx_zero_based + 1}\n{label}" if label else str(preset_idx_zero_based + 1)

    def refresh_all_preset_button_labels(self):
        for idx, btn in enumerate(getattr(self, "all_preset_buttons", [])):
            btn.config(text=self._format_all_preset_button_text(idx))

    def rename_all_preset(self, preset_1_based: int):
        current = ""
        if len(self.all_preset_labels) >= preset_1_based:
            current = self.all_preset_labels[preset_1_based - 1]
        value = self._prompt_for_label(f"All preset {preset_1_based} label", current)
        if value is None:
            return "break"
        while len(self.all_preset_labels) < PRESET_COUNT:
            self.all_preset_labels.append("")
        self.all_preset_labels[preset_1_based - 1] = value.strip()
        self.refresh_all_preset_button_labels()
        self.save_config()
        self.log(f"ALL: preset {preset_1_based} label updated")
        return "break"

    def _format_preset_button_text(self, cam_id: int, preset_idx_zero_based: int):
        cam = self.cameras[cam_id - 1]
        labels = list(cam.cfg.preset_labels) if cam.cfg.preset_labels else []
        while len(labels) < PRESET_COUNT:
            labels.append("")
        cam.cfg.preset_labels = labels[:PRESET_COUNT]
        label = (cam.cfg.preset_labels[preset_idx_zero_based] or "").strip()
        return f"{preset_idx_zero_based + 1}\n{label}" if label else str(preset_idx_zero_based + 1)

    def refresh_preset_button_labels(self, cam_id: int):
        ui = self.camera_ui.get(cam_id)
        if not ui:
            return
        for idx, btn in enumerate(ui["preset_buttons"]):
            btn.config(text=self._format_preset_button_text(cam_id, idx))

    def rename_preset(self, cam_id: int, preset_1_based: int):
        cam = self.cameras[cam_id - 1]
        current = ""
        if cam.cfg.preset_labels and len(cam.cfg.preset_labels) >= preset_1_based:
            current = cam.cfg.preset_labels[preset_1_based - 1]
        value = self._prompt_for_label(f"Preset {preset_1_based} label", current)
        if value is None:
            return "break"
        while len(cam.cfg.preset_labels) < PRESET_COUNT:
            cam.cfg.preset_labels.append("")
        cam.cfg.preset_labels[preset_1_based - 1] = value.strip()
        self.refresh_preset_button_labels(cam_id)
        self.save_config()
        self.log(f"CAM{cam_id}: preset {preset_1_based} label updated")
        return "break"

    def _consume_hotkey_widget_event(self, event):
        self._tk_keypress(event)
        return "break"

    def _release_hotkey_widget_event(self, event):
        self._tk_keyrelease(event)
        return "break"

    def load_config(self):
        if not CONFIG_PATH.exists():
            return
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            labels = list(data.get("all_preset_labels", []))
            while len(labels) < PRESET_COUNT:
                labels.append("")
            self.all_preset_labels = labels[:PRESET_COUNT]
            cams = data.get("cameras", [])
            for idx, cam_data in enumerate(cams[:MAX_CAMERAS]):
                cfg = CameraConfig(**cam_data)
                labels = list(cfg.preset_labels) if cfg.preset_labels else []
                while len(labels) < PRESET_COUNT:
                    labels.append("")
                cfg.preset_labels = labels[:PRESET_COUNT]
                self.cameras[idx].cfg = cfg
        except Exception:
            pass

    def save_config(self):
        try:
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        data = {
            "all_preset_labels": list(self.all_preset_labels[:PRESET_COUNT]),
            "cameras": [asdict(cam.cfg) for cam in self.cameras],
        }
        CONFIG_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        self.log("Config saved")

    def queue_action(self, fn):
        self.action_queue.put(fn)

    def threadsafe_log(self, msg: str):
        self.log_queue.put(msg)

    def log(self, msg: str):
        timestamp = time.strftime("%H:%M:%S")
        line = f"[{timestamp}] {msg}\n"
        self.log_text.insert("end", line)
        self.log_text.see("end")
        print(line, end="")

    def _drain_ui_queues(self):
        while True:
            try:
                fn = self.action_queue.get_nowait()
                fn()
            except queue.Empty:
                break
            except Exception as e:
                self.log(f"UI action error: {e}")
        while True:
            try:
                msg = self.log_queue.get_nowait()
                self.log(msg)
            except queue.Empty:
                break
        self.after(50, self._drain_ui_queues)

    def start_background_services(self):
        if OSC_AVAILABLE:
            self.restart_osc()
        else:
            self.osc_label.config(text="OSC: python-osc not installed", fg="#ffb86c")
        if not (PREVIEW_NUMPY and PREVIEW_PIL):
            self.threadsafe_log("In-app preview disabled (install numpy + pillow)")
        if PYNPUT_AVAILABLE:
            self.threadsafe_log("pynput installed, but global hotkeys are intentionally disabled. Hotkeys work only while this app is focused.")
        else:
            self.threadsafe_log("Hotkeys work only while this app is focused.")
        self.bind_all("<KeyPress>", self._tk_keypress)
        self.bind_all("<KeyRelease>", self._tk_keyrelease)
        self.bind("<FocusIn>", self._on_focus_in)
        self.bind("<FocusOut>", self._on_focus_out)
        self.after(150, self._update_focus_state)

    def restart_osc(self):
        self.stop_osc()
        if not OSC_AVAILABLE:
            return
        try:
            port = int(self.osc_port_var.get().strip())
            self.osc_thread = OSCServerThread(self, port)
            self.osc_thread.start()
            self.osc_label.config(text=f"OSC: UDP {port}", fg="#7dd87d")
        except Exception as e:
            self.osc_label.config(text="OSC: error", fg="#ff6b6b")
            self.log(f"OSC start failed: {e}")

    def stop_osc(self):
        try:
            if self.osc_thread:
                self.osc_thread.stop()
                self.osc_thread = None
            self.osc_label.config(text="OSC: off", fg="#9aa0aa")
        except Exception:
            pass

    def manual_refresh_sources(self, log_result=True):
        try:
            self.wrapper.wait_for_sources(300)
            sources = self.wrapper.get_sources()
            names = [s["name"] for s in sources]
            for cam in self.cameras:
                cam.last_sources = names
                ui = self.camera_ui.get(cam.cam_id)
                if ui:
                    ui["source_combo"]["values"] = names
                    if cam.cfg.source_name and cam.cfg.source_name in names:
                        ui["source_var"].set(cam.cfg.source_name)
            if log_result:
                self.log(f"Source list refreshed ({len(names)})")
            return names
        except Exception as e:
            if log_result:
                self.log(f"Source refresh failed: {e}")
            return []

    def _startup_auto_connect(self):
        self.auto_connect_retry_count += 1
        names = self.manual_refresh_sources(log_result=(self.auto_connect_retry_count == 1))
        if not names and self.auto_connect_retry_count < self.auto_connect_max_retries:
            self.after(2000, self._startup_auto_connect)
            return

        pending = False
        for cam in self.cameras:
            source_name = (cam.cfg.source_name or "").strip()
            if not source_name or cam.connected:
                continue
            if source_name not in names:
                pending = True
                continue

            ui = self.camera_ui.get(cam.cam_id)
            if ui:
                ui["source_var"].set(source_name)
            ok, msg = cam.connect()
            self._refresh_camera_status(cam.cam_id)
            if ok:
                cam.start_preview()
                self.log(f"Auto-connect: {msg}")
            else:
                pending = True

        if pending and self.auto_connect_retry_count < self.auto_connect_max_retries:
            self.after(2000, self._startup_auto_connect)

    def _on_focus_in(self, _event=None):
        self._update_focus_state()

    def _on_focus_out(self, _event=None):
        self._update_focus_state()

    def _update_focus_state(self):
        try:
            focused = (self.focus_displayof() is not None) and (self.focus_get() is not None)
        except Exception:
            focused = False
        effective_hotkeys = focused and (not self.hotkeys_temporarily_disabled)
        changed = effective_hotkeys != self.app_hotkeys_enabled
        self.app_hotkeys_enabled = effective_hotkeys
        if self.hotkeys_temporarily_disabled:
            hotkey_text = "Hotkeys: paused"
            hotkey_fg = "#ffb86c"
        else:
            hotkey_text = ("Hotkeys: active" if effective_hotkeys else "Hotkeys: inactive")
            hotkey_fg = ("#7dd87d" if effective_hotkeys else "#ffb86c")
        self.hotkey_label.config(text=hotkey_text, fg=hotkey_fg)
        if not effective_hotkeys and self.keys_down:
            self.keys_down.clear()
            try:
                self.stop_camera(self.selected_cam)
            except Exception:
                pass
        if changed:
            state = "PAUSE" if self.hotkeys_temporarily_disabled else ("ON" if effective_hotkeys else "OFF")
            self.status_label.config(
                text=f"Selected CAM{self.selected_cam} | Arrow keys=PTZ | +/-=Zoom | 1~8=Preset | Ctrl+1~4=Select Camera | Hotkeys {state}"
            )
        self.after(150, self._update_focus_state)

    def _source_refresh_tick(self):
        if self.polling:
            try:
                sources = self.wrapper.get_sources()
                names = [s["name"] for s in sources]
                for cam in self.cameras:
                    ui = self.camera_ui.get(cam.cam_id)
                    if ui and names != list(ui["source_combo"].cget("values")):
                        ui["source_combo"]["values"] = names
                # Don't spam log on automatic refresh.
            except Exception:
                pass
        self.after(3000, self._source_refresh_tick)

    def _ptz_tick(self):
        cam = self.cameras[self.selected_cam - 1]
        if not self.app_hotkeys_enabled:
            self.after(40, self._ptz_tick)
            return
        scale = cam.cfg.speed_scale
        pan = tilt = zoom = 0.0
        if "left" in self.keys_down:
            pan += scale
        if "right" in self.keys_down:
            pan -= scale
        if "up" in self.keys_down:
            tilt += scale
        if "down" in self.keys_down:
            tilt -= scale
        if "zoom_in" in self.keys_down:
            zoom += scale
        if "zoom_out" in self.keys_down:
            zoom -= scale

        if (pan, tilt, zoom) != (cam.ptz_pan, cam.ptz_tilt, cam.ptz_zoom):
            ok, msg = cam.send_ptz(pan, tilt, zoom)
            if not ok and cam.connected and any(abs(v) > 0 for v in (pan, tilt, zoom)):
                # Lightly rate-limit by only logging transitions from stopped to active if rejected.
                self.log(f"CAM{cam.cam_id}: {msg}")
        self.after(40, self._ptz_tick)

    def _preview_tick(self):
        for cam in self.cameras:
            ui = self.camera_ui.get(cam.cam_id)
            if not ui:
                continue
            label = ui["preview_label"]
            frame, size, err = cam.get_preview_frame()
            if frame is not None and PREVIEW_PIL:
                try:
                    image = Image.fromarray(frame)
                    target_w = max(320, label.winfo_width())
                    target_h = max(180, label.winfo_height())
                    src_w, src_h = image.size
                    scale = min(target_w / src_w, target_h / src_h)
                    draw_w = max(1, int(src_w * scale))
                    draw_h = max(1, int(src_h * scale))
                    if image.size != (draw_w, draw_h):
                        image = image.resize((draw_w, draw_h), Image.Resampling.BILINEAR)
                    canvas = Image.new("RGB", (target_w, target_h), (0, 0, 0))
                    paste_x = (target_w - draw_w) // 2
                    paste_y = (target_h - draw_h) // 2
                    canvas.paste(image, (paste_x, paste_y))
                    photo = ImageTk.PhotoImage(image=canvas)
                    label.configure(image=photo, text="")
                    ui["preview_photo"] = photo
                    if size[0] and size[1]:
                        ui["preview_info"].config(text=f"Preview {size[0]}x{size[1]} → 16:9 live view")
                except Exception as e:
                    label.configure(image="", text=f"Preview draw error\n{e}", fg="#ff6b6b")
                    ui["preview_photo"] = None
            else:
                if cam.connected:
                    msg = err or ("Preview waiting..." if (PREVIEW_NUMPY and PREVIEW_PIL) else "Install numpy + pillow")
                    label.configure(image="", text=msg, fg="#9aa0aa")
                    ui["preview_photo"] = None
                else:
                    label.configure(image="", text="Preview idle", fg="#9aa0aa")
                    ui["preview_photo"] = None
                    ui["preview_info"].config(text="16:9 in-app preview for monitoring.")
        self.after(50, self._preview_tick)

    def apply_mode(self, cam_id: int):
        cam = self.cameras[cam_id - 1]
        ui = self.camera_ui[cam_id]
        cam.cfg.mode = ui["mode_var"].get()
        if cam.connected:
            ok, msg = cam.connect()
            if ok:
                cam.start_preview()
            self.log(msg)
            self._refresh_camera_status(cam_id)

    def update_speed_scale(self, cam_id: int):
        cam = self.cameras[cam_id - 1]
        ui = self.camera_ui[cam_id]
        cam.cfg.speed_scale = float(ui["speed_var"].get())


    def connect_camera(self, cam_id: int):
        cam = self.cameras[cam_id - 1]
        ui = self.camera_ui[cam_id]
        cam.cfg.source_name = ui["source_var"].get().strip()
        ok, msg = cam.connect()
        if ok:
            cam.start_preview()
        self.log(msg)
        self._refresh_camera_status(cam_id)

    def disconnect_camera(self, cam_id: int):
        cam = self.cameras[cam_id - 1]
        cam.disconnect()
        self.log(f"CAM{cam_id} disconnected")
        self._refresh_camera_status(cam_id)

    def stop_camera(self, cam_id: int):
        cam = self.cameras[cam_id - 1]
        ok, msg = cam.send_ptz(0.0, 0.0, 0.0)
        if ok:
            self.log(f"CAM{cam_id}: stop")

    def recall_preset_all(self, preset_1_based: int):
        if not (1 <= preset_1_based <= PRESET_COUNT):
            return
        count = 0
        for cam in self.cameras:
            if cam.connected:
                ok, msg = cam.recall_preset(preset_1_based - 1)
                self.log(f"CAM{cam.cam_id}: {msg} {'OK' if ok else 'FAIL'}")
                count += 1
        if count == 0:
            self.log(f"ALL CAMS: preset {preset_1_based} skipped (no connected cameras)")
        else:
            self.log(f"ALL CAMS: recalled preset {preset_1_based} on {count} connected camera(s)")

    def recall_preset(self, cam_id: int, preset_1_based: int):
        if not (1 <= cam_id <= MAX_CAMERAS and 1 <= preset_1_based <= PRESET_COUNT):
            return
        cam = self.cameras[cam_id - 1]
        ok, msg = cam.recall_preset(preset_1_based - 1)
        self.log(f"CAM{cam_id}: {msg} {'OK' if ok else 'FAIL'}")

    def store_preset(self, cam_id: int, preset_1_based: int):
        if not (1 <= cam_id <= MAX_CAMERAS and 1 <= preset_1_based <= PRESET_COUNT):
            return
        cam = self.cameras[cam_id - 1]
        ok, msg = cam.store_preset(preset_1_based - 1)
        self.log(f"CAM{cam_id}: {msg} {'OK' if ok else 'FAIL'}")

    def select_camera(self, cam_id: int):
        self.selected_cam = cam_id
        self.notebook.select(cam_id - 1)
        state = "ON" if self.app_hotkeys_enabled else "OFF"
        self.status_label.config(text=f"Selected CAM{cam_id} | Arrow keys=PTZ | +/-=Zoom | 1~8=Preset | Ctrl+1~4=Select Camera | Hotkeys {state}")
        for c in self.cameras:
            btn = self.camera_ui[c.cam_id]["select_btn"]
            btn.config(relief=("sunken" if c.cam_id == cam_id else "raised"))

    def _refresh_camera_status(self, cam_id: int):
        cam = self.cameras[cam_id - 1]
        ui = self.camera_ui[cam_id]
        if cam.connected:
            ui["status"].config(text=f"● Connected: {cam.cfg.source_name}", fg="#7dd87d")
        else:
            txt = "● Disconnected" if not cam.last_error else f"● Error: {cam.last_error}"
            ui["status"].config(text=txt, fg="#ff6b6b")

    def _on_tab_changed(self, _event=None):
        idx = self.notebook.index(self.notebook.select())
        self.select_camera(idx + 1)

    def _tk_keypress(self, event):
        if not self.app_hotkeys_enabled:
            return
        k = event.keysym
        mapping = {
            'Up': 'up', 'Down': 'down', 'Left': 'left', 'Right': 'right',
            'plus': 'zoom_in', 'equal': 'zoom_in', 'KP_Add': 'zoom_in',
            'minus': 'zoom_out', 'KP_Subtract': 'zoom_out'
        }
        if k in mapping:
            self.keys_down.add(mapping[k])
        if event.state & 0x4:  # Ctrl
            if event.keysym in ('1', '2', '3', '4'):
                self.select_camera(int(event.keysym))
                return
        if event.keysym in tuple(str(i) for i in range(1, 9)):
            if event.state & 0x1:  # Shift
                self.store_preset(self.selected_cam, int(event.keysym))
            else:
                self.recall_preset(self.selected_cam, int(event.keysym))

    def _tk_keyrelease(self, event):
        if not self.app_hotkeys_enabled:
            return
        k = event.keysym
        mapping = {
            'Up': 'up', 'Down': 'down', 'Left': 'left', 'Right': 'right',
            'plus': 'zoom_in', 'equal': 'zoom_in', 'KP_Add': 'zoom_in',
            'minus': 'zoom_out', 'KP_Subtract': 'zoom_out'
        }
        if k in mapping:
            self.keys_down.discard(mapping[k])

    def on_key_press(self, key, ctrl_down=False, shift_down=False):
        # Global hotkeys intentionally ignored unless app is focused.
        if not self.app_hotkeys_enabled:
            return
        try:
            if hasattr(key, 'char') and key.char:
                ch = key.char
                if ctrl_down and ch in '1234':
                    self.queue_action(lambda c=int(ch): self.select_camera(c))
                    return
                if ch in '12345678':
                    if shift_down:
                        self.queue_action(lambda c=self.selected_cam, p=int(ch): self.store_preset(c, p))
                    else:
                        self.queue_action(lambda c=self.selected_cam, p=int(ch): self.recall_preset(c, p))
                    return
                if ch in ('+', '='):
                    self.keys_down.add('zoom_in')
                    return
                if ch == '-':
                    self.keys_down.add('zoom_out')
                    return
            if key == keyboard.Key.up:
                self.keys_down.add('up')
            elif key == keyboard.Key.down:
                self.keys_down.add('down')
            elif key == keyboard.Key.left:
                self.keys_down.add('left')
            elif key == keyboard.Key.right:
                self.keys_down.add('right')
        except Exception:
            pass

    def on_key_release(self, key):
        if not self.app_hotkeys_enabled:
            return
        try:
            if hasattr(key, 'char') and key.char:
                ch = key.char
                if ch in ('+', '='):
                    self.keys_down.discard('zoom_in')
                elif ch == '-':
                    self.keys_down.discard('zoom_out')
            if key == keyboard.Key.up:
                self.keys_down.discard('up')
            elif key == keyboard.Key.down:
                self.keys_down.discard('down')
            elif key == keyboard.Key.left:
                self.keys_down.discard('left')
            elif key == keyboard.Key.right:
                self.keys_down.discard('right')
        except Exception:
            pass

    def handle_virtual_key(self, cam_id: int, action: str, is_press: bool):
        self.select_camera(cam_id)
        if is_press:
            self.keys_down.add(action)
        else:
            self.keys_down.discard(action)

    def open_studio_monitor(self):
        candidates = [
            Path(r"C:\Program Files\NDI\NDI 6 Tools\Studio Monitor\Application.Network.StudioMonitor.x64.exe"),
            Path(r"C:\Program Files\NDI\NDI 5 Tools\Studio Monitor\Application.Network.StudioMonitor.x64.exe"),
            Path(r"C:\Program Files\NDI\NDI 5 Tools\Studio Monitor.exe"),
        ]
        for path in candidates:
            if path.exists():
                try:
                    subprocess.Popen([str(path)])
                    self.log("Opened NDI Studio Monitor")
                    return
                except Exception as e:
                    self.log(f"Failed to open Studio Monitor: {e}")
                    return
        self.log("Studio Monitor not found")

    def on_close(self):
        self.polling = False
        self.save_config()
        self.stop_osc()
        if self.key_listener:
            self.key_listener.stop()
        for cam in self.cameras:
            cam.disconnect()
        try:
            self.wrapper.shutdown()
        except Exception:
            pass
        self.destroy()


def main():
    try:
        wrapper = NDIWrapper()
    except Exception as e:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(APP_NAME, str(e))
        raise
    app = NDIControllerApp(wrapper)
    app.select_camera(1)
    app.manual_refresh_sources()
    app.mainloop()


if __name__ == "__main__":
    main()
