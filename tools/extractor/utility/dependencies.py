import platform
import sys
import shutil

isWindows = platform.system() == "Windows"


def _find_pdbutil() -> str | None:
    found = shutil.which("llvm-pdbutil")
    if found:
        return found
    # VS-bundled llvm-pdbutil
    patterns = [
        r"C:\Program Files (x86)\Microsoft Visual Studio\*\*\VC\Tools\Llvm\x64\bin\llvm-pdbutil.EXE",
        r"C:\Program Files\Microsoft Visual Studio\*\*\VC\Tools\Llvm\x64\bin\llvm-pdbutil.EXE",
    ]
    for pattern in patterns:
        matches = glob.glob(pattern)
        if matches:
            return matches[-1]  # take the latest
    sys.exit("Please install PDBUtil (Bundled with MSVC or LLVM)")


if isWindows: pdbutil = _find_pdbutil()
demangler = shutil.which("c++filt") or shutil.which("llvm-cxxfilt") or sys.exit("Please install LLVM (Windows) or C++filt (Linux / MacOS)!")
if not isWindows:
    dwarf_dump = shutil.which("llvm-dwarfdump") or shutil.which("dwarfdump") or sys.exit("Please install dwarfdump / LLVM")