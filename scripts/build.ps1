# Builds a standalone Sophia folder at dist\Sophia (about 500 MB).
# Run from the project root with the virtual environment active:
#   pip install pyinstaller
#   .\scripts\build.ps1                 includes the Piper voice (GPL-3.0)
#   .\scripts\build.ps1 -WithoutPiper   MIT/LGPL parts only; the system voice speaks
#
# Licensing: a folder built with Piper contains GPL-3.0 code (piper-tts,
# and MouseInfo / PyMsgBox from PyAutoGUI), so if you distribute it, do so
# under the GPL-3.0 terms. See THIRD_PARTY_LICENSES.md.

param([switch]$WithoutPiper)

$exclude = @("--exclude-module", "tkinter", "--exclude-module", "matplotlib", "--exclude-module", "mouseinfo", "--exclude-module", "pymsgbox")

if ($WithoutPiper) {
    $exclude += @("--exclude-module", "piper")
}

pyinstaller --noconfirm --clean --windowed --name Sophia `
    --icon assets\sophia.ico `
    --collect-all faster_whisper `
    --collect-all ctranslate2 `
    --collect-all openwakeword `
    --collect-all trafilatura `
    --collect-all ddgs `
    --collect-all edge_tts `
    --collect-all uiautomation `
    --collect-submodules keyring.backends `
    --hidden-import win32timezone `
    @exclude `
    main.py

Write-Host "Done: dist\Sophia\Sophia.exe"
