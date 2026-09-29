APOLLO EXE BUILDER
==================

This pack contains:
- apollo_logo.ico        -> Windows icon made from your supplied Apollo logo
- apollo_logo.png        -> Copy of your source logo
- build_apollo_exe.bat   -> Quick Windows build script
- apollo.spec            -> Optional PyInstaller spec file
- make_icon.py           -> Rebuild the icon if needed

HOW TO USE
----------
1. Copy these files into the ROOT of your Apollo project
   (the same folder that contains main.py).

2. On Windows, double-click:
   build_apollo_exe.bat

3. It will install PyInstaller and build:
   dist\Apollo.exe

DIRECT COMMAND (if you prefer terminal)
---------------------------------------
py -m pip install pyinstaller pillow
py -m PyInstaller --noconfirm --clean --windowed --onefile --name Apollo --icon apollo_logo.ico main.py

NOTES
-----
- If your entry file is not called main.py, edit APP_MAIN inside build_apollo_exe.bat.
- If Apollo uses extra assets/files, they may need adding to the PyInstaller command or spec file.
- This pack creates the icon and build files, but does not compile a Windows EXE inside this environment.
