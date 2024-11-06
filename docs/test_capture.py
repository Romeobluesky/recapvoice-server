import pyshark
import subprocess

def test_tshark():
    print("=== TShark 테스트 ===")
    try:
        result = subprocess.run(['tshark', '--version'], capture_output=True, text=True)
        print("TShark 버전:", result.stdout)
    except Exception as e:
        print("TShark 실행 오류:", str(e))

def test_interfaces():
    print("\n=== 네트워크 인터페이스 테스트 ===")
    try:
        interfaces = pyshark.LiveCapture.get_interfaces()
        print("사용 가능한 인터페이스:")
        for interface in interfaces:
            print(f"- {interface}")
    except Exception as e:
        print("인터페이스 조회 오류:", str(e))

def test_capture():
    print("\n=== 패킷 캡처 테스트 ===")
    try:
        # 여기서 'Ethernet'은 실제 인터페이스 이름으로 변경해야 할 수 있습니다
        capture = pyshark.LiveCapture(interface='이더넷')
        print("캡처 시작... (10개 패킷 캡처 후 종료)")
        
        for packet in capture.sniff_continuously(packet_count=10):
            print(f"패킷 감지: {packet.highest_layer}")
            
    except Exception as e:
        print("PyShark 오류:", str(e))

if __name__ == "__main__":
    test_tshark()
    test_interfaces()
    test_capture()
