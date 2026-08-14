from __future__ import annotations

import json
import platform
import re
import shutil
import subprocess
from dataclasses import dataclass, field


@dataclass(slots=True)
class HardwareProfile:
    system: str
    machine: str
    cpu: str
    gpus: list[str] = field(default_factory=list)
    has_nvidia: bool = False
    has_amd: bool = False
    has_intel_gpu: bool = False
    has_intel_arc: bool = False
    recommendation: str = "cpu"
    recommendation_label: str = "CPU"


def _run(args: list[str], timeout: float = 4.0) -> str:
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return ""
    return (proc.stdout or "").strip()


def _windows_gpu_names() -> list[str]:
    if shutil.which("powershell") is None and shutil.which("pwsh") is None:
        return []
    shell = shutil.which("powershell") or shutil.which("pwsh") or "powershell"
    script = "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name | ConvertTo-Json -Compress"
    out = _run([shell, "-NoProfile", "-Command", script])
    if not out:
        return []
    try:
        value = json.loads(out)
    except json.JSONDecodeError:
        return [line.strip() for line in out.splitlines() if line.strip()]
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(x) for x in value]
    return []


def _linux_gpu_names() -> list[str]:
    names: list[str] = []
    if shutil.which("lspci"):
        out = _run(["lspci"])
        for line in out.splitlines():
            lower = line.lower()
            if "vga compatible controller" in lower or "3d controller" in lower or "display controller" in lower:
                names.append(line.split(": ", 1)[-1].strip())
    return names


def _nvidia_smi_names() -> list[str]:
    if not shutil.which("nvidia-smi"):
        return []
    out = _run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"])
    return [line.strip() for line in out.splitlines() if line.strip()]


def detect_hardware() -> HardwareProfile:
    system = platform.system()
    cpu = platform.processor() or platform.machine()
    gpus = _nvidia_smi_names()
    if system == "Windows":
        gpus.extend(x for x in _windows_gpu_names() if x not in gpus)
    elif system == "Linux":
        gpus.extend(x for x in _linux_gpu_names() if x not in gpus)

    blob = " ".join(gpus).lower()
    has_nvidia = bool(re.search(r"\bnvidia\b|geforce|quadro|tesla|rtx|gtx", blob))
    has_amd = bool(re.search(r"\bamd\b|radeon|advanced micro devices", blob))
    has_intel = bool(re.search(r"\bintel\b.*(graphics|arc|iris|uhd|hd)|arc\(tm\)", blob))
    has_intel_arc = bool(re.search(r"\bintel\b.*\barc\b|\barc(?:\(tm\))?\s+[a-z]?\d", blob))

    if has_nvidia:
        recommendation, label = "cuda", "NVIDIA CUDA"
    elif has_amd:
        recommendation, label = "vulkan", "AMD Vulkan"
    elif has_intel_arc:
        recommendation, label = "vulkan", "Intel Arc Vulkan"
    elif has_intel:
        recommendation, label = "cpu", "CPU (Intel integrated graphics detected)"
    else:
        recommendation, label = "cpu", "CPU"

    return HardwareProfile(
        system=system,
        machine=platform.machine(),
        cpu=cpu,
        gpus=gpus,
        has_nvidia=has_nvidia,
        has_amd=has_amd,
        has_intel_gpu=has_intel,
        has_intel_arc=has_intel_arc,
        recommendation=recommendation,
        recommendation_label=label,
    )
