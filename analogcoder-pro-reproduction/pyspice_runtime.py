import os
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_NGSPICE_DLL_ROOT = ROOT / "vendor" / "ngspice-46-dll" / "Spice64_dll"
DEFAULT_NGSPICE_DLL = DEFAULT_NGSPICE_DLL_ROOT / "dll-vs" / "ngspice.dll"
DEFAULT_SPICE_LIB_DIR = ROOT / "repro_tools" / "ngspice"


def configure_pyspice() -> Path:
    """Configure PySpice to use the vendored Ngspice 46 shared library."""
    dll_path = Path(os.environ.get("NGSPICE_DLL_PATH", DEFAULT_NGSPICE_DLL)).resolve()
    if not dll_path.is_file():
        raise FileNotFoundError(
            "Ngspice shared library not found. Set NGSPICE_DLL_PATH to ngspice.dll: "
            f"{dll_path}"
        )

    spice_lib_dir = Path(
        os.environ.get("SPICE_LIB_DIR", DEFAULT_SPICE_LIB_DIR)
    ).resolve()
    os.environ["SPICE_LIB_DIR"] = str(spice_lib_dir)

    # Keep the handle alive for the process lifetime so dependent DLL lookup remains valid.
    if os.name == "nt" and hasattr(os, "add_dll_directory"):
        global _DLL_DIRECTORY_HANDLE
        _DLL_DIRECTORY_HANDLE = os.add_dll_directory(str(dll_path.parent))

    from PySpice.Spice.NgSpice.Shared import NgSpiceShared
    from PySpice.Spice.Simulation import CircuitSimulator

    NgSpiceShared.LIBRARY_PATH = str(dll_path)
    NgSpiceShared.NGSPICE_PATH = str(DEFAULT_NGSPICE_DLL_ROOT)
    CircuitSimulator.DEFAULT_SIMULATOR = "ngspice-shared"
    return dll_path
