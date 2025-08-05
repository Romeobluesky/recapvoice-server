import os
import sys
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import subprocess

class ReloadHandler(FileSystemEventHandler):
    def __init__(self, script):
        self.script = script
        self.process = subprocess.Popen([sys.executable, self.script])

    def on_modified(self, event):
        if event.src_path.endswith(self.script):
            print(f"\n🔄 {self.script} 변경 감지됨. 재시작합니다...")
            self.process.kill()
            time.sleep(0.5)
            self.process = subprocess.Popen([sys.executable, self.script])

if __name__ == "__main__":
    script = "dashboard.py"  # 여기 원하는 파일명 입력
    path = "."
    event_handler = ReloadHandler(script)
    observer = Observer()
    observer.schedule(event_handler, path=path, recursive=False)
    observer.start()
    print(f"👀 {script} 감시 중... 파일 수정 시 자동 재실행됩니다.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        observer.join()