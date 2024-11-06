import pyshark
import datetime

def test_rtp_capture():
    print("=== RTP 패킷 캡처 테스트 ===")
    try:
        capture = pyshark.LiveCapture(
            interface='이더넷',
            display_filter='rtp || sip'
        )
        
        print("SIP/RTP 패킷 캡처 시작... (Ctrl+C로 중지)")
        
        # RTP 패킷 카운터
        rtp_count = 0
        
        for packet in capture.sniff_continuously():
            timestamp = datetime.datetime.now().strftime('%H:%M:%S.%f')
            
            if hasattr(packet, 'rtp'):
                rtp_count += 1
                print(f"\n[{timestamp}] RTP 패킷 #{rtp_count}:")
                
                # 패킷의 모든 레이어 확인
                print("\n레이어 정보:")
                for layer in packet.layers:
                    print(f"- {layer.layer_name}")
                
                # RTP 레이어의 모든 필드 확인
                print("\nRTP 필드:")
                for field in packet.rtp._all_fields:
                    try:
                        value = packet.rtp.get_field_value(field)
                        print(f"{field}: {value}")
                    except Exception as e:
                        print(f"{field}: 접근 오류")
                
                # 원시 데이터 확인
                try:
                    raw_data = bytes(packet.get_raw_packet())
                    print(f"\n패킷 크기: {len(raw_data)} bytes")
                except Exception as e:
                    print(f"원시 데이터 접근 오류: {str(e)}")
                
            elif hasattr(packet, 'sip'):
                print(f"\n[{timestamp}] SIP 패킷:")
                print(f"Method: {packet.sip.get_field_value('method') if hasattr(packet.sip, 'method') else 'Response'}")
                print(f"Call-ID: {packet.sip.call_id}")
                
                if hasattr(packet, 'sdp'):
                    print("SDP 정보:")
                    print(f"미디어 IP: {packet.sdp.connection_info_address}")
                    print(f"미디어 포트: {packet.sdp.media_port}")
                    print(f"미디어 타입: {packet.sdp.media_type}")
                
    except KeyboardInterrupt:
        print("\n캡처 중지됨")
        print(f"총 {rtp_count}개의 RTP 패킷 캡처됨")
    except Exception as e:
        print(f"오류 발생: {str(e)}")

if __name__ == "__main__":
    test_rtp_capture() 