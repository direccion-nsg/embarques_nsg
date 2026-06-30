"""
Punto de entrada para PyInstaller.
Cuando se ejecuta como .exe, arranca el servidor Streamlit internamente
y abre el navegador automáticamente.
"""

import os
import sys
import threading
import time
import webbrowser


def resource_path(relative: str) -> str:
    """Localiza un recurso tanto en modo desarrollo como empaquetado con PyInstaller."""
    try:
        base = sys._MEIPASS  # type: ignore[attr-defined]
    except AttributeError:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, relative)


def iniciar_streamlit():
    """Lanza Streamlit usando su CLI interno (compatible con PyInstaller)."""
    app_path = resource_path("app.py")
    # Ajustar sys.argv para que Streamlit interprete correctamente los argumentos
    sys.argv = [
        "streamlit", "run", app_path,
        "--server.port=8501",
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
        "--server.enableCORS=false",
        "--server.enableXsrfProtection=false",
    ]
    from streamlit.web import cli as stcli
    stcli.main()


def abrir_navegador():
    """Espera a que Streamlit esté listo y abre el browser."""
    time.sleep(3)
    webbrowser.open("http://localhost:8501")


if __name__ == "__main__":
    # Abrir browser en hilo separado para no bloquear el inicio de Streamlit
    t_browser = threading.Thread(target=abrir_navegador, daemon=True)
    t_browser.start()
    # Streamlit bloquea el hilo principal (es intencional)
    iniciar_streamlit()
