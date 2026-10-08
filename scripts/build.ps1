# Builds a standalone Sophia folder at dist\Sophia (about 400 MB).
# Run from the project root with the virtual environment active:
#   pip install pyinstaller
#   .\scripts\build.ps1

pyinstaller --noconfirm --clean --windowed --name Sophia `
    --collect-all faster_whisper `
    --collect-all ctranslate2 `
    --collect-submodules keyring.backends `
    --hidden-import win32timezone `
    --exclude-module tkinter `
    --exclude-module matplotlib `
    main.py

Write-Host "Done: dist\Sophia\Sophia.exe"
