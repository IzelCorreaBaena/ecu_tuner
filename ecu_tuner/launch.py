#!/usr/bin/env python3
import sys
import subprocess
import platform
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent
    venv_dir = root / "venv"

    # Rutas del interprete dentro del venv
    if platform.system() == "Windows":
        py_exe = venv_dir / "Scripts" / "python.exe"
        pip_exe = venv_dir / "Scripts" / "pip.exe"
    else:
        py_exe = venv_dir / "bin" / "python"
        pip_exe = venv_dir / "bin" / "pip"

    # Crear entorno si no existe
    if not venv_dir.exists():
        print("[INFO] Creando entorno virtual...")
        ret = subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], cwd=str(root))
        if ret.returncode != 0:
            print("Error al crear el entorno virtual.")
            sys.exit(1)
        if platform.system() == "Windows":
            py_exe = venv_dir / "Scripts" / "python.exe"
            pip_exe = venv_dir / "Scripts" / "pip.exe"
        else:
            py_exe = venv_dir / "bin" / "python"
            pip_exe = venv_dir / "bin" / "pip"

    # Instalar dependencias
    req = root / "requirements.txt"
    if req.exists():
        print("[INFO] Instalando dependencias...")
        ret = subprocess.run([str(pip_exe), "install", "-r", str(req)], cwd=str(root))
        if ret.returncode != 0:
            print("Error al instalar dependencias.")
            sys.exit(1)

    # Ejecutar la aplicación
    print("[INFO] Iniciando ECU Tuner...")
    ret = subprocess.run([str(py_exe), str(root / "main.py")], cwd=str(root))
    if ret.returncode != 0:
        print("La ejecución terminó con código:", ret.returncode)
        sys.exit(ret.returncode)


if __name__ == "__main__":
    main()
