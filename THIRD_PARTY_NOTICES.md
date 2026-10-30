# Third-party components

This independently authored application uses Python/Tcl/Tk, NumPy, SciPy,
Matplotlib, Pillow and tzdata, plus their dependencies. Windows builds use
PyInstaller. Their respective copyright notices and licenses apply. Distribution
licenses collected from the exact build environment are included under
`_internal/licenses/` in the portable build, and inside the standalone executable.
Python/Tcl/Tk notices are also supplied by their PyInstaller runtime hooks.
Consult each package's bundled notices for BLAS, LAPACK, Qhull, fonts and other
embedded components. Dependency versions are pinned in `requirements-build.txt`.

FieldFox and Keysight are trademarks of their respective owners. This project is
not affiliated with or endorsed by Keysight. It includes no Data Link executable,
DLL, installer, decompiled source, instrument firmware, user recording or decoded
user data. The protocol and format documentation describe interoperability.

The decoder and browser originated in the author's separate repositories:
https://github.com/NicolasSayed/testing_data_conversion and
https://github.com/NicolasSayed/fieldfox_ethernet_browser.
