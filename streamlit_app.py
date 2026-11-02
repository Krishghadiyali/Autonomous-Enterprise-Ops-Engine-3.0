# *Verification:* Confirm `sitecustomize.py` is in the root directory alongside `seed.py`.

# 3. **Create `streamlit_app.py` in Your Project Root Folder**
#    Create a new file named `streamlit_app.py` in your root folder. This file loads your cloud secrets, runs `seed.py`, starts the FastAPI server on `127.0.0.1:8000` in the background once per container boot, and launches `ui/dashboard.py`:
#    ```python
import os
import runpy
import socket
import subprocess
import sys
import time
import streamlit as st


def is_backend_running() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", 8000)) == 0


if not is_backend_running():
       # Copy Streamlit Cloud Secrets into environment variables for seed.py and FastAPI
    for key, value in st.secrets.items():
        if isinstance(value, (str, int, float)):
            os.environ[str(key)] = str(value)

    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.dirname(os.path.abspath(__file__))

       # 1. Seed Aiven MySQL database and local ChromaDB embeddings
    subprocess.run([sys.executable, "seed.py"], env=env, check=True)

       # 2. Start FastAPI SSE backend in the background on port 8000
    subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ],
        env=env,
    )

       # Wait up to 20 seconds for FastAPI to accept connections
    for _ in range(40):
        if is_backend_running():
            break
        time.sleep(0.5)

   # 3. Launch your existing Streamlit operator console
runpy.run_path("ui/dashboard.py", run_name="__main__")