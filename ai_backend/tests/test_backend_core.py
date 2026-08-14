from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import mock

from ttl_ai_backend.config import BackendSettings, SettingsStore
from ttl_ai_backend.hardware import HardwareProfile
from ttl_ai_backend.models import CATALOG
from ttl_ai_backend.runtime import PINNED_LLAMA_CPP_RELEASE, _asset_patterns, describe_process_exit
from ttl_ai_backend.server import build_server_command, derive_alias, local_addresses, port_is_available


def test_settings_roundtrip() -> None:
    with tempfile.TemporaryDirectory() as td:
        store = SettingsStore(Path(td) / "settings.json")
        settings = BackendSettings(port=8123)
        settings.ensure_api_key()
        store.save(settings)
        loaded = store.load()
        assert loaded.port == 8123
        assert loaded.api_key == settings.api_key


def test_command_matches_reference_launcher() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        server = root / "llama-server"
        model = root / "Qwen3.5-9B-UD-Q5_K_XL.gguf"
        server.write_text("")
        model.write_text("")
        settings = BackendSettings(server_path=str(server), model_path=str(model), api_key="test-key", backend="cpu")
        cmd = build_server_command(settings)
        args = list(cmd.arguments)
        assert args[args.index("--host") + 1] == "0.0.0.0"
        assert args[args.index("--port") + 1] == "8081"
        assert args[args.index("--ctx-size") + 1] == "16384"
        assert args[args.index("--parallel") + 1] == "1"
        assert args[args.index("--cache-ram") + 1] == "0"
        assert args[args.index("--device") + 1] == "none"
        assert args[args.index("--n-gpu-layers") + 1] == "0"
        assert args[args.index("--flash-attn") + 1] == "auto"
        assert args[args.index("--reasoning") + 1] == "off"
        key_file = Path(args[args.index("--api-key-file") + 1])
        assert key_file.read_text().strip() == "test-key"
        assert "--no-webui" in args


def test_alias() -> None:
    assert derive_alias("/models/Qwen3.5-9B-UD-Q5_K_XL.gguf") == "qwen3.5-9b-ud-q5_k_xl"


def test_catalog_has_reference_model() -> None:
    assert CATALOG[0].filename == "Qwen3.5-9B-UD-Q5_K_XL.gguf"
    assert CATALOG[0].recommended
    assert CATALOG[0].alias == "qwen3.5-9b-q5"


def test_runtime_asset_patterns() -> None:
    cuda = _asset_patterns("Windows", "AMD64", "cuda")
    assert cuda[0].search("llama-b10430-bin-win-cuda-12.4-x64.zip")
    assert cuda[1].search("cudart-llama-bin-win-cuda-12.4-x64.zip")
    assert _asset_patterns("Windows", "AMD64", "openvino")[0].search("llama-b10430-bin-win-openvino-2026.2.1-x64.zip")
    assert _asset_patterns("Linux", "x86_64", "vulkan")[0].search("llama-b10430-bin-ubuntu-vulkan-x64.tar.gz")
    assert _asset_patterns("Linux", "x86_64", "openvino")[0].search("llama-b10430-bin-ubuntu-openvino-2026.2.1-x64.tar.gz")
    assert PINNED_LLAMA_CPP_RELEASE == "b10430"


def test_local_addresses_are_openai_base_urls() -> None:
    urls = local_addresses(8080)
    assert urls
    assert all(url.endswith(":8080/v1") for url in urls)


def test_backend_default_port_avoids_ttl_server():
    assert BackendSettings().port == 8081


def test_old_8080_setting_migrates():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "settings.json"
        path.write_text('{"port": 8080, "api_key": "test"}', encoding="utf-8")
        settings = SettingsStore(path).load()
        assert settings.port == 8081
        assert settings.settings_version == 5


def test_explicit_old_custom_port_is_preserved():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "settings.json"
        path.write_text('{"port": 9090, "api_key": "test"}', encoding="utf-8")
        settings = SettingsStore(path).load()
        assert settings.port == 9090



def test_memory_safe_defaults():
    settings = BackendSettings()
    assert settings.parallel_slots == 1
    assert settings.prompt_cache_ram_mb == 0


def test_port_availability_probe():
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.listen(1)
        assert not port_is_available("127.0.0.1", port)
    assert port_is_available("127.0.0.1", port)



def test_accelerated_backend_keeps_requested_gpu_layers() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        server = root / "llama-server"
        model = root / "model.gguf"
        server.write_text("")
        model.write_text("")
        settings = BackendSettings(
            server_path=str(server),
            model_path=str(model),
            api_key="test-key",
            backend="vulkan",
            gpu_layers="auto",
        )
        args = list(build_server_command(settings).arguments)
        assert "--device" not in args
        assert args[args.index("--n-gpu-layers") + 1] == "auto"


def test_intel_gpu_recommends_safe_cpu_path() -> None:
    from ttl_ai_backend import hardware
    with mock.patch.object(hardware.platform, "system", return_value="Linux"), \
         mock.patch.object(hardware.platform, "processor", return_value="Intel CPU"), \
         mock.patch.object(hardware.platform, "machine", return_value="x86_64"), \
         mock.patch.object(hardware, "_nvidia_smi_names", return_value=[]), \
         mock.patch.object(hardware, "_linux_gpu_names", return_value=["Intel Corporation UHD Graphics 630"]):
        profile = hardware.detect_hardware()
        assert profile.has_intel_gpu
        assert profile.recommendation == "cpu"
        assert "Intel integrated graphics" in profile.recommendation_label

def test_windows_access_violation_is_descriptive() -> None:
    message = describe_process_exit(3221225477, "vulkan")
    assert "0xC0000005" in message
    assert "Vulkan" in message
    assert "graphics-driver" in message
    assert "choose CPU" in message


def test_windows_loader_failure_is_descriptive() -> None:
    message = describe_process_exit(3221225781, "cuda")
    assert "0xC0000135" in message
    assert "required DLL" in message


def main() -> int:
    tests = [obj for name, obj in globals().items() if name.startswith("test_") and callable(obj)]
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")
    print(f"{len(tests)} backend core tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())



def test_windows_nvidia_recommends_cuda() -> None:
    from ttl_ai_backend import hardware
    with mock.patch.object(hardware.platform, "system", return_value="Windows"), \
         mock.patch.object(hardware.platform, "processor", return_value="AMD64"), \
         mock.patch.object(hardware.platform, "machine", return_value="AMD64"), \
         mock.patch.object(hardware, "_nvidia_smi_names", return_value=["NVIDIA GeForce RTX 3060"]), \
         mock.patch.object(hardware, "_windows_gpu_names", return_value=["NVIDIA GeForce RTX 3060"]):
        profile = hardware.detect_hardware()
        assert profile.has_nvidia
        assert profile.recommendation == "cuda"


def test_windows_amd_recommends_vulkan() -> None:
    from ttl_ai_backend import hardware
    with mock.patch.object(hardware.platform, "system", return_value="Windows"), \
         mock.patch.object(hardware.platform, "processor", return_value="AMD64"), \
         mock.patch.object(hardware.platform, "machine", return_value="AMD64"), \
         mock.patch.object(hardware, "_nvidia_smi_names", return_value=[]), \
         mock.patch.object(hardware, "_windows_gpu_names", return_value=["AMD Radeon RX 7800 XT"]):
        profile = hardware.detect_hardware()
        assert profile.has_amd
        assert profile.recommendation == "vulkan"


def test_windows_intel_arc_recommends_vulkan() -> None:
    from ttl_ai_backend import hardware
    with mock.patch.object(hardware.platform, "system", return_value="Windows"), \
         mock.patch.object(hardware.platform, "processor", return_value="AMD64"), \
         mock.patch.object(hardware.platform, "machine", return_value="AMD64"), \
         mock.patch.object(hardware, "_nvidia_smi_names", return_value=[]), \
         mock.patch.object(hardware, "_windows_gpu_names", return_value=["Intel(R) Arc(TM) A770 Graphics"]):
        profile = hardware.detect_hardware()
        assert profile.has_intel_arc
        assert profile.recommendation == "vulkan"


def test_windows_intel_integrated_uses_cpu_fallback() -> None:
    from ttl_ai_backend import hardware
    with mock.patch.object(hardware.platform, "system", return_value="Windows"), \
         mock.patch.object(hardware.platform, "processor", return_value="AMD64"), \
         mock.patch.object(hardware.platform, "machine", return_value="AMD64"), \
         mock.patch.object(hardware, "_nvidia_smi_names", return_value=[]), \
         mock.patch.object(hardware, "_windows_gpu_names", return_value=["Intel(R) UHD Graphics 770"]):
        profile = hardware.detect_hardware()
        assert profile.has_intel_gpu
        assert not profile.has_intel_arc
        assert profile.recommendation == "cpu"


def test_runtime_backend_matching() -> None:
    from ttl_ai_backend.runtime import runtime_backend_matches
    assert runtime_backend_matches("Windows", "cuda", "cuda")
    assert runtime_backend_matches("Windows", "vulkan", "vulkan")
    assert not runtime_backend_matches("Windows", "cuda", "cpu")
    assert runtime_backend_matches("Linux", "cuda", "vulkan")
