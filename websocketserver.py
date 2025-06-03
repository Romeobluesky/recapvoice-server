#!/mvenv/Scripts/activate
# -*- coding: utf-8 -*-
import asyncio
import datetime
import json
import traceback
import websockets
from pymongo import MongoClient
import socket

class WebSocketServer:
    """WebSocket 서버 클래스: SIP 패킷 감지 시 클라이언트에게 알림을 전송합니다."""
    
    def __init__(self, port=8765, log_callback=None, max_port_retry=5):
        self.port = port
        self.max_port_retry = max_port_retry  # 최대 포트 재시도 횟수
        self.connected_clients = {}  # ip -> websocket
        self.log_callback = log_callback
        self.server = None
        self.running = False
        print(f"WebSocketServer 초기화: 포트 {port}")
    
    def log(self, message, error=None):
        """로그 메시지 기록"""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] WebSocketServer: {message}")
        
        if self.log_callback:
            self.log_callback(message, error)
        
        if error:
            print(f"[{timestamp}] WebSocketServer 오류: {str(error)}")
            print(traceback.format_exc())
    
    async def handler(self, websocket):
        """WebSocket 연결 처리"""
        client_ip = websocket.remote_address[0]
        self.connected_clients[client_ip] = websocket
        print(f"[연결 성공] 클라이언트 연결됨: {client_ip}")
        print(f"[상태] 현재 연결된 클라이언트: {len(self.connected_clients)}개")
        self.log(f"클라이언트 연결됨: {client_ip}")
        
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    print(f"[메시지 수신] 클라이언트({client_ip})로부터: {data}")
                    self.log(f"클라이언트로부터 메시지 수신: {data}")
                    
                    # 클라이언트가 내선번호 등록 요청을 보낸 경우
                    if data.get('type') == 'register':
                        await self.handle_register(websocket, data, client_ip)
                except json.JSONDecodeError:
                    print(f"[오류] 잘못된 JSON 형식: {message}")
                    self.log(f"잘못된 JSON 형식: {message}")
                except Exception as e:
                    print(f"[오류] 메시지 처리 중 오류 발생: {str(e)}")
                    self.log("메시지 처리 중 오류 발생", e)
        except websockets.exceptions.ConnectionClosed:
            print(f"[연결 종료] 클라이언트 연결 종료: {client_ip}")
            self.log(f"클라이언트 연결 종료: {client_ip}")
        finally:
            if client_ip in self.connected_clients:
                del self.connected_clients[client_ip]
                print(f"[상태] 현재 연결된 클라이언트: {len(self.connected_clients)}개")
    
    async def handle_register(self, websocket, data, client_ip):
        """내선번호 등록 처리"""
        extension = data.get('extension_num')
        if not extension:
            print(f"[오류] 내선번호 없음: {client_ip}")
            await websocket.send(json.dumps({
                'type': 'error',
                'message': '내선번호가 제공되지 않았습니다.'
            }))
            return
        
        try:
            # MongoDB에 내선번호와 IP 매핑 저장
            print(f"[MongoDB] {extension} 내선번호 등록 시도 (IP: {client_ip})")
            mongo_client = None
            try:
                mongo_client = MongoClient("mongodb://localhost:27017/", serverSelectionTimeoutMS=2000)
                # 연결 테스트
                mongo_client.server_info()
                print(f"[MongoDB] 서버에 성공적으로 연결됨")
            except Exception as mongo_error:
                print(f"[MongoDB 오류] 연결 실패: {str(mongo_error)}")
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
            
            print(f"[MongoDB] {extension} 내선번호 등록 완료 (IP: {client_ip})")
            await websocket.send(json.dumps({
                'type': 'register_response',
                'status': 'success',
                'message': f'내선번호 {extension} 등록 완료'
            }))
            
            self.log(f"내선번호 등록 완료: {extension} -> {client_ip}")
            
        except Exception as e:
            print(f"[MongoDB 오류] 내선번호 등록 실패: {str(e)}")
            print(traceback.format_exc())
            self.log(f"내선번호 등록 중 오류", e)
            await websocket.send(json.dumps({
                'type': 'error',
                'message': '서버 오류로 등록 실패'
            }))
    
    async def notify_client(self, to_number, from_number, call_id=None):
        """클라이언트에 수신 전화 알림"""
        try:
            print(f"[알림 시작] 내선번호 {to_number}에 알림 시도 (발신: {from_number})")
            # MongoDB에서 내선번호에 해당하는 IP 조회
            mongo_client = MongoClient("mongodb://localhost:27017/")
            db = mongo_client['packetwave']
            members = db['members']
            
            member = members.find_one({'extension_num': to_number})
            if not member:
                print(f"[MongoDB] 내선번호 {to_number}에 대한 정보 없음")
                self.log(f"내선번호 {to_number}에 대한 정보 없음")
                return
            
            ip = member.get('default_ip')
            if not ip:
                print(f"[MongoDB] 내선번호 {to_number}에 대한 IP 주소 없음")
                self.log(f"내선번호 {to_number}에 대한 IP 주소 없음")
                return
            
            print(f"[알림 처리] 내선번호 {to_number}의 IP 주소: {ip}")
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
                
                print(f"[알림 전송] 메시지 전송: {message}")
                await self.connected_clients[ip].send(json.dumps(message))
                print(f"[알림 완료] 내선번호 {to_number} (IP: {ip})에 알림 전송 완료")
                self.log(f"알림 전송 완료: {to_number} (IP: {ip})")
            else:
                print(f"[알림 실패] 클라이언트 연결 없음: 내선번호 {to_number} (IP: {ip})")
                self.log(f"클라이언트 연결 없음: {ip}")
        except Exception as e:
            print(f"[알림 오류] 알림 전송 중 오류: {str(e)}")
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
                print(f"[서버 경고] 포트 {current_port}가 이미 사용 중입니다.")
                self.log(f"포트 {current_port}가 이미 사용 중입니다. 다른 포트 시도...")
                retry_count += 1
                current_port += 1
                continue
            
            try:
                print(f"[서버 시작] WebSocket 서버 시작: 포트 {current_port}")
                self.log(f"WebSocket 서버 시작: 포트 {current_port}")
                self.server = await websockets.serve(self.handler, "0.0.0.0", current_port)
                self.port = current_port  # 실제 사용 중인 포트 업데이트
                self.running = True
                print(f"[서버 상태] WebSocket 서버가 포트 {current_port}에서 실행 중")
                return self.server
            except OSError as e:
                print(f"[서버 오류] 포트 {current_port} 바인딩 실패: {str(e)}")
                self.log(f"포트 {current_port} 바인딩 실패", e)
                retry_count += 1
                current_port += 1
        
        raise RuntimeError(f"모든 포트 시도 실패 (포트 {self.port}~{current_port-1})")
    
    async def stop_server(self):
        """WebSocket 서버 중지"""
        if self.server:
            print("[서버 종료] WebSocket 서버 종료 중...")
            self.server.close()
            await self.server.wait_closed()
            print("[서버 종료] WebSocket 서버가 정상적으로 종료됨")
            self.log("WebSocket 서버 중지됨")
            self.running = False
    
    def run_in_thread(self):
        """별도 스레드에서 서버 실행"""
        asyncio.set_event_loop(asyncio.new_event_loop())
        loop = asyncio.get_event_loop()
        
        try:
            print("[스레드] WebSocket 서버 스레드 시작")
            self.log("WebSocket 서버 스레드 시작")
            server = loop.run_until_complete(self.start_server())
            loop.run_forever()
        except Exception as e:
            print(f"[스레드 오류] WebSocket 서버 실행 중 오류: {str(e)}")
            self.log("WebSocket 서버 실행 중 오류", e)
        finally:
            if self.running:
                loop.run_until_complete(self.stop_server())
            loop.close()
            print("[스레드] WebSocket 서버 스레드 종료")
            self.log("WebSocket 서버 스레드 종료")
