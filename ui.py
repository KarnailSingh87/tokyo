from __future__ import annotations

import json
import math
import os
import platform
import random
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil

if platform.system() == "Windows":
    _WIN_HIDE: dict = {"creationflags": subprocess.CREATE_NO_WINDOW}
else:
    _WIN_HIDE: dict = {}

from PyQt6.QtCore import (
    QEasingCurve, QMimeData, QObject, QPointF, QRectF, QSize, Qt,
    QTimer, QUrl, pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush, QColor, QConicalGradient, QDragEnterEvent, QDropEvent, QFont,
    QFontDatabase, QKeySequence, QLinearGradient, QPainter, QPainterPath,
    QPen, QPixmap, QRadialGradient, QShortcut,
)
from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QPushButton, QScrollArea, QSizePolicy, QSplitter,
    QStackedWidget, QTextEdit, QVBoxLayout, QWidget, QProgressBar,
)

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent

BASE_DIR   = _base_dir()
CONFIG_DIR = BASE_DIR / "config"
API_FILE   = CONFIG_DIR / "api_keys.json"


def _read_full_config() -> dict:
    """Read api_keys.json config dict. Returns {} on any error."""
    try:
        return json.loads(API_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


_DEFAULT_W, _DEFAULT_H = 980, 700
_MIN_W,     _MIN_H     = 820, 580
_LEFT_W  = 148
_RIGHT_W = 340

_OS = platform.system()  # "Windows" | "Darwin" | "Linux"


class C:
    BG        = "#000000"
    PANEL     = "#070707"
    PANEL2    = "#0e0e0e"
    BORDER    = "#181818"
    BORDER_B  = "#242424"
    BORDER_A  = "#1c1c1c"
    PRI       = "#00f0ff"
    PRI_DIM   = "#38bdf8"
    PRI_GHO   = "#0a1926"
    ACC       = "#ff2a70"
    ACC2      = "#9d4edd"
    GREEN     = "#00f5a0"
    GREEN_D   = "#00c878"
    RED       = "#ff4757"
    MUTED_C   = "#ff4757"
    TEXT      = "#f1f5f9"
    TEXT_DIM  = "#555b6e"
    TEXT_MED  = "#8892b0"
    WHITE     = "#ffffff"
    DARK      = "#000000"
    BAR_BG    = "#0a0a0a"


# Ana renge (accent) bağlı anahtarlar — durum renkleri (ACC, GREEN, RED…) sabit kalır
_HUE_LINKED = (
    "PANEL", "PANEL2", "BORDER", "BORDER_B", "BORDER_A",
    "PRI", "PRI_DIM", "PRI_GHO", "TEXT", "TEXT_DIM", "TEXT_MED",
    "WHITE", "BAR_BG",
)
_PALETTE_DEFAULTS: dict[str, str] = {k: getattr(C, k) for k in _HUE_LINKED}

DEFAULT_UI_COLOR = _PALETTE_DEFAULTS["PRI"]


def apply_ui_accent(accent_hex: str) -> bool:
    """
    Seçilen accent rengine göre paleti yeniden türetir.
    BG ve DARK daima saf siyah (#000000) kalır.
    """
    import colorsys

    accent_hex = (accent_hex or "").strip().lower()
    if not (accent_hex.startswith("#") and len(accent_hex) == 7):
        return False
    try:
        int(accent_hex[1:], 16)
    except ValueError:
        return False

    def _hsv(h: str) -> tuple[float, float, float]:
        r = int(h[1:3], 16) / 255
        g = int(h[3:5], 16) / 255
        b = int(h[5:7], 16) / 255
        return colorsys.rgb_to_hsv(r, g, b)

    base_h            = _hsv(_PALETTE_DEFAULTS["PRI"])[0]
    acc_h, acc_s, _av = _hsv(accent_hex)
    dh   = acc_h - base_h
    grey = acc_s < 0.08

    for key, hex0 in _PALETTE_DEFAULTS.items():
        h, s, v = _hsv(hex0)
        if grey:
            s *= 0.15
        r, g, b = colorsys.hsv_to_rgb((h + dh) % 1.0, s, v)
        setattr(C, key, "#{:02x}{:02x}{:02x}".format(
            int(r * 255 + 0.5), int(g * 255 + 0.5), int(b * 255 + 0.5)))
    C.BG = "#000000"
    C.DARK = "#000000"
    return True


def current_palette() -> dict[str, str]:
    """C sınıfındaki accent'e bağlı renklerin anlık kopyası."""
    return {k: getattr(C, k) for k in _HUE_LINKED}


def retheme_all_widgets(old: dict[str, str], new: dict[str, str]) -> None:
    """
    CANLI tam tema değişimi. Uygulamadaki HER widget'ın stylesheet'inde eski
    palet renklerini yenileriyle değiştirir ve yeniden çizdirir. Böylece renk
    değişimi yalnızca boyanan öğelerde değil, panel/buton/kenarlık dahil tüm
    arayüzde ANINDA uygulanır — yeniden başlatma gerekmez.
    """
    mapping = {old[k].lower(): new[k].lower()
               for k in old if old[k].lower() != new.get(k, old[k]).lower()}
    if not mapping:
        return
    app = QApplication.instance()
    if app is None:
        return
    for w in app.allWidgets():
        try:
            ss = w.styleSheet()
            if ss:
                s2 = ss
                for o, n in mapping.items():
                    if o in s2:
                        s2 = s2.replace(o, n)
                if s2 != ss:
                    w.setStyleSheet(s2)
            w.update()
        except Exception:
            pass


def qcol(h: str, a: int = 255) -> QColor:
    c = QColor(h); c.setAlpha(a); return c


def app_font(size: int = 9, bold: bool = False, italic: bool = False) -> QFont:
    """Universal modern sans-serif font family matching system standards without alias lookup lag."""
    f = QFont()
    f.setStyleHint(QFont.StyleHint.SansSerif)
    f.setPointSize(size)
    if bold:
        f.setWeight(QFont.Weight.DemiBold)
    if italic:
        f.setItalic(True)
    return f


# ── Windows GPU via NVML DLL (no subprocess, no console window) ──────────────
_nvml_lib: object = None   # cached ctypes DLL
_nvml_ok:  object = None   # None=untested, True=works, False=unavailable


def _nvml_gpu_windows() -> float:
    """Return NVIDIA GPU utilisation % using nvml.dll directly — zero subprocess."""
    global _nvml_lib, _nvml_ok
    if _nvml_ok is False:
        return -1.0
    try:
        import ctypes

        class _Util(ctypes.Structure):
            _fields_ = [("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]

        if _nvml_lib is None:
            for dll_name in ("nvml", r"C:\Windows\System32\nvml.dll"):
                try:
                    lib = ctypes.WinDLL(dll_name)
                    lib.nvmlInit_v2()
                    _nvml_lib = lib
                    break
                except Exception:
                    continue

        if _nvml_lib is None:
            import pynvml  # type: ignore
            pynvml.nvmlInit()
            h = pynvml.nvmlDeviceGetHandleByIndex(0)
            _nvml_ok = True
            return float(pynvml.nvmlDeviceGetUtilizationRates(h).gpu)

        dev = ctypes.c_void_p()
        _nvml_lib.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(dev))
        util = _Util()
        _nvml_lib.nvmlDeviceGetUtilizationRates(dev, ctypes.byref(util))
        _nvml_ok = True
        return float(util.gpu)
    except Exception:
        _nvml_ok = False
        return -1.0


class _SysMetrics:
    def __init__(self):
        self.cpu  = 0.0
        self.mem  = 0.0
        self.net  = 0.0   
        self.gpu  = -1.0  
        self.tmp  = -1.0  
        self._lock = threading.Lock()
        self._last_net = psutil.net_io_counters()
        self._last_net_t = time.time()
        self._running = True
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def _loop(self):
        while self._running:
            try:
                self._update()
            except Exception:
                pass
            time.sleep(1.5)

    def _update(self):
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory().percent

        nc  = psutil.net_io_counters()
        now = time.time()
        dt  = now - self._last_net_t
        if dt > 0:
            sent = (nc.bytes_sent - self._last_net.bytes_sent) / dt
            recv = (nc.bytes_recv - self._last_net.bytes_recv) / dt
            net  = (sent + recv) / (1024 * 1024)
        else:
            net = 0.0
        self._last_net   = nc
        self._last_net_t = now

        gpu = self._get_gpu()

        tmp = self._get_temp()

        with self._lock:
            self.cpu = cpu
            self.mem = mem
            self.net = net
            self.gpu = gpu
            self.tmp = tmp

    def _get_gpu(self) -> float:
        # pynvml — subprocess-free, works on all platforms if installed
        try:
            import pynvml  # type: ignore
            pynvml.nvmlInit()
            h = pynvml.nvmlDeviceGetHandleByIndex(0)
            return float(pynvml.nvmlDeviceGetUtilizationRates(h).gpu)
        except Exception:
            pass

        # Windows: nvml.dll via ctypes (already cached in _nvml_gpu_windows)
        if _OS == "Windows":
            return _nvml_gpu_windows()

        # Linux / macOS: libnvidia-ml shared lib via ctypes
        try:
            import ctypes
            _lib = "libnvidia-ml.so.1" if _OS == "Linux" else "libnvidia-ml.dylib"

            class _Util(ctypes.Structure):
                _fields_ = [("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]

            nv = ctypes.CDLL(_lib)
            nv.nvmlInit_v2()
            dev = ctypes.c_void_p()
            nv.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(dev))
            u = _Util()
            nv.nvmlDeviceGetUtilizationRates(dev, ctypes.byref(u))
            return float(u.gpu)
        except Exception:
            pass

        return -1.0   # N/A — zero subprocess on all platforms

    def _get_temp(self) -> float:
        # psutil — works on Linux; occasionally Windows with driver support
        try:
            temps = psutil.sensors_temperatures()
            for name in ["coretemp", "k10temp", "cpu_thermal", "acpitz",
                         "cpu-thermal", "zenpower", "it8688"]:
                if name in temps and temps[name]:
                    return temps[name][0].current
            for entries in temps.values():
                if entries:
                    return entries[0].current
        except Exception:
            pass

        # Windows: wmi module (pure Python COM, zero subprocess)
        if _OS == "Windows":
            try:
                import wmi  # type: ignore
                w = wmi.WMI(namespace="root/wmi")
                tz = w.MSAcpi_ThermalZoneTemperature()
                if tz:
                    return (tz[0].CurrentTemperature / 10.0) - 273.15
            except Exception:
                pass

        return -1.0   # N/A — zero subprocess on all platforms

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "cpu": self.cpu,
                "mem": self.mem,
                "net": self.net,
                "gpu": self.gpu,
                "tmp": self.tmp,
            }


_metrics = _SysMetrics()

class HudCanvas(QWidget):
    def __init__(self, face_path: str, assistant_name: str = "TOKYO", parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setMinimumSize(320, 320)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.muted    = False
        self.speaking = False
        self.state    = "ONLINE"
        self._assistant_name = assistant_name
        self.subtitle = ""
        self._subtitle_alpha = 0.0
        self._subtitle_target_alpha = 0.0

        self._tick = 0
        self._t    = 0.0
        self._energy = 0.35
        self._target_energy = 0.35
        self._halo = 60.0

        # Fluid blob rotation angles
        self._blob_rotations = [0.0, 0.8, 1.6, 2.4]

        # Orbiting glowing stardust particles
        self._particles: list[dict] = []
        for _ in range(26):
            self._particles.append({
                "angle": random.uniform(0, 2 * math.pi),
                "dist": random.uniform(0.40, 0.95),
                "speed": random.uniform(0.003, 0.010),
                "size": random.uniform(1.2, 2.4),
                "alpha": random.uniform(0.2, 0.8),
                "color_idx": random.randint(0, 3),
            })

        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._tmr.start(16)  # 60 FPS

    def set_subtitle(self, text: str):
        self.subtitle = text.strip()
        self._subtitle_target_alpha = 1.0 if self.subtitle else 0.0
        self.update()

    def _step(self):
        self._tick += 1
        self._t += 0.016

        # Target energy based on state
        if self.muted:
            self._target_energy = 0.10
        elif self.speaking:
            self._target_energy = 0.95 + 0.20 * math.sin(self._t * 6.0)
        elif self.state in ("THINKING", "PROCESSING"):
            self._target_energy = 0.70 + 0.15 * math.sin(self._t * 4.0)
        elif self.state == "LISTENING":
            self._target_energy = 0.48 + 0.10 * math.sin(self._t * 2.5)
        else:
            self._target_energy = 0.32 + 0.04 * math.sin(self._t * 1.6)

        # Smooth energy interpolation
        lerp_sp = 0.12 if self.speaking else 0.07
        self._energy += (self._target_energy - self._energy) * lerp_sp

        # Dynamic rotation
        rot_speeds = [0.014, -0.012, 0.018, -0.009] if not self.speaking else [0.038, -0.032, 0.045, -0.024]
        for i in range(4):
            self._blob_rotations[i] += rot_speeds[i]

        # Update orbiting stardust particles
        for p in self._particles:
            p["angle"] += p["speed"] * (2.0 if self.speaking else 1.0)
            p["alpha"] = 0.25 + 0.45 * (0.5 + 0.5 * math.sin(self._t * 2.0 + p["angle"]))

        # Subtitle alpha fade
        self._subtitle_alpha += (self._subtitle_target_alpha - self._subtitle_alpha) * 0.08

        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        W, H = self.width(), self.height()
        cx, cy = W / 2.0, H / 2.0 - 32.0
        fw = min(W, H)

        # Deep pure OLED black background
        p.fillRect(self.rect(), QColor("#000000"))

        e = max(0.10, min(1.25, self._energy))

        # 1. Focused Ambient Glow behind orb (tight radius, pure black background outside)
        r_ambient = fw * 0.28
        ambient_grad = QRadialGradient(cx, cy, r_ambient)
        if self.muted:
            ambient_grad.setColorAt(0.0, QColor(255, 71, 87, int(35 * e)))
            ambient_grad.setColorAt(0.6, QColor(157, 78, 221, int(15 * e)))
            ambient_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        else:
            ambient_grad.setColorAt(0.0, QColor(0, 240, 255, int(50 * e)))
            ambient_grad.setColorAt(0.4, QColor(157, 78, 221, int(35 * e)))
            ambient_grad.setColorAt(0.75, QColor(255, 42, 112, int(20 * e)))
            ambient_grad.setColorAt(1.0, QColor(0, 0, 0, 0))

        p.setBrush(QBrush(ambient_grad))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(cx - r_ambient, cy - r_ambient, r_ambient * 2, r_ambient * 2))

        # 2. Ambient Stardust Micro-particles
        palette = [
            QColor(0, 240, 255),
            QColor(255, 42, 112),
            QColor(157, 78, 221),
            QColor(0, 245, 160),
        ]
        for pt in self._particles:
            pr = fw * 0.32 * pt["dist"]
            px = cx + math.cos(pt["angle"]) * pr
            py = cy + math.sin(pt["angle"]) * pr
            pcol = QColor(palette[pt["color_idx"]])
            pcol.setAlpha(int(pt["alpha"] * 255 * min(1.0, e * 1.2)))
            p.setBrush(QBrush(pcol))
            p.drawEllipse(QPointF(px, py), pt["size"], pt["size"])

        # 3. Siri Fluid Morphing Orb (Layered organic harmonic lobes)
        r_base = fw * 0.17 * (1.0 + 0.10 * self._energy)

        lobes = [
            (QColor(0, 240, 255, int(195 * e)), QColor(67, 97, 238, 0), self._blob_rotations[0], [0.15, 0.09, 0.07, 0.03], (math.cos(self._t * 1.2) * 10 * e, math.sin(self._t * 1.5) * 8 * e)),
            (QColor(255, 42, 112, int(185 * e)), QColor(157, 78, 221, 0), self._blob_rotations[1], [0.14, 0.11, 0.05, 0.04], (math.sin(self._t * 1.4) * -9 * e, math.cos(self._t * 1.1) * 9 * e)),
            (QColor(157, 78, 221, int(175 * e)), QColor(0, 240, 255, 0), self._blob_rotations[2], [0.16, 0.08, 0.09, 0.03], (math.cos(self._t * 0.9) * 7 * e, math.sin(self._t * 1.3) * -10 * e)),
            (QColor(255, 170, 0, int(130 * e)), QColor(255, 42, 112, 0), self._blob_rotations[3], [0.11, 0.13, 0.04, 0.05], (math.sin(self._t * 1.8) * 8 * e, math.cos(self._t * 1.6) * -7 * e)),
        ]

        if self.muted:
            lobes = [
                (QColor(255, 71, 87, int(160 * e)), QColor(120, 20, 40, 0), self._blob_rotations[0], [0.07, 0.03, 0.02, 0.01], (0, 0)),
                (QColor(180, 50, 80, int(140 * e)), QColor(60, 10, 20, 0), self._blob_rotations[1], [0.05, 0.03, 0.01, 0.01], (0, 0)),
            ]

        num_points = 80
        for grad_c, grad_e, rot, weights, (ox, oy) in lobes:
            path = QPainterPath()
            pts = []
            for i in range(num_points):
                theta = (i / num_points) * 2 * math.pi
                w1, w2, w3, w4 = weights
                dr = (
                    w1 * math.sin(2 * theta + rot + self._t * 2.0) +
                    w2 * math.cos(3 * theta - rot + self._t * 1.7) +
                    w3 * math.sin(4 * theta + rot * 1.5 + self._t * 2.4) +
                    w4 * math.cos(5 * theta - rot * 0.8)
                ) * self._energy

                r = r_base * (1.0 + dr)
                px = cx + ox + r * math.cos(theta)
                py = cy + oy + r * math.sin(theta)
                pts.append(QPointF(px, py))

            if pts:
                path.moveTo(pts[0])
                for pt in pts[1:]:
                    path.lineTo(pt)
                path.closeSubpath()

                lobe_grad = QRadialGradient(cx + ox, cy + oy, r_base * 1.4)
                lobe_grad.setColorAt(0.0, grad_c)
                lobe_grad.setColorAt(0.7, QColor(grad_c.red(), grad_c.green(), grad_c.blue(), int(grad_c.alpha() * 0.4)))
                lobe_grad.setColorAt(1.0, grad_e)

                p.setBrush(QBrush(lobe_grad))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawPath(path)

        # 4. Luminous White-Hot Core
        r_core = r_base * 0.65 * (0.9 + 0.12 * math.sin(self._t * 3.0) * self._energy)
        core_grad = QRadialGradient(cx, cy, r_core)
        if self.muted:
            core_grad.setColorAt(0.0, QColor(255, 230, 235, int(220 * e)))
            core_grad.setColorAt(0.4, QColor(255, 71, 87, int(150 * e)))
            core_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        else:
            core_grad.setColorAt(0.0, QColor(255, 255, 255, int(245 * e)))
            core_grad.setColorAt(0.35, QColor(180, 245, 255, int(195 * e)))
            core_grad.setColorAt(0.75, QColor(157, 78, 221, int(110 * e)))
            core_grad.setColorAt(1.0, QColor(0, 0, 0, 0))

        p.setBrush(QBrush(core_grad))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(cx - r_core, cy - r_core, r_core * 2, r_core * 2))

        # 5. Glowing Orbital Light Ribbons
        if not self.muted:
            for idx, (rx_f, ry_f, tilt, speed, color_a, color_b) in enumerate([
                (1.32, 0.42, 25.0, 1.2, QColor(0, 240, 255), QColor(255, 42, 112)),
                (1.22, 0.38, -35.0, -0.9, QColor(157, 78, 221), QColor(0, 245, 160)),
            ]):
                p.save()
                p.translate(cx, cy)
                p.rotate(tilt + math.sin(self._t * 0.5 + idx) * 8.0)

                ring_rx = r_base * rx_f
                ring_ry = r_base * ry_f

                ring_grad = QConicalGradient(0, 0, (self._t * speed * 60) % 360)
                alpha_val = int(min(220, 140 * self._energy))
                c1 = QColor(color_a); c1.setAlpha(alpha_val)
                c2 = QColor(color_b); c2.setAlpha(alpha_val)
                c_trans = QColor(0, 0, 0, 0)

                ring_grad.setColorAt(0.0, c1)
                ring_grad.setColorAt(0.3, c_trans)
                ring_grad.setColorAt(0.5, c2)
                ring_grad.setColorAt(0.8, c_trans)
                ring_grad.setColorAt(1.0, c1)

                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(QBrush(ring_grad), 2.2))
                p.drawEllipse(QRectF(-ring_rx, -ring_ry, ring_rx * 2, ring_ry * 2))
                p.restore()

        # 6. Siri Sound Wave Ribbons
        wy = cy + r_base * 1.45 + 14.0
        wave_w = min(W * 0.75, 420.0)
        wx0 = cx - wave_w / 2.0

        wave_layers = [
            (QColor(0, 240, 255, int(220 * e)), 1.0, 1.0, 0.0),
            (QColor(255, 42, 112, int(200 * e)), 1.3, 1.4, 1.5),
            (QColor(157, 78, 221, int(190 * e)), 0.8, 0.9, 3.0),
            (QColor(0, 245, 160, int(170 * e)), 1.1, 1.2, 4.5),
        ]
        if self.muted:
            wave_layers = [(QColor(255, 71, 87, int(140 * e)), 0.5, 0.5, 0.0)]

        wave_steps = 60
        for w_col, freq_mul, spd_mul, phase_off in wave_layers:
            w_path = QPainterPath()
            max_amp = (24.0 if self.speaking else (6.0 if self.state == "LISTENING" else 3.0)) * self._energy

            for s in range(wave_steps + 1):
                prog = s / wave_steps
                x = wx0 + prog * wave_w
                env = math.sin(prog * math.pi) ** 1.8

                k = 2.0 * math.pi * freq_mul / wave_w * 2.5
                omega = (self._t * 4.0 * spd_mul) + phase_off

                wave_val = (
                    math.sin(k * (x - wx0) - omega) +
                    0.4 * math.sin(2.2 * k * (x - wx0) + 0.8 * omega) +
                    0.2 * math.cos(3.1 * k * (x - wx0) - 1.2 * omega)
                )

                y = wy + wave_val * max_amp * env

                if s == 0:
                    w_path.moveTo(x, y)
                else:
                    w_path.lineTo(x, y)

            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(w_col, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            p.drawPath(w_path)

        # 7. Subtitle / Prompt Transcript (if active)
        if self.subtitle and self._subtitle_alpha > 0.05:
            sub_w = min(W * 0.80, 520.0)
            sub_h = 36.0
            sub_y = wy + 20.0
            sub_rect = QRectF(cx - sub_w / 2.0, sub_y, sub_w, sub_h)

            p.setBrush(QBrush(QColor(8, 8, 8, int(230 * self._subtitle_alpha))))
            p.setPen(QPen(QColor(40, 40, 40, int(100 * self._subtitle_alpha)), 1.0))
            p.drawRoundedRect(sub_rect, 10.0, 10.0)

            p.setFont(app_font(8))
            p.setPen(QPen(QColor(245, 245, 245, int(240 * self._subtitle_alpha))))
            p.drawText(sub_rect.adjusted(12, 0, -12, 0), Qt.AlignmentFlag.AlignCenter, self.subtitle)
        else:
            # 8. Clean Minimal Status Pill
            sy = wy + 24.0
            if self.muted:
                st_text = "Muted"
                dot_col = QColor(255, 71, 87)
            elif self.speaking:
                st_text = "Speaking"
                dot_col = QColor(0, 240, 255)
            elif self.state in ("THINKING", "PROCESSING"):
                st_text = "Thinking"
                dot_col = QColor(157, 78, 221)
            elif self.state == "LISTENING":
                st_text = "Listening"
                dot_col = QColor(0, 245, 160)
            else:
                st_text = "Ready"
                dot_col = QColor(0, 240, 255)

            pill_w, pill_h = 100.0, 24.0
            pill_rect = QRectF(cx - pill_w / 2.0, sy, pill_w, pill_h)

            p.setBrush(QBrush(QColor(255, 255, 255, 10)))
            p.setPen(QPen(QColor(255, 255, 255, 20), 1.0))
            p.drawRoundedRect(pill_rect, 12.0, 12.0)

            dot_alpha = int(180 + 75 * math.sin(self._t * 4.0))
            dot_c = QColor(dot_col); dot_c.setAlpha(dot_alpha)
            p.setBrush(QBrush(dot_c))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(cx - 30.0, sy + 12.0), 3.0, 3.0)

            p.setFont(app_font(7, bold=True))
            p.setPen(QPen(QColor(230, 240, 250, 220)))
            p.drawText(QRectF(cx - 18.0, sy, 60.0, pill_h), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, st_text)


class MetricBar(QWidget):
    def __init__(self, label: str, color: str = C.PRI, parent=None):
        super().__init__(parent)
        self._label = label
        self._color = color
        self._value = 0.0       # 0–100
        self._text  = "--"
        self.setFixedHeight(38)
        self.setMinimumWidth(80)

    def set_value(self, pct: float, text: str):
        self._value = max(0.0, min(100.0, pct))
        self._text  = text
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()

        p.setBrush(QBrush(qcol(C.PANEL2, 200)))
        p.setPen(QPen(qcol(C.BORDER, 150), 1))
        p.drawRoundedRect(QRectF(1, 1, W - 2, H - 2), 8, 8)

        bar_h   = 4
        bar_y   = H - bar_h - 7
        bar_w   = W - 16
        bar_x   = 8
        fill_w  = int(bar_w * self._value / 100)

        p.setBrush(QBrush(qcol(C.BAR_BG)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(bar_x, bar_y, bar_w, bar_h), 2, 2)

        if self._value > 85:
            bar_col = qcol(C.RED)
        elif self._value > 65:
            bar_col = qcol(C.ACC)
        else:
            bar_col = qcol(self._color)

        if fill_w > 0:
            fill_grad = QLinearGradient(bar_x, 0, bar_x + fill_w, 0)
            fill_grad.setColorAt(0.0, bar_col)
            fill_grad.setColorAt(1.0, qcol(C.PRI if bar_col != qcol(C.RED) else C.ACC))
            p.setBrush(QBrush(fill_grad))
            p.drawRoundedRect(QRectF(bar_x, bar_y, fill_w, bar_h), 2, 2)

        p.setFont(app_font(7, bold=True))
        p.setPen(QPen(qcol(C.TEXT_MED), 1))
        p.drawText(QRectF(10, 5, 50, 14), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._label)

        p.setFont(app_font(8, bold=True))
        p.setPen(QPen(bar_col if self._text != "--" else qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(0, 4, W - 10, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, self._text)


class LogWidget(QTextEdit):
    _sig = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(app_font(8))
        self.setStyleSheet(f"""
            QTextEdit {{
                background: {C.PANEL};
                color: {C.TEXT};
                border: 1px solid {C.BORDER};
                border-radius: 10px;
                padding: 8px;
                selection-background-color: {C.PRI_GHO};
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 6px;
                border: none;
                margin: 4px 2px 4px 0;
            }}
            QScrollBar::handle:vertical {{
                background: {C.BORDER_B};
                border-radius: 3px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {C.PRI_DIM};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """)
        self._queue: list[str] = []
        self._typing  = False
        self._text    = ""
        self._pos     = 0
        self._tag     = "sys"
        self._ai_name_lc = "tokyo"   # updated when assistant name changes
        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._sig.connect(self._enqueue)

    def append_log(self, text: str):
        self._sig.emit(text)

    def _enqueue(self, text: str):
        self._queue.append(text)
        if not self._typing:
            self._next()

    def _next(self):
        if not self._queue:
            self._typing = False
            return
        self._typing = True
        self._text   = self._queue.pop(0)
        self._pos    = 0
        tl = self._text.lower()
        _ai_pfx = f"{self._ai_name_lc}:"
        if   tl.startswith("you:"):                              self._tag = "you"
        elif tl.startswith(_ai_pfx) or tl.startswith("tokyo:"): self._tag = "ai"
        elif tl.startswith("file:"):                             self._tag = "file"
        elif "err" in tl:                                        self._tag = "err"
        else:                                                    self._tag = "sys"
        self._tmr.start(6)

    def _step(self):
        if self._pos < len(self._text):
            ch  = self._text[self._pos]
            cur = self.textCursor()
            fmt = cur.charFormat()
            col = {
                "you":  qcol(C.WHITE),
                "ai":   qcol(C.PRI),
                "err":  qcol(C.RED),
                "file": qcol(C.GREEN),
                "sys":  qcol(C.ACC2),
            }.get(self._tag, qcol(C.TEXT))
            fmt.setForeground(QBrush(col))
            cur.movePosition(cur.MoveOperation.End)
            cur.insertText(ch, fmt)
            self.setTextCursor(cur)
            self.ensureCursorVisible()
            self._pos += 1
        else:
            self._tmr.stop()
            cur = self.textCursor()
            cur.movePosition(cur.MoveOperation.End)
            cur.insertText("\n")
            self.setTextCursor(cur)
            self.ensureCursorVisible()
            QTimer.singleShot(20, self._next)

_FILE_ICONS = {
    "image":   ("🖼", "#00d4ff"), "video":   ("🎬", "#ff6b00"),
    "audio":   ("🎵", "#cc44ff"), "pdf":     ("📄", "#ff4444"),
    "word":    ("📝", "#4488ff"), "excel":   ("📊", "#44bb44"),
    "code":    ("💻", "#ffcc00"), "archive": ("📦", "#ff8844"),
    "pptx":    ("📊", "#ff6622"), "text":    ("📃", "#aaaaaa"),
    "data":    ("🔧", "#88ddff"), "unknown": ("📎", "#888888"),
}
_EXT_TO_CAT = {
    **dict.fromkeys(["jpg","jpeg","png","gif","webp","bmp","tiff","svg","ico"], "image"),
    **dict.fromkeys(["mp4","avi","mov","mkv","wmv","flv","webm","m4v"],         "video"),
    **dict.fromkeys(["mp3","wav","ogg","m4a","aac","flac","wma","opus"],        "audio"),
    **dict.fromkeys(["pdf"],                                                     "pdf"),
    **dict.fromkeys(["doc","docx"],                                              "word"),
    **dict.fromkeys(["xls","xlsx","ods"],                                        "excel"),
    **dict.fromkeys(["ppt","pptx"],                                              "pptx"),
    **dict.fromkeys(["py","js","ts","jsx","tsx","html","css","java","c","cpp",
                     "cs","go","rs","rb","php","swift","kt","sh","sql","lua"],   "code"),
    **dict.fromkeys(["zip","rar","tar","gz","7z","bz2","xz"],                   "archive"),
    **dict.fromkeys(["txt","md","rst","log"],                                    "text"),
    **dict.fromkeys(["csv","tsv","json","xml"],                                  "data"),
}

def _file_category(path: Path) -> str:
    return _EXT_TO_CAT.get(path.suffix.lower().lstrip("."), "unknown")

def _fmt_size(size: int) -> str:
    if   size < 1024:    return f"{size} B"
    elif size < 1024**2: return f"{size/1024:.1f} KB"
    elif size < 1024**3: return f"{size/1024**2:.1f} MB"
    else:                return f"{size/1024**3:.1f} GB"


class FileDropZone(QWidget):
    file_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(100)
        self._current_file: str | None = None
        self._hovering  = False
        self._drag_over = False
        self._dash_offset = 0.0
        self._anim_tmr = QTimer(self)
        self._anim_tmr.timeout.connect(self._animate)
        self._anim_tmr.start(40)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._canvas = _DropCanvas(self)
        layout.addWidget(self._canvas)

    def _animate(self):
        self._dash_offset = (self._dash_offset + 0.8) % 20
        self._canvas.update()

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._drag_over = True; self._canvas.update()

    def dragLeaveEvent(self, e):
        self._drag_over = False; self._canvas.update()

    def dropEvent(self, e: QDropEvent):
        self._drag_over = False
        urls = e.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if Path(path).is_file():
                self._set_file(path)
        self._canvas.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._browse()

    def enterEvent(self, e):
        self._hovering = True; self._canvas.update()

    def leaveEvent(self, e):
        self._hovering = False; self._canvas.update()

    def current_file(self) -> str | None:
        return self._current_file

    def clear_file(self):
        self._current_file = None; self._canvas.update()

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select a file for TOKYO", str(Path.home()),
            "All Files (*.*);;"
            "Images (*.jpg *.jpeg *.png *.gif *.webp *.bmp *.svg);;"
            "Documents (*.pdf *.docx *.txt *.md *.pptx);;"
            "Data (*.csv *.xlsx *.json *.xml);;"
            "Code (*.py *.js *.ts *.html *.css *.java *.cpp *.go);;"
            "Audio (*.mp3 *.wav *.ogg *.m4a *.aac *.flac);;"
            "Video (*.mp4 *.avi *.mov *.mkv *.wmv *.webm);;"
            "Archives (*.zip *.rar *.tar *.gz *.7z)",
        )
        if path:
            self._set_file(path)

    def _set_file(self, path: str):
        self._current_file = path
        self._canvas.update()
        self.file_selected.emit(path)


class _DropCanvas(QWidget):
    def __init__(self, zone: FileDropZone):
        super().__init__(zone)
        self._z = zone

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        z    = self._z
        W, H = self.width(), self.height()
        pad  = 4
        rect = QRectF(pad, pad, W - pad * 2, H - pad * 2)

        bg_col = qcol("#161a2b" if z._drag_over else ("#121624" if z._hovering else C.PANEL))
        p.setBrush(QBrush(bg_col)); p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(rect, 10, 10)

        if z._current_file:   border_col = qcol(C.GREEN, 220)
        elif z._drag_over:    border_col = qcol(C.PRI, 240)
        elif z._hovering:     border_col = qcol(C.PRI_DIM, 200)
        else:                 border_col = qcol(C.BORDER_B, 150)

        pen = QPen(border_col, 1.5, Qt.PenStyle.DashLine)
        pen.setDashOffset(z._dash_offset)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, 10, 10)

        if z._current_file:   self._paint_file(p, W, H)
        elif z._drag_over:    self._paint_drag_over(p, W, H)
        else:                 self._paint_idle(p, W, H, z._hovering)

    def _paint_idle(self, p, W, H, hover):
        cx, cy = W / 2, H / 2
        col = qcol(C.PRI if hover else C.TEXT_MED)
        p.setFont(app_font(12, bold=True))
        p.setPen(QPen(col, 1))
        p.drawText(QRectF(0, cy - 22, W, 20), Qt.AlignmentFlag.AlignCenter, "☁")

        p.setFont(app_font(8, bold=True))
        p.setPen(QPen(qcol(C.TEXT if hover else C.TEXT_MED), 1))
        p.drawText(QRectF(0, cy - 2, W, 16), Qt.AlignmentFlag.AlignCenter,
                   "Drop file here or click to browse")
        p.setFont(app_font(7))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(0, cy + 15, W, 14), Qt.AlignmentFlag.AlignCenter,
                   "PDF · Images · Video · Audio · Docs · Code")

    def _paint_drag_over(self, p, W, H):
        cx, cy = W / 2, H / 2
        p.setFont(app_font(16, bold=True))
        p.setPen(QPen(qcol(C.PRI), 1))
        p.drawText(QRectF(0, cy - 20, W, 24), Qt.AlignmentFlag.AlignCenter, "↓")
        p.setFont(app_font(8, bold=True))
        p.setPen(QPen(qcol(C.PRI), 1))
        p.drawText(QRectF(0, cy + 8, W, 16), Qt.AlignmentFlag.AlignCenter, "Release to load")

    def _paint_file(self, p, W, H):
        path = Path(self._z._current_file)
        cat  = _file_category(path)
        icon, icon_col = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])
        size_str = _fmt_size(path.stat().st_size)
        ext_str  = path.suffix.upper().lstrip(".") or "FILE"

        block_x, block_w = 8, 54
        p.setFont(QFont("Segoe UI Emoji", 20) if _OS == "Windows" else QFont("Arial", 20))
        p.setPen(QPen(qcol(icon_col), 1))
        p.drawText(QRectF(block_x, 0, block_w, H), Qt.AlignmentFlag.AlignCenter, icon)

        tx = block_x + block_w + 6
        tw = W - tx - 36

        p.setFont(app_font(8, bold=True))
        p.setPen(QPen(qcol(C.WHITE), 1))
        name = path.name if len(path.name) <= 32 else path.name[:29] + "..."
        p.drawText(QRectF(tx, H * 0.18, tw, 16),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)

        p.setFont(app_font(7))
        p.setPen(QPen(qcol(C.TEXT_MED), 1))
        p.drawText(QRectF(tx, H * 0.18 + 18, tw, 14),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   f"{ext_str}  ·  {size_str}")

        p.setFont(app_font(6))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        par = str(path.parent)
        if len(par) > 40: par = "…" + par[-39:]
        p.drawText(QRectF(tx, H * 0.18 + 34, tw, 12),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, par)

        p.setFont(app_font(9, bold=True))
        p.setPen(QPen(qcol(C.RED, 200), 1))
        p.drawText(QRectF(W - 32, 0, 26, H), Qt.AlignmentFlag.AlignCenter, "✕")

    def mousePressEvent(self, e):
        z = self._z
        if z._current_file and e.pos().x() > self.width() - 34:
            z.clear_file()
        else:
            z.mousePressEvent(e)


class _CameraPreview(QWidget):
    """Floating overlay that briefly shows what the camera captured."""

    _W, _H = 244, 188

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            _CameraPreview {{
                background: rgba(12, 14, 22, 0.95);
                border: 1px solid {C.BORDER_B};
                border-radius: 12px;
            }}
        """)
        self.setFixedWidth(self._W)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(6)

        hdr = QHBoxLayout()
        title = QLabel("VISUAL INPUT")
        title.setFont(app_font(7, bold=True))
        title.setStyleSheet(f"color: {C.PRI_DIM}; background: transparent; letter-spacing: 1px;")
        hdr.addWidget(title)
        hdr.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(18, 18)
        close_btn.setFont(app_font(8))
        close_btn.setStyleSheet(
            f"color: {C.TEXT_DIM}; background: transparent; border: none;"
        )
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.hide)
        hdr.addWidget(close_btn)
        lay.addLayout(hdr)

        self._img_lbl = QLabel()
        self._img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img_lbl.setStyleSheet("background: transparent; border-radius: 8px;")
        lay.addWidget(self._img_lbl)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

        self.hide()

    def show_frame(self, img_bytes: bytes) -> None:
        px = QPixmap()
        px.loadFromData(img_bytes)
        if not px.isNull():
            max_w = self._W - 16
            scaled = px.scaled(
                max_w, 160,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._img_lbl.setPixmap(scaled)
            self._img_lbl.setFixedSize(scaled.width(), scaled.height())
            self.adjustSize()
        self.show()
        self.raise_()
        self._timer.start(6_000)


class SetupOverlay(QWidget):
    done = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            SetupOverlay {{
                background: rgba(12, 14, 22, 0.96);
                border: 1px solid {C.BORDER_B};
                border-radius: 16px;
            }}
        """)

        detected = {"darwin": "mac", "windows": "windows"}.get(
            _OS.lower(), "linux"
        )
        self._sel_os = detected

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(12)

        def _lbl(txt, font_size=9, bold=False, color=C.WHITE, align=Qt.AlignmentFlag.AlignLeft):
            w = QLabel(txt)
            w.setAlignment(align)
            w.setFont(app_font(font_size, bold=bold))
            w.setStyleSheet(f"color: {color}; background: transparent;")
            return w

        layout.addWidget(_lbl("Setup", 13, True, color=C.WHITE))

        layout.addWidget(_lbl("API Key", 8, color=C.TEXT_MED))
        self._key_input = QLineEdit()
        self._key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_input.setPlaceholderText("Gemini API Key…")
        self._key_input.setFont(app_font(9))
        self._key_input.setFixedHeight(36)
        self._key_input.setStyleSheet(f"""
            QLineEdit {{
                background: {C.PANEL2}; color: {C.TEXT};
                border: 1px solid {C.BORDER}; border-radius: 10px; padding: 4px 12px;
            }}
            QLineEdit:focus {{ border: 1px solid {C.PRI}; }}
        """)
        layout.addWidget(self._key_input)

        layout.addWidget(_lbl("Platform", 8, color=C.TEXT_MED))
        os_row = QHBoxLayout(); os_row.setSpacing(8)
        self._os_btns: dict[str, QPushButton] = {}
        for key, label in [("windows","Windows"),("mac","macOS"),("linux","Linux")]:
            btn = QPushButton(label)
            btn.setFont(app_font(8, bold=True))
            btn.setFixedHeight(34)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, k=key: self._sel(k))
            os_row.addWidget(btn)
            self._os_btns[key] = btn
        layout.addLayout(os_row)
        self._sel(detected)

        layout.addSpacing(6)
        init_btn = QPushButton("Continue")
        init_btn.setFont(app_font(9, bold=True))
        init_btn.setFixedHeight(36)
        init_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        init_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.PRI}; color: #000000;
                border: none; border-radius: 10px; font-weight: bold;
            }}
            QPushButton:hover {{
                background: #38bdf8;
            }}
        """)
        init_btn.clicked.connect(self._submit)
        layout.addWidget(init_btn)

    def _sel(self, key: str):
        self._sel_os = key
        for k, btn in self._os_btns.items():
            if k == key:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {C.PRI_GHO}; color: {C.PRI};
                        border: 1px solid {C.PRI}; border-radius: 8px; font-weight: bold;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {C.PANEL2}; color: {C.TEXT_MED};
                        border: 1px solid {C.BORDER}; border-radius: 8px;
                    }}
                    QPushButton:hover {{ color: {C.WHITE}; border: 1px solid {C.BORDER_B}; }}
                """)

    def _submit(self):
        key = self._key_input.text().strip()
        if not key:
            self._key_input.setStyleSheet(
                self._key_input.styleSheet() +
                f" QLineEdit {{ border: 1px solid {C.RED}; }}"
            )
            return
        self.done.emit(key, self._sel_os)


class HueWheel(QWidget):
    hue_picked    = pyqtSignal(str)
    hue_committed = pyqtSignal(str)

    _RING = 16

    def __init__(self, initial_hex: str = DEFAULT_UI_COLOR, parent=None):
        super().__init__(parent)
        self.setFixedSize(130, 130)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hue  = 0.53
        self._drag = False
        self.set_color(initial_hex)

    def color(self) -> str:
        return QColor.fromHsvF(self._hue, 1.0, 1.0).name()

    def set_color(self, hex_str: str):
        c = QColor((hex_str or "").strip())
        if c.isValid() and c.hsvHueF() >= 0:
            self._hue = c.hsvHueF()
            self.update()

    def _ring_rect(self) -> QRectF:
        m = self._RING / 2 + 3
        return QRectF(self.rect()).adjusted(m, m, -m, -m)

    def _hue_from_pos(self, pos: QPointF) -> float:
        c  = QRectF(self.rect()).center()
        dx = pos.x() - c.x()
        dy = c.y() - pos.y()
        ang = math.atan2(dy, dx)
        return (ang / (2 * math.pi)) % 1.0

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect   = self._ring_rect()
        center = rect.center()

        grad = QConicalGradient(center, 0)
        for i in range(0, 361, 20):
            grad.setColorAt(i / 360.0, QColor.fromHsvF((i % 360) / 360.0, 1.0, 1.0))
        p.setPen(QPen(QBrush(grad), self._RING))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(rect)

        preview = QColor.fromHsvF(self._hue, 1.0, 1.0)
        inner   = rect.adjusted(24, 24, -24, -24)
        p.setPen(QPen(qcol(C.BORDER_B), 1))
        p.setBrush(QBrush(preview))
        p.drawEllipse(inner)

        r   = rect.width() / 2
        ang = self._hue * 2 * math.pi
        hx  = center.x() + r * math.cos(ang)
        hy  = center.y() - r * math.sin(ang)
        p.setPen(QPen(QColor("#00060a"), 2))
        p.setBrush(QBrush(QColor("#ffffff")))
        p.drawEllipse(QPointF(hx, hy), 6.5, 6.5)

    def mousePressEvent(self, e):
        self._drag = True
        self._hue  = self._hue_from_pos(e.position())
        self.update()
        self.hue_picked.emit(self.color())

    def mouseMoveEvent(self, e):
        if self._drag:
            self._hue = self._hue_from_pos(e.position())
            self.update()
            self.hue_picked.emit(self.color())

    def mouseReleaseEvent(self, e):
        if self._drag:
            self._drag = False
            self.hue_committed.emit(self.color())


class CustomizeOverlay(QWidget):
    saved = pyqtSignal(str, str, str)
    _OW, _OH = 360, 440

    def __init__(self, assistant_name="TOKYO", user_name="",
                 ui_color=DEFAULT_UI_COLOR, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            CustomizeOverlay {{
                background: rgba(12, 14, 22, 0.96);
                border: 1px solid {C.BORDER_B};
                border-radius: 16px;
            }}
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(8)

        def _lbl(txt, fs=8, bold=False, color=C.TEXT_MED, align=Qt.AlignmentFlag.AlignLeft):
            w = QLabel(txt); w.setAlignment(align)
            w.setFont(app_font(fs, bold=bold))
            w.setStyleSheet(f"color: {color}; background: transparent;")
            return w

        _fs = (f"QLineEdit {{ background: {C.PANEL2}; color: {C.TEXT}; "
               f"border: 1px solid {C.BORDER}; border-radius: 8px; padding: 4px 10px; }}"
               f"QLineEdit:focus {{ border: 1px solid {C.PRI}; }}")

        lay.addWidget(_lbl("Settings", 12, True, color=C.WHITE))
        lay.addSpacing(2)

        lay.addWidget(_lbl("Name"))
        self._name_input = QLineEdit(assistant_name)
        self._name_input.setFont(app_font(9))
        self._name_input.setFixedHeight(32)
        self._name_input.setStyleSheet(_fs)
        lay.addWidget(self._name_input)

        lay.addWidget(_lbl("User Name"))
        self._user_input = QLineEdit(user_name)
        self._user_input.setPlaceholderText("Optional")
        self._user_input.setFont(app_font(9))
        self._user_input.setFixedHeight(32)
        self._user_input.setStyleSheet(_fs)
        lay.addWidget(self._user_input)

        lay.addWidget(_lbl("Accent Color"))
        self._initial_color = (ui_color or DEFAULT_UI_COLOR).strip().lower()
        self._sel_color     = self._initial_color
        self.on_preview     = None

        self._wheel = HueWheel(self._sel_color)
        wheel_row = QHBoxLayout()
        wheel_row.addStretch(); wheel_row.addWidget(self._wheel); wheel_row.addStretch()
        lay.addLayout(wheel_row)
        self._wheel.hue_picked.connect(self._on_wheel_pick)
        self._wheel.hue_committed.connect(self._on_wheel_commit)

        self._hex_input = QLineEdit(self._sel_color)
        self._hex_input.setFont(app_font(8))
        self._hex_input.setFixedHeight(26)
        self._hex_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hex_input.setStyleSheet(_fs)
        self._hex_input.textEdited.connect(self._on_hex_edited)
        lay.addWidget(self._hex_input)

        lay.addSpacing(4)
        btn_row = QHBoxLayout(); btn_row.setSpacing(8)

        save_btn = QPushButton("Save")
        save_btn.setFixedHeight(34)
        save_btn.setFont(app_font(8, bold=True))
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.PRI}; color: #000000;
                border: none; border-radius: 8px; font-weight: bold;
            }}
            QPushButton:hover {{ background: #38bdf8; }}
        """)
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedHeight(34)
        cancel_btn.setFont(app_font(8))
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.PANEL2}; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 8px;
            }}
            QPushButton:hover {{ color: {C.WHITE}; border-color: {C.BORDER_B}; }}
        """)
        cancel_btn.clicked.connect(self._cancel)
        btn_row.addWidget(cancel_btn)
        lay.addLayout(btn_row)

    def _set_color(self, hx: str, update_wheel: bool = True, preview: bool = True):
        self._sel_color = hx.strip().lower()
        self._hex_input.blockSignals(True)
        self._hex_input.setText(self._sel_color)
        self._hex_input.blockSignals(False)
        if update_wheel:
            self._wheel.set_color(self._sel_color)
        if preview and self.on_preview:
            self.on_preview(self._sel_color)

    def _on_wheel_pick(self, hx: str):
        self._sel_color = hx
        self._hex_input.blockSignals(True)
        self._hex_input.setText(hx)
        self._hex_input.blockSignals(False)

    def _on_wheel_commit(self, hx: str):
        self._set_color(hx, update_wheel=False)

    def _on_hex_edited(self, text: str):
        t = text.strip().lower()
        if t.startswith("#") and len(t) == 7:
            try:
                int(t[1:], 16)
            except ValueError:
                return
            self._set_color(t, update_wheel=True, preview=True)

    def _cancel(self):
        if self.on_preview and self._sel_color != self._initial_color:
            self.on_preview(self._initial_color)
        self.hide()

    def _save(self):
        name = self._name_input.text().strip() or "TOKYO"
        user = self._user_input.text().strip()
        self.saved.emit(name, user, self._sel_color or DEFAULT_UI_COLOR)
        self.hide()


class PluginManagerOverlay(QWidget):
    _OW = 380

    def __init__(self, plugins: list[dict], parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            PluginManagerOverlay {{
                background: rgba(12, 14, 22, 0.96);
                border: 1px solid {C.BORDER_B};
                border-radius: 16px;
            }}
        """)
        self.setFixedWidth(self._OW)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(8)

        hdr = QLabel("Plugins")
        hdr.setFont(app_font(12, bold=True))
        hdr.setStyleSheet(f"color: {C.WHITE}; background: transparent;")
        lay.addWidget(hdr)

        if not plugins:
            empty = QLabel("No plugins found")
            empty.setFont(app_font(8))
            empty.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
            lay.addWidget(empty)

        for p in plugins:
            lay.addLayout(self._build_row(p))

        lay.addSpacing(6)
        close_btn = QPushButton("Done")
        close_btn.setFixedHeight(32)
        close_btn.setFont(app_font(8, bold=True))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.PRI}; color: #000000;
                border: none; border-radius: 8px; font-weight: bold;
            }}
            QPushButton:hover {{ background: #38bdf8; }}
        """)
        close_btn.clicked.connect(self.hide)
        lay.addWidget(close_btn)
        self.adjustSize()

    def _build_row(self, p: dict) -> QHBoxLayout:
        row = QHBoxLayout(); row.setSpacing(8)

        lbl = QLabel(p["name"])
        lbl.setFont(app_font(8))
        lbl.setStyleSheet(f"color: {C.TEXT if p['valid'] else C.TEXT_DIM}; background: transparent;")
        row.addWidget(lbl, stretch=1)

        btn = QPushButton()
        btn.setFixedSize(60, 24)
        btn.setFont(app_font(7, bold=True))
        if not p["valid"]:
            btn.setText("Error")
            btn.setEnabled(False)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {C.TEXT_DIM};
                    border: 1px solid {C.BORDER}; border-radius: 6px;
                }}
            """)
        else:
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._style_toggle(btn, p["enabled"])
            btn.clicked.connect(lambda _, name=p["name"], b=btn: self._toggle(name, b))
        row.addWidget(btn)
        return row

    def _style_toggle(self, btn: QPushButton, enabled: bool):
        if enabled:
            btn.setText("ON")
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: rgba(0, 245, 160, 0.15); color: {C.GREEN};
                    border: 1px solid rgba(0, 245, 160, 0.4); border-radius: 6px;
                }}
            """)
        else:
            btn.setText("OFF")
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {C.PANEL2}; color: {C.TEXT_DIM};
                    border: 1px solid {C.BORDER}; border-radius: 6px;
                }}
            """)

    def _toggle(self, name: str, btn: QPushButton):
        from memory.config_manager import get_plugin_enabled, save_plugin_enabled
        new_val = not get_plugin_enabled(name)
        save_plugin_enabled(name, new_val)
        self._style_toggle(btn, new_val)


class ClipboardPanel(QWidget):
    action_requested = pyqtSignal(str)
    _W, _H = 320, 95

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            ClipboardPanel {{
                background: rgba(12, 14, 22, 0.96);
                border: 1px solid {C.BORDER_B};
                border-radius: 12px;
            }}
        """)
        self.setFixedWidth(self._W)
        self._clip_text = ""

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(6)

        hdr = QHBoxLayout(); hdr.setSpacing(4)
        icon_lbl = QLabel("Clipboard")
        icon_lbl.setFont(app_font(7, bold=True))
        icon_lbl.setStyleSheet(f"color: {C.PRI_DIM}; background: transparent;")
        hdr.addWidget(icon_lbl); hdr.addStretch()
        x_btn = QPushButton("✕")
        x_btn.setFixedSize(16, 16)
        x_btn.setFont(app_font(8))
        x_btn.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none;")
        x_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        x_btn.clicked.connect(self.hide)
        hdr.addWidget(x_btn)
        lay.addLayout(hdr)

        btn_row = QHBoxLayout(); btn_row.setSpacing(6)
        _bs = (f"QPushButton {{ background: {C.PANEL2}; color: {C.TEXT_MED}; "
               f"border: 1px solid {C.BORDER}; border-radius: 6px; }}"
               f"QPushButton:hover {{ color: {C.PRI}; border-color: {C.PRI_DIM}; }}")
        for label, cmd_fmt in [
            ("Translate", "Translate this: {text}"),
            ("Summarise", "Summarise this: {text}"),
            ("Explain",   "Explain this: {text}"),
        ]:
            b = QPushButton(label)
            b.setFixedHeight(24)
            b.setFont(app_font(7))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(_bs)
            b.clicked.connect(lambda _, c=cmd_fmt: self._trigger(c))
            btn_row.addWidget(b)
        lay.addLayout(btn_row)

        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self.hide)
        self.hide()

    def _trigger(self, cmd_fmt: str):
        if self._clip_text:
            self.action_requested.emit(cmd_fmt.format(text=self._clip_text[:800]))
        self.hide()

    def show_clipboard(self, text: str):
        self._clip_text = text
        self.show(); self.raise_()
        self._dismiss_timer.start(8000)


class RemoteKeyOverlay(QWidget):
    closed = pyqtSignal()
    _OW, _OH = 360, 420

    def __init__(self, url: str, key: str, auto_login_url: str = "",
                 manual_url: str = "", expiry_secs: int = 600, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            RemoteKeyOverlay {{
                background: rgba(12, 14, 22, 0.96);
                border: 1px solid {C.BORDER_B};
                border-radius: 16px;
            }}
        """)
        self._expiry          = time.time() + expiry_secs
        self._on_new_key      = None
        self._auto_login_url  = auto_login_url
        self._manual_url      = manual_url or url

        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(8)

        def _lbl(txt, fs=8, bold=False, color=C.WHITE, align=Qt.AlignmentFlag.AlignCenter):
            w = QLabel(txt); w.setAlignment(align)
            w.setFont(app_font(fs, bold=bold))
            w.setStyleSheet(f"color: {color}; background: transparent;")
            return w

        lay.addWidget(_lbl("Remote Access", 12, True, color=C.WHITE))

        self._qr_label = QLabel()
        self._qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._qr_label.setFixedSize(160, 160)
        self._qr_label.setStyleSheet("background: white; border-radius: 10px; padding: 4px;")
        qr_row = QHBoxLayout()
        qr_row.addStretch(); qr_row.addWidget(self._qr_label); qr_row.addStretch()
        lay.addLayout(qr_row)

        self._update_qr(auto_login_url)

        self._key_lbl = QLabel(key)
        self._key_lbl.setFont(app_font(22, bold=True))
        self._key_lbl.setStyleSheet(f"""
            color: {C.ACC};
            background: {C.PANEL2};
            border: 1px solid {C.BORDER_B};
            border-radius: 8px;
            padding: 4px;
            letter-spacing: 6px;
        """)
        self._key_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._key_lbl)

        btn_row = QHBoxLayout(); btn_row.setSpacing(8)
        close_btn = QPushButton("Done")
        close_btn.setFixedHeight(32)
        close_btn.setFont(app_font(8, bold=True))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.PRI}; color: #000000;
                border: none; border-radius: 8px; font-weight: bold;
            }}
            QPushButton:hover {{ background: #38bdf8; }}
        """)
        close_btn.clicked.connect(self._do_close)
        btn_row.addWidget(close_btn)
        lay.addLayout(btn_row)

        self._ctimer = QTimer(self)
        self._ctimer.timeout.connect(self._tick)
        self._ctimer.start(1000)
        self._tick()

    def set_new_key_callback(self, fn) -> None:
        self._on_new_key = fn

    def _update_qr(self, url: str) -> None:
        if not url:
            self._qr_label.setText("—")
            return
        try:
            import qrcode as _qrmod
            from io import BytesIO
            qr = _qrmod.QRCode(
                box_size=4, border=1,
                error_correction=_qrmod.constants.ERROR_CORRECT_M,
            )
            qr.add_data(url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buf = BytesIO()
            img.save(buf, format="PNG")
            px = QPixmap()
            px.loadFromData(buf.getvalue())
            self._qr_label.setPixmap(
                px.scaled(150, 150,
                          Qt.AspectRatioMode.KeepAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
            )
        except Exception:
            self._qr_label.setText("QR unavailable")

    def _tick(self):
        rem = max(0, int(self._expiry - time.time()))
        if rem <= 0:
            self._do_close()

    def mark_connected(self) -> None:
        """Call from any thread when a phone successfully connects."""
        self._ctimer.stop()
        self._key_lbl.setText("CONNECTED")
        self._key_lbl.setStyleSheet(f"""
            color: {C.GREEN};
            background: rgba(34,197,94,0.08);
            border: 2px solid rgba(34,197,94,0.4);
            border-radius: 8px;
            padding: 6px 4px;
            letter-spacing: 4px;
        """)
        self._qr_label.setText("✓")
        self._qr_label.setFont(QFont("Courier New", 54, QFont.Weight.Bold))
        self._qr_label.setStyleSheet(
            "color: #00ff88; background: #001a0d; border-radius: 10px;"
        )
        self._timer_lbl.setText("Phone connected — TOKYO ready")
        self._timer_lbl.setStyleSheet(f"color: {C.GREEN}; background: transparent;")

    def _refresh_key(self):
        if self._on_new_key:
            result = self._on_new_key()
            if result:
                url    = result[0]
                key    = result[1]
                auto   = result[2] if len(result) >= 3 else ""
                manual = result[3] if len(result) >= 4 else url
                self._manual_url     = manual or url
                self._url_lbl.setText(self._manual_url)
                self._key_lbl.setText(key)
                self._auto_login_url = auto
                self._update_qr(auto or url)
                self._expiry = time.time() + 600
                self._key_lbl.setStyleSheet(f"""
                    color: {C.ACC};
                    background: {C.PANEL2};
                    border: 1px solid {C.BORDER_B};
                    border-radius: 8px;
                    padding: 6px 4px;
                    letter-spacing: 10px;
                """)
                self._timer_lbl.setStyleSheet(
                    f"color: {C.TEXT_MED}; background: transparent;"
                )
                self._ctimer.start(1000)
                self._tick()

    def _do_close(self):
        self._ctimer.stop()
        self.hide()
        self.closed.emit()


class MainWindow(QMainWindow):
    _log_sig        = pyqtSignal(str)
    _state_sig      = pyqtSignal(str)
    _content_sig    = pyqtSignal(str, str)   # (title, text) — thread-safe content display
    _reconfig_sig   = pyqtSignal()           # trigger setup overlay from any thread
    _camera_sig     = pyqtSignal(bytes)      # show camera frame preview (small overlay)
    _cam_stream_sig = pyqtSignal(bool)       # True=start live stream, False=stop
    _cam_frame_sig  = pyqtSignal(bytes)      # live camera frame → HUD area
    _clipboard_sig  = pyqtSignal(str)        # clipboard text changed (thread-safe)

    def __init__(self, face_path: str):
        super().__init__()
        self._face_path = face_path

        # Load customization from config
        _cfg = _read_full_config()
        self._assistant_name: str = (_cfg.get("assistant_name") or "TOKYO").strip()
        _display = self._assistant_name.upper()

        # Kayıtlı UI rengini panel/stylesheet'ler kurulmadan ÖNCE uygula
        _ui_color = (_cfg.get("ui_color") or "").strip()
        if _ui_color and _ui_color.lower() != DEFAULT_UI_COLOR:
            apply_ui_accent(_ui_color)

        self.setWindowTitle(f"{_display} — MARK LI")
        self.setMinimumSize(_MIN_W, _MIN_H)
        self.resize(_DEFAULT_W, _DEFAULT_H)

        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            (screen.width()  - _DEFAULT_W) // 2,
            (screen.height() - _DEFAULT_H) // 2,
        )

        self.on_text_command   = None
        self.on_remote_clicked = None   # callable: () -> (url, key) | None
        self.on_interrupt      = None   # callable: () -> None — stop TOKYO mid-speech
        self.get_plugins       = None   # callable: () -> list[dict], set by TokyoLive
        self._muted            = False
        self._current_file: str | None = None
        self._remote_overlay: RemoteKeyOverlay | None = None
        self._remote_overlay: RemoteKeyOverlay | None = None
        self._customize_overlay: CustomizeOverlay | None = None
        self._plugin_manager_overlay: PluginManagerOverlay | None = None

        central = QWidget()
        central.setStyleSheet(f"background: {C.BG};")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        # Center column: HUD + floating action dock
        center_col = QWidget()
        center_col_lay = QVBoxLayout(center_col)
        center_col_lay.setContentsMargins(0, 0, 0, 16)
        center_col_lay.setSpacing(10)

        self.hud = HudCanvas(face_path, _display)
        self.hud.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Live camera container
        _cam_cont = QWidget()
        _cam_cont.setStyleSheet("background: #000308;")
        _cam_v = QVBoxLayout(_cam_cont)
        _cam_v.setContentsMargins(0, 0, 0, 0)
        _cam_v.setSpacing(0)
        _cam_hdr = QHBoxLayout()
        _cam_hdr.setContentsMargins(12, 8, 12, 8)
        _cam_title = QLabel("CAMERA")
        _cam_title.setFont(app_font(8, bold=True))
        _cam_title.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        _cam_hdr.addWidget(_cam_title)
        _cam_hdr.addStretch()
        _cam_x = QPushButton("✕")
        _cam_x.setFont(app_font(8))
        _cam_x.setCursor(Qt.CursorShape.PointingHandCursor)
        _cam_x.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none;")
        _cam_x.clicked.connect(self.stop_camera_stream)
        _cam_hdr.addWidget(_cam_x)
        _cam_v.addLayout(_cam_hdr)
        self._cam_live_lbl = QLabel()
        self._cam_live_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cam_live_lbl.setStyleSheet("background: transparent;")
        self._cam_live_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        _cam_v.addWidget(self._cam_live_lbl, stretch=1)

        self._hud_cam_stack = QStackedWidget()
        self._hud_cam_stack.addWidget(self.hud)
        self._hud_cam_stack.addWidget(_cam_cont)
        center_col_lay.addWidget(self._hud_cam_stack, stretch=1)

        # Content / Briefing panel
        self._content_panel = self._build_content_panel()
        center_col_lay.addWidget(self._content_panel)

        # Floating Bottom Dock (Action Controls)
        self._dock_widget = self._build_floating_dock()
        center_col_lay.addWidget(self._dock_widget)

        # Text prompt input row (collapsible / toggleable)
        self._input_row_widget = self._build_input_container()
        center_col_lay.addWidget(self._input_row_widget)

        body.addWidget(center_col, stretch=1)

        # Collapsible right-side Activity & Files drawer (hidden by default)
        self._right_panel = self._build_right_panel()
        self._right_panel.hide()
        body.addWidget(self._right_panel, stretch=0)

        root.addLayout(body, stretch=1)

        self._quick_drawer = self._build_quick_drawer()
        self._update_autostart_btn(self._check_autostart())
        from memory.config_manager import get_brief_enabled as _gbe
        self._update_brief_btn(_gbe())
        self._metric_tmr = QTimer(self)
        self._metric_tmr.timeout.connect(self._update_metrics)
        self._metric_tmr.start(2000)
        self._update_metrics()

        self._log_sig.connect(self._handle_log_event)
        self._state_sig.connect(self._apply_state)
        self._content_sig.connect(self._show_content)
        self._reconfig_sig.connect(self._show_setup)
        self._camera_sig.connect(self._show_camera_frame)
        self._cam_stream_sig.connect(self._on_cam_stream)
        self._cam_frame_sig.connect(self._on_cam_frame)
        self._clipboard_sig.connect(self._show_clipboard_panel)
        self._cam_stop = threading.Event()

        self._cam_preview = _CameraPreview(self.centralWidget())
        self._clipboard_panel = ClipboardPanel(self.centralWidget())
        self._clipboard_panel.action_requested.connect(self._on_clipboard_action)
        QApplication.clipboard().dataChanged.connect(self._on_clipboard_changed)

        self._overlay: SetupOverlay | None = None
        self._ready = self._check_config()
        if not self._ready:
            self._show_setup()

        sc_mute = QShortcut(QKeySequence("F4"), self)
        sc_mute.activated.connect(self._toggle_mute)
        sc_full = QShortcut(QKeySequence("F11"), self)
        sc_full.activated.connect(self._toggle_fullscreen)
        sc_intr = QShortcut(QKeySequence("Escape"), self)
        sc_intr.activated.connect(self._do_interrupt)

    def _handle_log_event(self, text: str):
        self._log.append_log(text)
        # Show clean subtitle if spoken by assistant or user
        if text.startswith(f"{self._assistant_name}:"):
            speech = text.split(":", 1)[1].strip()
            self.hud.set_subtitle(speech)
        elif text.startswith("You:"):
            speech = text.split(":", 1)[1].strip()
            self.hud.set_subtitle(f'"{speech}"')

    def _show_camera_frame(self, img_bytes: bytes):
        self._cam_preview.show_frame(img_bytes)
        cw = self.centralWidget()
        pw = _CameraPreview._W
        ph = self._cam_preview.height()
        self._cam_preview.setGeometry(
            cw.width() - pw - 18,
            cw.height() - ph - 28,
            pw, ph,
        )

    def _on_cam_stream(self, start: bool) -> None:
        if start:
            self._hud_cam_stack.setCurrentIndex(1)
        else:
            self._hud_cam_stack.setCurrentIndex(0)
            self._cam_live_lbl.clear()

    def _on_cam_frame(self, data: bytes) -> None:
        px = QPixmap()
        px.loadFromData(data)
        if not px.isNull():
            w, h = self._cam_live_lbl.width(), self._cam_live_lbl.height()
            if w > 1 and h > 1:
                self._cam_live_lbl.setPixmap(
                    px.scaled(w, h,
                              Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
                )

    def start_camera_stream(self) -> None:
        if self._hud_cam_stack.currentIndex() == 1:
            self.stop_camera_stream()
            return
        self._cam_stop.clear()
        self._cam_stream_sig.emit(True)
        t = threading.Thread(target=self._cam_loop, daemon=True, name="cam-stream")
        t.start()

    def _cam_loop(self) -> None:
        try:
            import cv2
            cam_idx = 0
            try:
                import json as _j
                cfg = _j.loads((CONFIG_DIR / "api_keys.json").read_text(encoding="utf-8"))
                cam_idx = int(cfg.get("camera_index", 0))
            except Exception:
                pass
            try:
                backend = cv2.CAP_DSHOW if _OS == "Windows" else cv2.CAP_ANY
            except AttributeError:
                backend = 0
            cap = cv2.VideoCapture(cam_idx, backend)
            if not cap.isOpened():
                cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                return
            for _ in range(5):
                cap.read()
            while not self._cam_stop.wait(0.033) and cap.isOpened():
                ret, frame = cap.read()
                if ret and frame is not None:
                    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 65])
                    self._cam_frame_sig.emit(buf.tobytes())
            cap.release()
        except Exception as e:
            print(f"[Camera] Stream error: {e}")
        finally:
            self._cam_stream_sig.emit(False)

    def stop_camera_stream(self) -> None:
        self._cam_stop.set()

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _toggle_side_drawer(self):
        if self._right_panel.isVisible():
            self._right_panel.hide()
            self._history_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {C.PANEL2}; color: {C.TEXT_MED};
                    border: 1px solid {C.BORDER}; border-radius: 8px;
                }}
                QPushButton:hover {{ color: {C.WHITE}; border-color: {C.BORDER_B}; }}
            """)
        else:
            self._right_panel.show()
            self._history_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {C.PRI_GHO}; color: {C.PRI};
                    border: 1px solid {C.PRI}; border-radius: 8px;
                }}
            """)

    def _toggle_input_row(self):
        if self._input_row_widget.isVisible():
            self._input_row_widget.hide()
        else:
            self._input_row_widget.show()
            self._input.setFocus()

    def _open_file_picker(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Upload File", str(Path.home()),
            "All Files (*.*);;Images (*.jpg *.jpeg *.png *.webp);;Documents (*.pdf *.docx *.txt *.md)",
        )
        if path:
            self._on_file_selected(path)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cw = self.centralWidget()
        if self._overlay and self._overlay.isVisible():
            ow, oh = 380, 320
            self._overlay.setGeometry(
                (cw.width()  - ow) // 2,
                (cw.height() - oh) // 2,
                ow, oh,
            )
        if self._remote_overlay and self._remote_overlay.isVisible():
            ow, oh = RemoteKeyOverlay._OW, RemoteKeyOverlay._OH
            self._remote_overlay.setGeometry(
                (cw.width()  - ow) // 2,
                (cw.height() - oh) // 2,
                ow, oh,
            )
        if self._customize_overlay and self._customize_overlay.isVisible():
            ow, oh = CustomizeOverlay._OW, CustomizeOverlay._OH
            self._customize_overlay.setGeometry(
                (cw.width()  - ow) // 2,
                (cw.height() - oh) // 2,
                ow, oh,
            )
        pw = _CameraPreview._W
        ph = self._cam_preview.height() or _CameraPreview._H
        self._cam_preview.setGeometry(
            cw.width() - pw - 18,
            cw.height() - ph - 28,
            pw, ph,
        )
        if hasattr(self, '_clipboard_panel') and self._clipboard_panel.isVisible():
            self._position_clipboard_panel()
        if hasattr(self, '_quick_drawer') and self._quick_drawer.isVisible():
            self._position_quick_drawer()

    def _update_metrics(self):
        snap = _metrics.snapshot()
        cpu = snap["cpu"]
        self._bar_cpu.set_value(cpu, f"{cpu:.0f}%")
        mem = snap["mem"]
        self._bar_mem.set_value(mem, f"{mem:.0f}%")
        net = snap["net"]
        net_str = f"{net*1024:.0f}KB/s" if net < 1.0 else f"{net:.1f}MB/s"
        self._bar_net.set_value(min(100, net * 10), net_str)
        gpu = snap["gpu"]
        self._bar_gpu.set_value(gpu if gpu >= 0 else 0, f"{gpu:.0f}%" if gpu >= 0 else "N/A")

    def _build_header(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(50)
        w.setStyleSheet(f"background: transparent;")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(20, 0, 20, 0)
        lay.setSpacing(12)

        # Left brand
        brand_box = QHBoxLayout(); brand_box.setSpacing(8)
        self._brand_dot = QLabel("●")
        self._brand_dot.setFont(app_font(7))
        self._brand_dot.setStyleSheet(f"color: {C.GREEN}; background: transparent;")
        brand_box.addWidget(self._brand_dot)

        _disp = self._assistant_name.upper()
        self._title_lbl = QLabel(_disp)
        self._title_lbl.setFont(app_font(10, bold=True))
        self._title_lbl.setStyleSheet(f"color: {C.WHITE}; background: transparent; letter-spacing: 1px;")
        brand_box.addWidget(self._title_lbl)
        lay.addLayout(brand_box)

        lay.addStretch()

        # Right Action Icons
        actions = QHBoxLayout(); actions.setSpacing(8)

        self._history_btn = QPushButton("💬")
        self._history_btn.setFixedSize(30, 30)
        self._history_btn.setFont(app_font(10))
        self._history_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._history_btn.setToolTip("Activity & Files")
        self._history_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.PANEL2}; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 8px;
            }}
            QPushButton:hover {{ color: {C.WHITE}; border-color: {C.BORDER_B}; }}
        """)
        self._history_btn.clicked.connect(self._toggle_side_drawer)
        actions.addWidget(self._history_btn)

        self._drawer_btn = QPushButton("⚙")
        self._drawer_btn.setFixedSize(30, 30)
        self._drawer_btn.setFont(app_font(10))
        self._drawer_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._drawer_btn.setToolTip("Settings")
        self._drawer_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.PANEL2}; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 8px;
            }}
            QPushButton:hover {{ color: {C.WHITE}; border-color: {C.BORDER_B}; }}
        """)
        self._drawer_btn.clicked.connect(self._toggle_drawer)
        actions.addWidget(self._drawer_btn)

        fs_btn = QPushButton("⛶")
        fs_btn.setFixedSize(30, 30)
        fs_btn.setFont(app_font(10))
        fs_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        fs_btn.setToolTip("Fullscreen")
        fs_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.PANEL2}; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 8px;
            }}
            QPushButton:hover {{ color: {C.WHITE}; border-color: {C.BORDER_B}; }}
        """)
        fs_btn.clicked.connect(self._toggle_fullscreen)
        actions.addWidget(fs_btn)

        lay.addLayout(actions)
        return w

    def _build_floating_dock(self) -> QWidget:
        """Floating glass capsule centered at bottom (like ChatGPT / Gemini Live)."""
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        capsule = QWidget()
        capsule.setStyleSheet(f"""
            QWidget {{
                background: rgba(10, 10, 10, 0.96);
                border: 1px solid {C.BORDER_B};
                border-radius: 28px;
            }}
        """)
        c_lay = QHBoxLayout(capsule)
        c_lay.setContentsMargins(14, 8, 14, 8)
        c_lay.setSpacing(12)

        # 1. Attachment / Upload button
        upload_btn = QPushButton("📎")
        upload_btn.setFixedSize(38, 38)
        upload_btn.setFont(app_font(11))
        upload_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        upload_btn.setToolTip("Upload file")
        upload_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.PANEL2}; color: {C.TEXT};
                border: 1px solid {C.BORDER}; border-radius: 19px;
            }}
            QPushButton:hover {{ background: #181818; border-color: {C.BORDER_B}; }}
        """)
        upload_btn.clicked.connect(self._open_file_picker)
        c_lay.addWidget(upload_btn)

        # 2. Camera Stream button
        cam_btn = QPushButton("📷")
        cam_btn.setFixedSize(38, 38)
        cam_btn.setFont(app_font(11))
        cam_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cam_btn.setToolTip("Visual Input")
        cam_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.PANEL2}; color: {C.TEXT};
                border: 1px solid {C.BORDER}; border-radius: 19px;
            }}
            QPushButton:hover {{ background: #181818; border-color: {C.BORDER_B}; }}
        """)
        cam_btn.clicked.connect(self.start_camera_stream)
        c_lay.addWidget(cam_btn)

        # 3. Hero Microphone Button (Glowing circle in the center)
        self._mute_btn = QPushButton("🎙")
        self._mute_btn.setFixedSize(48, 48)
        self._mute_btn.setFont(app_font(14, bold=True))
        self._mute_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mute_btn.setToolTip("Mute / Unmute [F4 / Space]")
        self._mute_btn.clicked.connect(self._toggle_mute)
        self._style_mute_btn()
        c_lay.addWidget(self._mute_btn)

        # 4. Text Input Toggle button
        chat_btn = QPushButton("💬")
        chat_btn.setFixedSize(38, 38)
        chat_btn.setFont(app_font(11))
        chat_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        chat_btn.setToolTip("Type Message")
        chat_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.PANEL2}; color: {C.TEXT};
                border: 1px solid {C.BORDER}; border-radius: 19px;
            }}
            QPushButton:hover {{ background: #181818; border-color: {C.BORDER_B}; }}
        """)
        chat_btn.clicked.connect(self._toggle_input_row)
        c_lay.addWidget(chat_btn)

        # 5. Stop / Interrupt Button
        self._interrupt_btn = QPushButton("✕")
        self._interrupt_btn.setFixedSize(38, 38)
        self._interrupt_btn.setFont(app_font(11, bold=True))
        self._interrupt_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._interrupt_btn.setToolTip("Stop [Esc]")
        self._interrupt_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(255, 71, 87, 0.14); color: #ff6b81;
                border: 1px solid rgba(255, 71, 87, 0.35); border-radius: 19px;
            }}
            QPushButton:hover {{
                background: rgba(255, 71, 87, 0.28); color: #ffffff;
            }}
        """)
        self._interrupt_btn.clicked.connect(self._do_interrupt)
        c_lay.addWidget(self._interrupt_btn)

        lay.addWidget(capsule)
        return w

    def _build_input_container(self) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        input_pill = QWidget()
        input_pill.setFixedWidth(460)
        input_pill.setStyleSheet(f"""
            QWidget {{
                background: rgba(10, 10, 10, 0.96);
                border: 1px solid {C.BORDER_B};
                border-radius: 20px;
            }}
        """)
        p_lay = QHBoxLayout(input_pill)
        p_lay.setContentsMargins(12, 4, 6, 4)
        p_lay.setSpacing(6)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Ask anything or type command…")
        self._input.setFont(app_font(8))
        self._input.setFixedHeight(28)
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: transparent; color: {C.WHITE};
                border: none; padding: 0 4px;
            }}
        """)
        self._input.returnPressed.connect(self._send)
        p_lay.addWidget(self._input)

        send_btn = QPushButton("↑")
        send_btn.setFixedSize(28, 28)
        send_btn.setFont(app_font(10, bold=True))
        send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        send_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.PRI}; color: #000000;
                border: none; border-radius: 14px; font-weight: bold;
            }}
            QPushButton:hover {{ background: #38bdf8; }}
        """)
        send_btn.clicked.connect(self._send)
        p_lay.addWidget(send_btn)

        lay.addWidget(input_pill)
        w.hide()  # Hidden by default until 💬 clicked
        return w

    def _build_right_panel(self) -> QWidget:
        """Collapsible side drawer for Activity Log and File Uploads."""
        w = QWidget()
        w.setFixedWidth(320)
        w.setStyleSheet(f"background: {C.PANEL}; border-left: 1px solid {C.BORDER};")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(10)

        # Header
        hdr = QHBoxLayout()
        title = QLabel("Activity")
        title.setFont(app_font(9, bold=True))
        title.setStyleSheet(f"color: {C.WHITE}; background: transparent;")
        hdr.addWidget(title)
        hdr.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(22, 22)
        close_btn.setFont(app_font(8))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none;")
        close_btn.clicked.connect(self._toggle_side_drawer)
        hdr.addWidget(close_btn)
        lay.addLayout(hdr)

        # Telemetry
        self._bar_cpu = MetricBar("CPU", C.PRI)
        self._bar_mem = MetricBar("MEM", C.ACC2)
        self._bar_net = MetricBar("NET", C.GREEN)
        self._bar_gpu = MetricBar("GPU", C.ACC)
        for b in [self._bar_cpu, self._bar_mem, self._bar_net, self._bar_gpu]:
            lay.addWidget(b)

        # Log
        self._log = LogWidget()
        lay.addWidget(self._log, stretch=1)

        # File drop
        self._drop_zone = FileDropZone()
        self._drop_zone.file_selected.connect(self._on_file_selected)
        lay.addWidget(self._drop_zone)

        return w

    def _toggle_drawer(self, checked: bool):
        if checked:
            self._position_quick_drawer()
            self._quick_drawer.show()
            self._quick_drawer.raise_()
        else:
            self._quick_drawer.hide()

    def _position_quick_drawer(self):
        if not hasattr(self, '_quick_drawer'):
            return
        _W = 220
        self._quick_drawer.setFixedWidth(_W)
        self._quick_drawer.adjustSize()
        self._quick_drawer.setGeometry(12, 54, _W, self._quick_drawer.sizeHint().height())

    def _build_input_row(self) -> QHBoxLayout:
        row = QHBoxLayout(); row.setSpacing(8)
        self._input = QLineEdit()
        self._input.setPlaceholderText("Type a command or question…")
        self._input.setFont(app_font(8))
        self._input.setFixedHeight(34)
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: {C.PANEL2}; color: {C.WHITE};
                border: 1px solid {C.BORDER}; border-radius: 10px; padding: 4px 12px;
            }}
            QLineEdit:focus {{ border: 1px solid {C.PRI}; background: #161b2a; }}
        """)
        self._input.returnPressed.connect(self._send)
        row.addWidget(self._input)

        send = QPushButton("↑")
        send.setFixedSize(34, 34)
        send.setFont(app_font(11, bold=True))
        send.setCursor(Qt.CursorShape.PointingHandCursor)
        send.setStyleSheet(f"""
            QPushButton {{
                background: {C.PRI}; color: #000000;
                border: none; border-radius: 10px; font-weight: bold;
            }}
            QPushButton:hover {{ background: #38bdf8; }}
            QPushButton:pressed {{ background: #0284c7; }}
        """)
        send.clicked.connect(self._send)
        row.addWidget(send)
        return row

    def _build_content_panel(self) -> QWidget:
        """
        Collapsible panel below the HUD — shows search results, news, briefings.
        Hidden by default; appears when show_content() is called.
        """
        w = QWidget()
        w.setObjectName("ContentPanel")
        w.setStyleSheet(f"""
            QWidget#ContentPanel {{
                background: {C.PANEL};
                border-top: 1px solid {C.BORDER};
                border-radius: 12px 12px 0 0;
            }}
        """)
        w.hide()

        lay = QVBoxLayout(w)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(6)

        # ── header row ───────────────────────────────────────────────────────
        hdr = QHBoxLayout(); hdr.setSpacing(6)

        self._content_title_lbl = QLabel("BRIEFING")
        self._content_title_lbl.setFont(app_font(8, bold=True))
        self._content_title_lbl.setStyleSheet(
            f"color: {C.PRI}; background: transparent; letter-spacing: 1px;"
        )
        hdr.addWidget(self._content_title_lbl)
        hdr.addStretch()

        self._content_ts_lbl = QLabel("")
        self._content_ts_lbl.setFont(app_font(7))
        self._content_ts_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        hdr.addWidget(self._content_ts_lbl)

        dismiss = QPushButton("Dismiss ✕")
        dismiss.setFont(app_font(7))
        dismiss.setFixedHeight(22)
        dismiss.setCursor(Qt.CursorShape.PointingHandCursor)
        dismiss.setStyleSheet(f"""
            QPushButton {{
                background: {C.PANEL2}; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 6px; padding: 0 8px;
            }}
            QPushButton:hover {{ color: {C.WHITE}; border-color: {C.BORDER_B}; }}
        """)
        dismiss.clicked.connect(w.hide)
        hdr.addWidget(dismiss)
        lay.addLayout(hdr)

        # ── text display ──────────────────────────────────────────────────────
        self._content_display = QTextEdit()
        self._content_display.setReadOnly(True)
        self._content_display.setFont(app_font(8))
        self._content_display.setMinimumHeight(60)
        self._content_display.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._content_display.setStyleSheet(f"""
            QTextEdit {{
                background: {C.DARK};
                color: {C.TEXT};
                border: 1px solid {C.BORDER};
                border-radius: 8px;
                padding: 8px 10px;
                selection-background-color: {C.PRI_GHO};
            }}
            QScrollBar:vertical {{
                background: transparent; width: 6px; border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {C.BORDER_B}; border-radius: 3px; min-height: 16px;
            }}
        """)
        lay.addWidget(self._content_display)
        return w

    def _show_content(self, title: str, text: str):
        """Slot — runs on Qt main thread. Updates and shows the content panel."""
        import time as _time
        self._content_title_lbl.setText(title.upper()[:48])
        self._content_ts_lbl.setText(_time.strftime("%H:%M:%S"))
        self._content_display.setPlainText(text)
        self._content_display.moveCursor(
            self._content_display.textCursor().MoveOperation.Start
        )
        self._content_panel.show()

    def _build_quick_drawer(self) -> QWidget:
        """Floating overlay panel shown when the ⚙ header button is toggled."""
        _BTN_STYLE = f"""
            QPushButton {{
                background: {C.PANEL2}; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 8px;
                text-align: left; padding: 0 10px;
            }}
            QPushButton:hover {{ color: {C.WHITE}; border-color: {C.BORDER_B}; }}
        """

        w = QWidget(self.centralWidget())
        w.setObjectName("QuickDrawer")
        w.setStyleSheet(f"""
            QWidget#QuickDrawer {{
                background: rgba(12, 14, 22, 0.96);
                border: 1px solid {C.BORDER_B};
                border-radius: 12px;
            }}
        """)
        w.hide()

        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 10, 12, 12)
        lay.setSpacing(6)

        hdr = QLabel("Quick Menu")
        hdr.setFont(app_font(8, bold=True))
        hdr.setStyleSheet(f"color: {C.WHITE}; background: transparent; padding-bottom: 4px;")
        lay.addWidget(hdr)

        remote_btn = QPushButton("Remote Access")
        remote_btn.setFixedHeight(28)
        remote_btn.setFont(app_font(7, bold=True))
        remote_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remote_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.PRI_GHO}; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 8px;
                text-align: left; padding: 0 10px;
            }}
            QPushButton:hover {{ background: {C.PRI}; color: #000000; }}
        """)
        remote_btn.clicked.connect(self._open_remote)
        lay.addWidget(remote_btn)

        cust_btn = QPushButton("Customise Assistant")
        cust_btn.setFixedHeight(28)
        cust_btn.setFont(app_font(7))
        cust_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cust_btn.setStyleSheet(_BTN_STYLE)
        cust_btn.clicked.connect(self._open_customize)
        lay.addWidget(cust_btn)

        self._autostart_btn = QPushButton("Auto-Start: OFF")
        self._autostart_btn.setFixedHeight(28)
        self._autostart_btn.setFont(app_font(7))
        self._autostart_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._autostart_btn.setStyleSheet(_BTN_STYLE)
        self._autostart_btn.clicked.connect(self._toggle_autostart)
        lay.addWidget(self._autostart_btn)

        self._brief_btn = QPushButton("Morning Brief: OFF")
        self._brief_btn.setFixedHeight(28)
        self._brief_btn.setFont(app_font(7))
        self._brief_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._brief_btn.setStyleSheet(_BTN_STYLE)
        self._brief_btn.clicked.connect(self._toggle_brief)
        lay.addWidget(self._brief_btn)

        plugin_btn = QPushButton("Plugins")
        plugin_btn.setFixedHeight(28)
        plugin_btn.setFont(app_font(7))
        plugin_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        plugin_btn.setStyleSheet(_BTN_STYLE)
        plugin_btn.clicked.connect(self._open_plugin_manager)
        lay.addWidget(plugin_btn)

        w.adjustSize()
        return w

    def _toggle_drawer(self):
        if self._quick_drawer.isVisible():
            self._quick_drawer.hide()
        else:
            self._position_quick_drawer()
            self._quick_drawer.show()
            self._quick_drawer.raise_()

    def _position_quick_drawer(self):
        if not hasattr(self, '_quick_drawer'):
            return
        _W = 200
        self._quick_drawer.setFixedWidth(_W)
        self._quick_drawer.adjustSize()
        cw = self.centralWidget()
        self._quick_drawer.setGeometry(cw.width() - _W - 16, 50, _W, self._quick_drawer.sizeHint().height())

    def _on_file_selected(self, path: str):
        self._current_file = path
        p    = Path(path)
        cat  = _file_category(p)
        icon, _ = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])
        size = _fmt_size(p.stat().st_size)
        self._file_hint.setText(f"{icon}  {p.name}  ·  {size}  ·  Tell {self._assistant_name} what to do with it")
        self._log.append_log(f"FILE: {p.name} ({size}) loaded")
        if self.on_text_command:
            msg = (
                f"[FILE_UPLOADED] path={path} | name={p.name} | "
                f"type={p.suffix.lstrip('.')} | size={size} | "
                f"Briefly tell the user you can see the file '{p.name}' "
                f"({size}) has been uploaded and ask what they'd like to do with it."
            )
            threading.Thread(target=self.on_text_command, args=(msg,), daemon=True).start()

    def notify_phone_connected(self) -> None:
        if self._remote_overlay and self._remote_overlay.isVisible():
            self._remote_overlay.mark_connected()

    def _open_remote(self):
        if not self.on_remote_clicked:
            self._log.append_log("SYS: Dashboard not running — remote unavailable.")
            return
        result = self.on_remote_clicked()
        if not result:
            self._log.append_log("SYS: Could not generate remote key.")
            return
        url    = result[0]
        key    = result[1]
        auto   = result[2] if len(result) >= 3 else ""
        manual = result[3] if len(result) >= 4 else url
        if self._remote_overlay:
            self._remote_overlay._do_close()
        cw  = self.centralWidget()
        ow, oh = RemoteKeyOverlay._OW, RemoteKeyOverlay._OH
        ov  = RemoteKeyOverlay(url, key, auto_login_url=auto, manual_url=manual,
                               expiry_secs=600, parent=cw)
        ov.set_new_key_callback(self.on_remote_clicked)
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.closed.connect(lambda: setattr(self, '_remote_overlay', None))
        ov.show()
        self._remote_overlay = ov
        self._log.append_log(f"SYS: Remote key generated — manual: {manual or url}")

    # ── Auto-start ──────────────────────────────────────────────────────────────

    def _check_autostart(self) -> bool:
        """Returns True if auto-start is currently registered on this OS."""
        try:
            if _OS == "Windows":
                import winreg
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
                try:
                    winreg.QueryValueEx(key, "TOKYO_AI")
                    return True
                except FileNotFoundError:
                    return False
                finally:
                    winreg.CloseKey(key)
            elif _OS == "Darwin":
                return (Path.home() / "Library" / "LaunchAgents"
                        / "com.tokyo.assistant.plist").exists()
            else:
                return (Path.home() / ".config" / "autostart" / "tokyo.desktop").exists()
        except Exception:
            return False

    def _toggle_autostart(self):
        currently_on = self._check_autostart()
        try:
            script = str(Path(__file__).resolve().parent / "main.py")
            if _OS == "Windows":
                import winreg
                reg = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_ALL_ACCESS)
                if currently_on:
                    winreg.DeleteValue(reg, "TOKYO_AI")
                else:
                    pythonw = Path(sys.executable).parent / "pythonw.exe"
                    exe = str(pythonw if pythonw.exists() else sys.executable)
                    winreg.SetValueEx(reg, "TOKYO_AI", 0, winreg.REG_SZ,
                                      f'"{exe}" "{script}"')
                winreg.CloseKey(reg)
            elif _OS == "Darwin":
                plist_dir = Path.home() / "Library" / "LaunchAgents"
                plist_dir.mkdir(parents=True, exist_ok=True)
                plist = plist_dir / "com.tokyo.assistant.plist"
                if currently_on:
                    plist.unlink(missing_ok=True)
                else:
                    plist.write_text(
                        '<?xml version="1.0" encoding="UTF-8"?>\n'
                        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                        '<plist version="1.0"><dict>\n'
                        '  <key>Label</key><string>com.tokyo.assistant</string>\n'
                        '  <key>ProgramArguments</key><array>\n'
                        f'    <string>{sys.executable}</string>\n'
                        f'    <string>{script}</string>\n'
                        '  </array>\n'
                        '  <key>RunAtLoad</key><true/>\n'
                        '</dict></plist>\n'
                    )
            else:
                desk_dir = Path.home() / ".config" / "autostart"
                desk_dir.mkdir(parents=True, exist_ok=True)
                desk = desk_dir / "tokyo.desktop"
                if currently_on:
                    desk.unlink(missing_ok=True)
                else:
                    desk.write_text(
                        "[Desktop Entry]\n"
                        f"Name={self._assistant_name}\n"
                        f"Exec={sys.executable} {script}\n"
                        "Type=Application\nTerminal=false\n"
                        "X-GNOME-Autostart-enabled=true\n"
                    )
            enabled = not currently_on
            self._update_autostart_btn(enabled)
            self._log.append_log(
                f"SYS: Auto-start {'enabled' if enabled else 'disabled'}.")
        except Exception as e:
            self._log.append_log(f"ERR: Auto-start failed — {e}")

    def _update_autostart_btn(self, enabled: bool):
        if not hasattr(self, '_autostart_btn'):
            return
        if enabled:
            self._autostart_btn.setText("◉  AUTO-START: ON")
            self._autostart_btn.setStyleSheet(f"""
                QPushButton {{
                    background: #001a08; color: {C.GREEN};
                    border: 1px solid {C.GREEN_D}; border-radius: 3px;
                }}
                QPushButton:hover {{ background: #002010; }}
            """)
        else:
            self._autostart_btn.setText("◉  AUTO-START: OFF")
            self._autostart_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {C.TEXT_DIM};
                    border: 1px solid {C.BORDER}; border-radius: 3px;
                }}
                QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}
            """)

    def _toggle_brief(self):
        from memory.config_manager import get_brief_enabled, save_brief_enabled
        new_val = not get_brief_enabled()
        save_brief_enabled(new_val)
        self._update_brief_btn(new_val)

    def _update_brief_btn(self, enabled: bool):
        if not hasattr(self, '_brief_btn'):
            return
        if enabled:
            self._brief_btn.setText("☀  MORNING BRIEF: ON")
            self._brief_btn.setStyleSheet(f"""
                QPushButton {{
                    background: #001a08; color: {C.GREEN};
                    border: 1px solid {C.GREEN_D}; border-radius: 3px;
                    text-align: left; padding: 0 8px;
                }}
                QPushButton:hover {{ background: #002010; }}
            """)
        else:
            self._brief_btn.setText("☀  MORNING BRIEF: OFF")
            self._brief_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {C.TEXT_DIM};
                    border: 1px solid {C.BORDER}; border-radius: 3px;
                    text-align: left; padding: 0 8px;
                }}
                QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}
            """)

    # ── Customization ────────────────────────────────────────────────────────────

    def _open_customize(self):
        cfg = _read_full_config()
        if self._customize_overlay:
            self._customize_overlay.hide()
        cw = self.centralWidget()
        ov = CustomizeOverlay(
            cfg.get("assistant_name", "TOKYO") or "TOKYO",
            cfg.get("user_name", ""),
            cfg.get("ui_color", "") or DEFAULT_UI_COLOR,
            parent=cw,
        )
        ow, oh = CustomizeOverlay._OW, CustomizeOverlay._OH
        oh = min(oh, cw.height() - 16)
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.on_preview = self._preview_ui_color
        ov.saved.connect(self._apply_name_update)
        ov.show()
        self._customize_overlay = ov

    def _preview_ui_color(self, hex_color: str):
        """Canlı önizleme — tüm arayüzü yeni renge boyar (config'e YAZMAZ)."""
        old = current_palette()
        if apply_ui_accent(hex_color):
            retheme_all_widgets(old, current_palette())

    def _apply_name_update(self, name: str, user_name: str, ui_color: str = ""):
        """Update all name/theme-dependent UI elements and persist to config."""
        self._assistant_name = name.strip() or "TOKYO"
        display = self._assistant_name.upper()
        self.setWindowTitle(f"{display} — MARK LI")
        self._title_lbl.setText(display)
        if display in ("TOKYO", "J.A.R.V.I.S"):
            self._sub_lbl.setText("Just A Rather Very Intelligent System")
        else:
            self._sub_lbl.setText("Personal AI Assistant")
        self._log._ai_name_lc = self._assistant_name.lower()
        self.hud._assistant_name = display

        color_changed = False
        if ui_color:
            old = current_palette()
            if apply_ui_accent(ui_color):
                # Tüm arayüzü (paneller, butonlar, kenarlıklar, HUD) canlı boya
                retheme_all_widgets(old, current_palette())
                color_changed = old["PRI"] != C.PRI

        try:
            data = _read_full_config()
            data["assistant_name"] = self._assistant_name
            data["user_name"] = user_name.strip()
            if ui_color:
                data["ui_color"] = ui_color.strip().lower()
            API_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")
            self._log.append_log(f"SYS: Identity updated — {display}")
            if color_changed:
                self._log.append_log(f"SYS: UI colour applied — {ui_color}")
        except Exception as e:
            self._log.append_log(f"ERR: Config save failed — {e}")

    def _open_plugin_manager(self):
        plugins = self.get_plugins() if self.get_plugins else []
        cw = self.centralWidget()
        ov = PluginManagerOverlay(plugins, parent=cw)
        ov.adjustSize()
        ov.setGeometry(
            (cw.width()  - ov.width())  // 2,
            (cw.height() - ov.height()) // 2,
            ov.width(), ov.height(),
        )
        ov.show()
        ov.raise_()
        self._plugin_manager_overlay = ov   # keep a reference so it isn't GC'd

    # ── Clipboard intelligence ───────────────────────────────────────────────────

    def _on_clipboard_changed(self):
        try:
            text = QApplication.clipboard().text().strip()
            if len(text) >= 10:
                self._clipboard_sig.emit(text)
        except Exception:
            pass

    def _show_clipboard_panel(self, text: str):
        self._clipboard_panel.show_clipboard(text)
        self._position_clipboard_panel()

    def _position_clipboard_panel(self):
        cw = self.centralWidget()
        pw = ClipboardPanel._W
        ph = self._clipboard_panel.sizeHint().height() or ClipboardPanel._H
        x = (cw.width() - pw) // 2
        y = cw.height() - ph - 6
        self._clipboard_panel.setGeometry(x, y, pw, ph)
        self._clipboard_panel.raise_()

    def _on_clipboard_action(self, cmd: str):
        if self.on_text_command:
            threading.Thread(target=self.on_text_command, args=(cmd,), daemon=True).start()

    # ────────────────────────────────────────────────────────────────────────────

    def _do_interrupt(self):
        if self.on_interrupt:
            self.on_interrupt()

    def _toggle_mute(self):
        self._muted = not self._muted
        self.hud.muted = self._muted
        self._style_mute_btn()
        if self._muted:
            self._apply_state("MUTED")
            self._log.append_log("SYS: Microphone muted.")
        else:
            self._apply_state("LISTENING")
            self._log.append_log("SYS: Microphone active.")

    def _style_mute_btn(self):
        if self._muted:
            self._mute_btn.setText("🔇")
            self._mute_btn.setStyleSheet(f"""
                QPushButton {{
                    background: rgba(255, 71, 87, 0.18); color: #ff6b81;
                    border: 1px solid rgba(255, 71, 87, 0.45); border-radius: 24px;
                }}
                QPushButton:hover {{
                    background: rgba(255, 71, 87, 0.32); color: #ffffff;
                }}
            """)
        else:
            self._mute_btn.setText("🎙")
            self._mute_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {C.PRI_GHO}; color: {C.PRI};
                    border: 1px solid {C.PRI}; border-radius: 24px;
                }}
                QPushButton:hover {{
                    background: {C.PRI}; color: #000000;
                }}
            """)

    def _send(self):
        txt = self._input.text().strip()
        if not txt: return
        self._input.clear()
        self._log.append_log(f"You: {txt}")
        if self.on_text_command:
            threading.Thread(target=self.on_text_command, args=(txt,), daemon=True).start()

    def _apply_state(self, state: str):
        self.hud.state    = state
        self.hud.speaking = (state == "SPEAKING")

    def _check_config(self) -> bool:
        if not API_FILE.exists(): return False
        try:
            d = json.loads(API_FILE.read_text(encoding="utf-8"))
            return bool(d.get("gemini_api_key")) and bool(d.get("os_system"))
        except Exception:
            return False

    def _show_setup(self):
        ov = SetupOverlay(self.centralWidget())
        cw = self.centralWidget()
        ow, oh = 380, 300
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.done.connect(self._on_setup_done)
        ov.show()
        self._overlay = ov

    def _on_setup_done(self, key: str, os_name: str):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        API_FILE.write_text(
            json.dumps({"gemini_api_key": key, "os_system": os_name}, indent=4),
            encoding="utf-8",
        )
        self._ready = True
        if self._overlay:
            self._overlay.hide()
            self._overlay = None
        self._apply_state("LISTENING")
        self._assistant_name = _read_full_config().get("assistant_name", "TOKYO") or "TOKYO"
        self._log.append_log(f"SYS: Initialised. OS={os_name.upper()}. {self._assistant_name} online.")

class _RootShim:
    def __init__(self, app: QApplication):
        self._app = app
    def mainloop(self):
        self._app.exec()
    def protocol(self, *_):
        pass


class TokyoUI:
    def __init__(self, face_path: str, size=None):
        self._app = QApplication.instance() or QApplication(sys.argv)
        self._app.setStyle("Fusion")
        self._win = MainWindow(face_path)
        self._win.show()
        self.root = _RootShim(self._app)

    @property
    def muted(self) -> bool:
        return self._win._muted

    @muted.setter
    def muted(self, v: bool):
        if v != self._win._muted:
            self._win._toggle_mute()

    @property
    def current_file(self) -> str | None:
        return self._win._drop_zone.current_file()

    @property
    def on_text_command(self):
        return self._win.on_text_command

    @on_text_command.setter
    def on_text_command(self, cb):
        self._win.on_text_command = cb

    @property
    def on_remote_clicked(self):
        return self._win.on_remote_clicked

    @on_remote_clicked.setter
    def on_remote_clicked(self, cb):
        self._win.on_remote_clicked = cb

    @property
    def on_interrupt(self):
        return self._win.on_interrupt

    @on_interrupt.setter
    def on_interrupt(self, cb):
        self._win.on_interrupt = cb

    @property
    def get_plugins(self):
        return self._win.get_plugins

    @get_plugins.setter
    def get_plugins(self, cb):
        self._win.get_plugins = cb

    def notify_phone_connected(self) -> None:
        self._win.notify_phone_connected()

    def set_state(self, state: str):
        self._win._state_sig.emit(state)

    def write_log(self, text: str):
        self._win._log_sig.emit(text)

    def wait_for_api_key(self):
        while not self._win._ready:
            time.sleep(0.1)

    def show_content(self, title: str, text: str):
        """Thread-safe: display content in the panel below the HUD."""
        self._win._content_sig.emit(title[:48], text[:4000])

    def prompt_reconfig(self):
        """Thread-safe: show the API key setup overlay (e.g. after an auth error)."""
        self._win._ready = False
        self._win._reconfig_sig.emit()

    def show_camera_frame(self, img_bytes: bytes):
        """Thread-safe: show a webcam frame in the small overlay (screen captures)."""
        self._win._camera_sig.emit(img_bytes)

    def start_camera_stream(self) -> None:
        """Thread-safe: start live camera feed in the full HUD area."""
        self._win.start_camera_stream()

    def stop_camera_stream(self) -> None:
        """Thread-safe: stop the live camera feed."""
        self._win.stop_camera_stream()

    @property
    def assistant_name(self) -> str:
        return self._win._assistant_name

    def start_speaking(self):
        self.set_state("SPEAKING")

    def stop_speaking(self):
        if not self.muted:
            self.set_state("LISTENING")