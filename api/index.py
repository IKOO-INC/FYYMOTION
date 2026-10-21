"""
Entrypoint cadangan untuk Vercel (file-based Python Function di /api).
Entrypoint utama modern Vercel (framework preset Flask) adalah app.py di root.
File ini hanya meneruskan (re-export) WSGI app agar kompatibel dengan
konfigurasi lama: builds/routes -> api/index.py.
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app import app  # noqa: E402,F401  (Vercel membaca top-level `app`)
