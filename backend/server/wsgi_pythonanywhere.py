"""Archivo WSGI para PythonAnywhere (plan gratis).

En PythonAnywhere → pestaña "Web" → sección "Code" → abre el archivo WSGI y reemplaza
su contenido por este, ajustando TU_USUARIO y las dos claves.
"""
import os
import sys

BASE = "/home/TU_USUARIO/cgame/backend"       # carpeta backend/ subida a PythonAnywhere
sys.path.insert(0, BASE + "/server")
sys.path.insert(0, BASE)

os.environ["CGAME_SECRET_KEY"] = "PON_AQUI_UNA_CLAVE_LARGA_ALEATORIA_1"
os.environ["CGAME_ADMIN_KEY"] = "PON_AQUI_TU_CLAVE_DE_ADMIN"
os.environ["CGAME_CORS_ORIGIN"] = "*"
os.environ["CGAME_DB_PATH"] = "/home/TU_USUARIO/cgame_data.db"   # el disco de PythonAnywhere SÍ persiste

from app import app as application  # noqa: E402
