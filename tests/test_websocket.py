#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
WebSocket 클라이언트 테스트

이 모듈은 SIP 알림 시스템의 WebSocket 서버와 클라이언트 간의 
통신을 테스트하기 위한 테스트 코드를 제공합니다.
"""

import asyncio
import websockets
import json
import datetime
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import sys
import os

# 상위 디렉토리의 모듈들을 import하기 위한 경로 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class WebSocketTestClient:
    """WebSocket 테스트 클라이언트"""
    
    def __init__(self, uri="ws://localhost:8765", extension="1234"):
        self.uri = uri
        self.extension = extension
        self.connected = False
        self.received_messages = []
        
    async def connect_and_register(self):
        """서버에 연결하고 내선번호 등록"""
        try:
            async with websockets.connect(self.uri) as websocket:
                self.connected = True
                
                # 내선번호 등록 메시지 전송
                register_msg = {
                    "type": "register",
                    "extension_num": self.extension
                }
                
                await websocket.send(json.dumps(register_msg))
                
                # 응답 수신
                response = await websocket.recv()
                self.received_messages.append(response)
                
                return json.loads(response)
                
        except Exception as e:
            self.connected = False
            raise e
            
    async def listen_for_messages(self, duration=5):
        """지정된 시간 동안 메시지 수신 대기"""
        try:
            async with websockets.connect(self.uri) as websocket:
                # 먼저 등록
                register_msg = {
                    "type": "register",
                    "extension_num": self.extension
                }
                await websocket.send(json.dumps(register_msg))
                await websocket.recv()  # 등록 응답 무시
                
                # 메시지 수신 대기
                end_time = asyncio.get_event_loop().time() + duration
                while asyncio.get_event_loop().time() < end_time:
                    try:
                        message = await asyncio.wait_for(websocket.recv(), timeout=1)
                        data = json.loads(message)
                        self.received_messages.append(data)
                        
                        # 수신 확인 메시지 전송
                        if data.get("type") == "incoming_call":
                            confirm_msg = {
                                "type": "confirm_notification",
                                "call_id": data.get("call_id", ""),
                                "received_at": datetime.datetime.now().isoformat()
                            }
                            await websocket.send(json.dumps(confirm_msg))
                            
                    except asyncio.TimeoutError:
                        continue
                        
                return self.received_messages
                
        except Exception as e:
            raise e


@pytest.fixture
def test_client():
    """테스트 클라이언트 fixture"""
    return WebSocketTestClient()


@pytest.fixture
def mock_websocket():
    """Mock WebSocket fixture"""
    mock_ws = AsyncMock()
    return mock_ws


class TestWebSocketClient:
    """WebSocket 클라이언트 테스트 클래스"""
    
    def test_client_initialization(self):
        """클라이언트 초기화 테스트"""
        client = WebSocketTestClient("ws://localhost:8765", "1001")
        
        assert client.uri == "ws://localhost:8765"
        assert client.extension == "1001"
        assert client.connected is False
        assert client.received_messages == []
        
    def test_client_default_values(self):
        """클라이언트 기본값 테스트"""
        client = WebSocketTestClient()
        
        assert client.uri == "ws://localhost:8765"
        assert client.extension == "1234"
        
    @pytest.mark.asyncio
    async def test_connection_success(self, mock_websocket):
        """연결 성공 테스트"""
        # Mock 응답 설정
        mock_websocket.recv.return_value = json.dumps({
            "status": "success",
            "message": "등록 완료",
            "extension": "1234"
        })
        
        with patch('websockets.connect') as mock_connect:
            mock_connect.return_value.__aenter__.return_value = mock_websocket
            
            client = WebSocketTestClient()
            response = await client.connect_and_register()
            
            assert client.connected is True
            assert response["status"] == "success"
            assert response["extension"] == "1234"
            
    @pytest.mark.asyncio
    async def test_registration_message_format(self, mock_websocket):
        """등록 메시지 형식 테스트"""
        mock_websocket.recv.return_value = json.dumps({"status": "success"})
        
        with patch('websockets.connect') as mock_connect:
            mock_connect.return_value.__aenter__.return_value = mock_websocket
            
            client = WebSocketTestClient(extension="1001")
            await client.connect_and_register()
            
            # 전송된 메시지 확인
            sent_data = json.loads(mock_websocket.send.call_args[0][0])
            assert sent_data["type"] == "register"
            assert sent_data["extension_num"] == "1001"
            
    @pytest.mark.asyncio
    async def test_incoming_call_handling(self, mock_websocket):
        """수신 전화 알림 처리 테스트"""
        # Mock 메시지 시퀀스
        messages = [
            json.dumps({"status": "success"}),  # 등록 응답
            json.dumps({
                "type": "incoming_call",
                "from": "01077141436",
                "to": "1234",
                "call_id": "test-call-123"
            })
        ]
        
        mock_websocket.recv.side_effect = messages + [asyncio.TimeoutError()]
        
        with patch('websockets.connect') as mock_connect:
            mock_connect.return_value.__aenter__.return_value = mock_websocket
            
            client = WebSocketTestClient()
            received_messages = await client.listen_for_messages(duration=1)
            
            # 수신된 메시지 확인
            call_message = received_messages[0]
            assert call_message["type"] == "incoming_call"
            assert call_message["from"] == "01077141436"
            assert call_message["to"] == "1234"
            
            # 확인 메시지가 전송되었는지 확인
            confirm_calls = [call for call in mock_websocket.send.call_args_list 
                           if "confirm_notification" in str(call)]
            assert len(confirm_calls) > 0
            
    @pytest.mark.asyncio
    async def test_connection_failure(self):
        """연결 실패 테스트"""
        with patch('websockets.connect') as mock_connect:
            mock_connect.side_effect = ConnectionRefusedError("Connection refused")
            
            client = WebSocketTestClient("ws://invalid:8765")
            
            with pytest.raises(ConnectionRefusedError):
                await client.connect_and_register()
                
            assert client.connected is False
            
    @pytest.mark.asyncio
    async def test_invalid_response_handling(self, mock_websocket):
        """잘못된 응답 처리 테스트"""
        # 잘못된 JSON 응답
        mock_websocket.recv.return_value = "invalid json"
        
        with patch('websockets.connect') as mock_connect:
            mock_connect.return_value.__aenter__.return_value = mock_websocket
            
            client = WebSocketTestClient()
            
            with pytest.raises(json.JSONDecodeError):
                await client.connect_and_register()


class TestWebSocketIntegration:
    """WebSocket 통합 테스트"""
    
    @pytest.mark.skipif(True, reason="Requires running WebSocket server")
    @pytest.mark.asyncio
    async def test_real_server_connection(self):
        """실제 서버 연결 테스트 (서버가 실행 중일 때만)"""
        client = WebSocketTestClient("ws://localhost:8765", "test-1234")
        
        try:
            response = await client.connect_and_register()
            assert response is not None
        except (ConnectionRefusedError, OSError):
            pytest.skip("WebSocket 서버가 실행되지 않았습니다")
            
    @pytest.mark.skipif(True, reason="Requires running WebSocket server")
    @pytest.mark.asyncio
    async def test_message_flow(self):
        """메시지 플로우 테스트 (서버가 실행 중일 때만)"""
        client = WebSocketTestClient("ws://localhost:8765", "test-1001")
        
        try:
            # 연결 및 등록
            await client.connect_and_register()
            
            # 메시지 수신 대기 (5초)
            messages = await client.listen_for_messages(duration=5)
            
            # 결과 확인 (실제 메시지가 있을 경우)
            print(f"Received {len(messages)} messages")
            for msg in messages:
                print(f"Message: {msg}")
                
        except (ConnectionRefusedError, OSError):
            pytest.skip("WebSocket 서버가 실행되지 않았습니다")


def create_standalone_test_client():
    """독립적인 테스트 클라이언트 생성"""
    async def run_test_client(uri="ws://localhost:8765", extension="1234"):
        """테스트 클라이언트 실행"""
        print(f"WebSocket 테스트 클라이언트 시작 (내선번호: {extension}, URI: {uri})")
        
        client = WebSocketTestClient(uri, extension)
        
        try:
            # 연결 및 등록
            response = await client.connect_and_register()
            print(f"서버 연결 성공: {response}")
            
            # 메시지 수신 대기
            print("메시지 수신 대기 중... (10초)")
            messages = await client.listen_for_messages(duration=10)
            
            print(f"\n총 {len(messages)}개의 메시지를 수신했습니다:")
            for i, msg in enumerate(messages, 1):
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if isinstance(msg, dict) and msg.get("type") == "incoming_call":
                    from_num = msg.get("from", "알 수 없음")
                    to_num = msg.get("to", "알 수 없음")
                    print(f"[{timestamp}] {i}. 📞 전화 수신 알림! 발신: {from_num} → 수신: {to_num}")
                else:
                    print(f"[{timestamp}] {i}. 메시지: {msg}")
                    
        except ConnectionRefusedError:
            print(f"연결 거부됨: {uri}")
            print("서버가 실행 중인지 또는 방화벽 설정을 확인하세요.")
        except Exception as e:
            print(f"오류 발생: {e}")
    
    return run_test_client


# 직접 실행 시 테스트 실행
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "standalone":
        # 독립 실행 모드
        uri = "ws://localhost:8765"
        extension = "1234"
        
        if len(sys.argv) > 2:
            extension = sys.argv[2]
        if len(sys.argv) > 3:
            port = sys.argv[3]
            uri = f"ws://localhost:{port}"
        
        test_client = create_standalone_test_client()
        try:
            asyncio.run(test_client(uri, extension))
        except KeyboardInterrupt:
            print("\n사용자에 의해 프로그램이 종료되었습니다.")
    else:
        # pytest 실행 모드
        pytest.main([__file__, "-v"])