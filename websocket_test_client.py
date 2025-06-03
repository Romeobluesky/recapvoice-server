#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
WebSocket 테스트 클라이언트

이 스크립트는 SIP 알림 시스템 클라이언트를 테스트하기 위한 도구입니다.
서버에 연결하여 내선번호를 등록하고, 수신 전화에 대한 알림을 받습니다.

사용법:
    python websocket_test_client.py [호스트] [포트]

    기본값:
    - 호스트: localhost
    - 포트: 8765
"""
import asyncio
import websockets
import json
import sys
import time
import datetime

async def connect_websocket(uri="ws://localhost:8765", extension="1234"):
    """WebSocket 서버에 연결하고 메시지를 주고받는 테스트 클라이언트"""
    print(f"WebSocket 서버({uri})에 연결 시도...")
    
    try:
        async with websockets.connect(uri) as websocket:
            print(f"연결 성공: {uri}")
            
            # 내선번호 등록 메시지 전송
            register_msg = {
                "type": "register",
                "extension_num": extension
            }
            
            print(f"내선번호 등록 요청 전송: {register_msg}")
            await websocket.send(json.dumps(register_msg))
            
            # 응답 수신 대기
            response = await websocket.recv()
            print(f"서버 응답: {response}")
            
            # 계속해서 메시지 수신 대기
            print("\n메시지 수신 대기 중... (종료하려면 Ctrl+C를 누르세요)")
            while True:
                try:
                    message = await websocket.recv()
                    data = json.loads(message)
                    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    if data.get("type") == "incoming_call":
                        from_number = data.get("from", "알 수 없음")
                        to_number = data.get("to", "알 수 없음")
                        print(f"\n[{timestamp}] 📞 전화 수신 알림!")
                        print(f"발신: {from_number} → 수신: {to_number}")
                        
                        # 여기서 수신 확인 메시지를 서버로 보낼 수 있음
                        confirm_msg = {
                            "type": "confirm_notification",
                            "call_id": data.get("call_id", ""),
                            "received_at": timestamp
                        }
                        await websocket.send(json.dumps(confirm_msg))
                    else:
                        print(f"\n[{timestamp}] 메시지 수신: {data}")
                        
                except websockets.exceptions.ConnectionClosed:
                    print("\n서버와의 연결이 종료되었습니다.")
                    break
                except Exception as e:
                    print(f"\n메시지 처리 중 오류 발생: {e}")
                    continue
    
    except websockets.exceptions.InvalidStatusCode as status_error:
        print(f"연결 오류: 상태 코드 {status_error.status_code}")
        if status_error.status_code == 404:
            print("웹소켓 엔드포인트를 찾을 수 없습니다. URI가 올바른지 확인하세요.")
    except ConnectionRefusedError:
        print(f"연결 거부됨: {uri}")
        print("서버가 실행 중인지 또는 방화벽 설정을 확인하세요.")
    except Exception as e:
        print(f"연결 중 오류 발생: {e}")

def main():
    """메인 함수"""
    # 커맨드 라인 인자 처리
    uri = "ws://localhost:8765"  # 기본 URI
    extension = "1234"           # 기본 내선번호
    
    if len(sys.argv) > 1:
        extension = sys.argv[1]
    
    if len(sys.argv) > 2:
        port = sys.argv[2]
        uri = f"ws://localhost:{port}"
    
    print(f"WebSocket 테스트 클라이언트 시작 (내선번호: {extension}, URI: {uri})")
    
    try:
        # 이벤트 루프 실행
        asyncio.run(connect_websocket(uri, extension))
    except KeyboardInterrupt:
        print("\n사용자에 의해 프로그램이 종료되었습니다.")
    except Exception as e:
        print(f"프로그램 실행 중 오류 발생: {e}")

if __name__ == "__main__":
    main() 