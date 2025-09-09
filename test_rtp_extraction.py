#!/usr/bin/env python3
"""
FFmpeg 기반 RTP 추출 테스트 스크립트
"""

import sys
import os
from pathlib import Path

# 현재 디렉토리를 Python 경로에 추가
sys.path.insert(0, str(Path(__file__).parent))

from sip_rtp_session_grouper import SipRtpSessionGrouper

def test_rtp_extraction():
    """실제 pcapng 파일로 RTP 추출 테스트"""
    # 테스트할 pcapng 파일
    test_file = Path("temp_recordings/3f5dbb4a2414610610ded07e7b3a5411776a2f99_112.222.225.77.pcapng")
    
    if not test_file.exists():
        print(f"테스트 파일이 없습니다: {test_file}")
        return False
    
    print(f"테스트 파일: {test_file}")
    print(f"파일 크기: {test_file.stat().st_size} bytes")
    
    # SipRtpSessionGrouper 인스턴스 생성
    grouper = SipRtpSessionGrouper()
    
    try:
        # RTP 스트림 분석 테스트
        print("\n1. RTP 스트림 분석 테스트")
        rtp_streams = grouper._analyze_rtp_streams_with_ffmpeg(test_file)
        
        if not rtp_streams:
            print("RTP 스트림을 찾을 수 없습니다")
            return False
        
        print(f"{len(rtp_streams)}개의 RTP 스트림 발견")
        for i, stream in enumerate(rtp_streams):
            print(f"   스트림 {i+1}: {stream['src_ip']}:{stream['src_port']} -> {stream['dst_ip']}:{stream['dst_port']}")
            print(f"             SSRC: {stream['ssrc']}, 패킷: {stream['packet_count']}개")
        
        # WAV 변환 테스트
        print("\n2. WAV 변환 테스트")
        success = grouper._extract_rtp_to_wav(
            test_file, 
            "01077141436",  # from_number
            "109Q1427",     # to_number  
            "3f5dbb4a2414610610ded07e7b3a5411776a2f99@112.222.225.77"  # call_id
        )
        
        if success:
            print("WAV 변환 성공!")
            
            # 생성된 파일 확인
            recording_path = grouper._get_final_recording_path("01077141436", "109Q1427")
            if recording_path:
                print(f"녹음 경로: {recording_path}")
                
                wav_files = list(recording_path.glob("*.wav"))
                if wav_files:
                    print("생성된 WAV 파일들:")
                    for wav_file in wav_files:
                        size = wav_file.stat().st_size
                        print(f"   - {wav_file.name} ({size} bytes)")
                else:
                    print("WAV 파일이 생성되지 않았습니다")
            
            return True
        else:
            print("WAV 변환 실패")
            return False
            
    except Exception as e:
        print(f"테스트 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("FFmpeg 기반 RTP 추출 테스트 시작")
    print("=" * 50)
    
    success = test_rtp_extraction()
    
    print("\n" + "=" * 50)
    if success:
        print("테스트 성공!")
    else:
        print("테스트 실패!")
    
    print("테스트 완료")