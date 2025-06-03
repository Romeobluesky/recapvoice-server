#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
독립형 WebSocket 서버

이 스크립트는 SIP 알림 시스템의 WebSocket 서버를 독립적으로 실행합니다.
대시보드 애플리케이션과 별도로 실행할 수 있어 테스트 및 디버깅에 유용합니다.

사용법:
    python run_websocket_server.py [포트] [--force]

    옵션:
    - 포트: WebSocket 서버가 사용할 포트 (기본값: 8765)
    - --force: 이미 사용 중인 포트를 강제로 해제하고 서버 시작
"""
import asyncio
import sys
import socket
import os
import signal
import argparse
import datetime
import json
import traceback
import websockets
from pymongo import MongoClient

class StandaloneWebSocketServer:
    """독립형 WebSocket 서버 클래스"""
    
    def __init__(self, port=8765, max_port_retry=5, mongo_uri="mongodb://localhost:27017/"):
        self.port = port
        self.max_port_retry = max_port_retry
        self.mongo_uri = mongo_uri
        self.connected_clients = {}  # ip -> websocket
        self.server = None
        self.running = False
        self._setup_logging()
        print(f"WebSocket 서버 초기화: 포트 {port}")
    
    def _setup_logging(self):
        """로깅 설정"""
        self.log_dir = "logs"
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)
        
        # 오늘 날짜로 로그 파일 이름 생성
        today = datetime.datetime.now().strftime("%Y%m%d")
        self.log_file = os.path.join(self.log_dir, f'websocket_server_{today}.log')
    
    def log(self, message, error=None):
        """로그 메시지 기록"""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"[{timestamp}] {message}"
        print(log_message)
        
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(f"{log_message}\n")
                if error:
                    f.write(f"[{timestamp}] 오류: {str(error)}\n")
                    f.write(f"스택 트레이스:\n{traceback.format_exc()}\n")
        except Exception as e:
            print(f"로그 파일 기록 중 오류: {e}")
    
    async def handler(self, websocket):
        """WebSocket 연결 처리"""
        client_ip = websocket.remote_address[0]
        self.connected_clients[client_ip] = websocket
        self.log(f"클라이언트 연결됨: {client_ip}")
        print(f"[상태] 현재 연결된 클라이언트: {len(self.connected_clients)}개")
        
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    self.log(f"클라이언트({client_ip})로부터 메시지 수신: {data}")
                    
                    # 클라이언트가 내선번호 등록 요청을 보낸 경우
                    if data.get('type') == 'register':
                        await self.handle_register(websocket, data, client_ip)
                except json.JSONDecodeError:
                    self.log(f"잘못된 JSON 형식: {message}")
                except Exception as e:
                    self.log("메시지 처리 중 오류 발생", e)
        except websockets.exceptions.ConnectionClosed:
            self.log(f"클라이언트 연결 종료: {client_ip}")
        finally:
            if client_ip in self.connected_clients:
                del self.connected_clients[client_ip]
                print(f"[상태] 현재 연결된 클라이언트: {len(self.connected_clients)}개")
    
    async def handle_register(self, websocket, data, client_ip):
        """내선번호 등록 처리"""
        extension = data.get('extension_num')
        if not extension:
            self.log(f"내선번호 없음: {client_ip}")
            await websocket.send(json.dumps({
                'type': 'error',
                'message': '내선번호가 제공되지 않았습니다.'
            }))
            return
        
        try:
            # MongoDB에 내선번호와 IP 매핑 저장
            self.log(f"{extension} 내선번호 등록 시도 (IP: {client_ip})")
            
            try:
                mongo_client = MongoClient(self.mongo_uri, serverSelectionTimeoutMS=2000)
                # 연결 테스트
                mongo_client.server_info()
                self.log("MongoDB 서버에 성공적으로 연결됨")
            except Exception as mongo_error:
                self.log("MongoDB 연결 실패", mongo_error)
                await websocket.send(json.dumps({
                    'type': 'error',
                    'message': '서버 오류로 등록 실패'
                }))
                return
            
            db = mongo_client['packetwave']
            members = db['members']
            
            # 기존 IP 주소 업데이트
            result = members.update_one(
                {'extension_num': extension},
                {'$set': {'default_ip': client_ip}},
                upsert=True
            )
            
            self.log(f"{extension} 내선번호 등록 완료 (IP: {client_ip})")
            await websocket.send(json.dumps({
                'type': 'register_response',
                'status': 'success',
                'message': f'내선번호 {extension} 등록 완료'
            }))
            
        except Exception as e:
            self.log("내선번호 등록 중 오류", e)
            await websocket.send(json.dumps({
                'type': 'error',
                'message': '서버 오류로 등록 실패'
            }))
    
    async def notify_client(self, to_number, from_number, call_id=None):
        """클라이언트에 수신 전화 알림"""
        try:
            self.log(f"내선번호 {to_number}에 알림 시도 (발신: {from_number})")
            
            # MongoDB에서 내선번호에 해당하는 IP 조회
            mongo_client = MongoClient(self.mongo_uri)
            db = mongo_client['packetwave']
            members = db['members']
            
            member = members.find_one({'extension_num': to_number})
            if not member:
                self.log(f"내선번호 {to_number}에 대한 정보 없음")
                return
            
            ip = member.get('default_ip')
            if not ip:
                self.log(f"내선번호 {to_number}에 대한 IP 주소 없음")
                return
            
            # 해당 IP로 연결된 클라이언트가 있는지 확인
            if ip in self.connected_clients:
                message = {
                    'type': 'incoming_call',
                    'from': from_number,
                    'to': to_number,
                    'timestamp': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                
                if call_id:
                    message['call_id'] = call_id
                
                await self.connected_clients[ip].send(json.dumps(message))
                self.log(f"알림 전송 완료: 내선번호 {to_number} (IP: {ip})")
            else:
                self.log(f"클라이언트 연결 없음: 내선번호 {to_number} (IP: {ip})")
        except Exception as e:
            self.log("알림 전송 중 오류", e)
    
    def is_port_in_use(self, port):
        """지정된 포트가 사용 중인지 확인"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('0.0.0.0', port))
                return False
            except socket.error:
                return True
    
    async def start_server(self):
        """WebSocket 서버 시작"""
        current_port = self.port
        retry_count = 0
        
        while retry_count < self.max_port_retry:
            if self.is_port_in_use(current_port):
                self.log(f"포트 {current_port}가 이미 사용 중입니다. 다른 포트 시도...")
                retry_count += 1
                current_port += 1
                continue
            
            try:
                self.log(f"WebSocket 서버 시작: 포트 {current_port}")
                self.server = await websockets.serve(self.handler, "0.0.0.0", current_port)
                self.port = current_port  # 실제 사용 중인 포트 업데이트
                self.running = True
                self.log(f"WebSocket 서버가 포트 {current_port}에서 실행 중")
                return self.server
            except OSError as e:
                self.log(f"포트 {current_port} 바인딩 실패", e)
                retry_count += 1
                current_port += 1
        
        raise RuntimeError(f"모든 포트 시도 실패 (포트 {self.port}~{current_port-1})")
    
    async def stop_server(self):
        """WebSocket 서버 중지"""
        if self.server:
            self.log("WebSocket 서버 종료 중...")
            self.server.close()
            await self.server.wait_closed()
            self.log("WebSocket 서버가 정상적으로 종료됨")
            self.running = False

def handle_signal(ws_server, loop):
    """시그널 핸들러"""
    async def shutdown():
        print("\n서버 종료 신호를 받았습니다. 서버를 종료합니다...")
        if ws_server.running:
            await ws_server.stop_server()
        loop.stop()
    
    loop.create_task(shutdown())

async def main_async(args):
    """비동기 메인 함수"""
    # 서버 인스턴스 생성
    ws_server = StandaloneWebSocketServer(
        port=args.port,
        max_port_retry=args.max_retry,
        mongo_uri=args.mongo_uri
    )
    
    # 시그널 핸들러 설정
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: handle_signal(ws_server, loop))
    
    # 서버 시작
    await ws_server.start_server()
    
    # 테스트 모드인 경우 테스트 알림 전송
    if args.test:
        await asyncio.sleep(2)  # 서버 안정화를 위한 대기
        ws_server.log("테스트 모드: 가상의 알림 전송을 시작합니다...")
        
        # 테스트 알림 전송
        test_extensions = ["1234", "1001", "1427"]
        for ext in test_extensions:
            ws_server.log(f"테스트 알림 전송 시도: 내선번호 {ext}")
            await ws_server.notify_client(ext, "01012345678", "test_call_id_123")
            await asyncio.sleep(1)
    
    # 서버 실행 상태 유지
    await asyncio.Future()  # 무한 대기

def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(description="독립형 WebSocket 서버")
    parser.add_argument("--port", type=int, default=8765, help="WebSocket 서버 포트 (기본값: 8765)")
    parser.add_argument("--max-retry", type=int, default=5, help="포트 바인딩 실패 시 최대 재시도 횟수 (기본값: 5)")
    parser.add_argument("--mongo-uri", type=str, default="mongodb://localhost:27017/", 
                        help="MongoDB 연결 URI (기본값: mongodb://localhost:27017/)")
    parser.add_argument("--test", action="store_true", help="테스트 모드 실행 (가상의 알림 전송)")
    
    args = parser.parse_args()
    
    print("="*50)
    print(f"독립형 WebSocket 서버 시작")
    print(f"포트: {args.port}")
    print(f"MongoDB URI: {args.mongo_uri}")
    if args.test:
        print("모드: 테스트 (가상의 알림 전송 포함)")
    print("="*50)
    print("서버를 종료하려면 Ctrl+C를 누르세요.")
    
    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        print("\n사용자에 의해 서버가 종료되었습니다.")
    except Exception as e:
        print(f"서버 실행 중 오류 발생: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main() 