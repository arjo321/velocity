""" Velocity desktop launcher. """
import sys
import os

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

import threading
import time
import webview
import server

class Api:
    def pick_folder(self):
        result = webview.windows[0].create_file_dialog(webview.FOLDER_DIALOG)
        return result[0] if result else None

def start_server():
    server.app.run(host="127.0.0.1", port=5000, debug=False, threaded=True, use_reloader=False)

if __name__ == "__main__":
    threading.Thread(target=start_server, daemon=True).start()
    time.sleep(0.6)
    
    webview.create_window(
        "Velocity",
        "http://127.0.0.1:5000/",
        width=980,
        height=820,
        min_size=(760, 640),
        frameless=False,
        background_color="#08080f",
        js_api=Api(),
    )
    webview.start()
