"""Configuración común de pytest.

Añade la carpeta backend/ al path para que `pytest` funcione igual que
`python -m pytest`, sin importar desde dónde se ejecute.
"""
import os
import sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
