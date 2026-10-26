"""Start Closet Twin: python run.py, then open http://127.0.0.1:8000 (PORT=8001 python run.py for another port)"""

import os
import sys
import webbrowser
from threading import Timer

import uvicorn

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    url = f"http://127.0.0.1:{port}"
    if "--no-browser" not in sys.argv:
        Timer(1.5, lambda: webbrowser.open(url)).start()
    print(f"\n  Closet Twin is running at {url}  (Ctrl+C to stop)\n")
    uvicorn.run("app.main:app", host="127.0.0.1", port=port)
