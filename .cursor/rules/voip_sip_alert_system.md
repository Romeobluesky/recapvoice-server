# VoIP SIP 신호 감지 및 클라이언트 알림 시스템 설계 문서

## 🧩 시스템 개요

본 시스템은 Python 기반의 데스크탑 프로그램으로 구성되며, VoIP 환경에서 SIP 신호를 포트미러링을 통해 감지하고, 해당 신호를 MongoDB 정보와 매칭한 뒤, 알맞은 클라이언트 PC로 알림을 전송하는 구조입니다.

---

## 🖧 네트워크 구성

```
┌───────────────┐         포트미러링          ┌─────────────────┐
│  인터넷전화망 │──────────────────────────▶ │    서버 PC       │
└───────────────┘                           │ - SIP 감지       │
                                            │ - MongoDB 조회   │
                                            │ - WebSocket 송신 │
                                            └──────┬──────────┘
                                                   │
                                         ┌─────────▼────────────┐
                                         │ 클라이언트 PC (여러대) │
                                         │ - WebSocket 수신     │
                                         │ - 알림 GUI 표시       │
                                         └──────────────────────┘
```

---

## 🛠 구성 요소 및 역할

### 서버 프로그램

- **패킷 감지**: Wireshark 기반 포트미러링으로 SIP 패킷 감시 (`pyshark`, `scapy`)
- **MongoDB 조회**: `members` 컬렉션에서 `to` 내선번호에 해당하는 내부 IP 조회
- **WebSocket 송신**: 해당 내부 IP로 알림 메시지 전송

### 클라이언트 프로그램

- **WebSocket 수신**: 서버로부터 알림 메시지를 수신
- **알림 표시**: 수신 시 GUI 창 또는 시스템 트레이 알림 표시 (`PySide6`)

---

## 💾 MongoDB 컬렉션 예시 (`members`)

```json
{
  "extension_num": "1001",
  "default_ip": "192.168.0.101"
}
```

---

## 🧪 서버 WebSocket 코드 예시

```python
import asyncio
import websockets
import pymongo
import json

connected_clients = {}  # ip -> websocket

async def handler(websocket):
    client_ip = websocket.remote_address[0]
    connected_clients[client_ip] = websocket
    try:
        async for message in websocket:
            pass
    finally:
        del connected_clients[client_ip]

async def notify_client(to_number, from_number):
    mongo = pymongo.MongoClient("mongodb://localhost:27017")
    db = mongo['packetwave']
    member = db.members.find_one({'extension_num': to_number})
    if not member:
        return
    ip = member['default_ip']
    if ip in connected_clients:
        await connected_clients[ip].send(json.dumps({
            'type': 'incoming_call',
            'from': from_number,
            'to': to_number
        }))

async def main():
    async with websockets.serve(handler, "0.0.0.0", 8765):
        await asyncio.Future()

asyncio.run(main())
```

---

## 🧪 클라이언트 PySide6 예시 코드

```python
import sys
import asyncio
import threading
import websockets
import json
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

class AlertWindow(QWidget):
    def __init__(self):
        super().__init__()

    def show_alert(self, caller):
        QMessageBox.information(self, "전화 수신", f"{caller} 에게서 전화가 왔습니다!")

def start_websocket(alert_window):
    async def listen():
        uri = "ws://서버IP:8765"
        async with websockets.connect(uri) as websocket:
            while True:
                msg = await websocket.recv()
                data = json.loads(msg)
                if data['type'] == 'incoming_call':
                    alert_window.show_alert(data['from'])

    asyncio.run(listen())

app = QApplication(sys.argv)
window = AlertWindow()
threading.Thread(target=start_websocket, args=(window,), daemon=True).start()
sys.exit(app.exec())
```

---

## 🧩 추천 기술 스택

| 항목 | 라이브러리 |
|------|------------|
| SIP 패킷 분석 | `pyshark`, `scapy` |
| MongoDB 연동 | `pymongo` |
| WebSocket 서버 | `websockets`, `aiohttp` |
| WebSocket 클라이언트 | `websocket-client`, `websockets` |
| GUI 알림 | `PySide6`, `QMessageBox`, `QSystemTrayIcon` |

---

## ✅ 작업 순서 요약

1. SIP 패킷 감지 코드 구현
2. MongoDB에 내선-아이피 매핑 등록
3. WebSocket 서버 구현 및 클라이언트 연결 확인
4. 알림 수신 테스트
5. GUI 최적화 및 트레이 연동 (선택)

---