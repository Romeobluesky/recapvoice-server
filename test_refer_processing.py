#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
REFER 처리 및 폴더 생성 테스트
"""

import os
import sys
import tempfile
from pathlib import Path
from sip_rtp_session_grouper import SipRtpSessionGrouper
from extension_recording_manager import ExtensionRecordingManager

def test_refer_mapping():
    """REFER 매핑 기능 테스트"""
    print("=== REFER 매핑 기능 테스트 ===")
    
    # SipRtpSessionGrouper 인스턴스 생성
    grouper = SipRtpSessionGrouper()
    
    # 테스트 케이스들
    test_cases = [
        {
            'call_id': 'test-call-123@server.com',
            'original_from': '109Q1427',  # REFER 전 발신번호
            'refer_from': '5000',        # REFER 후 실제 발신번호
            'to_number': '2000'
        },
        {
            'call_id': 'test-call-456@server.com', 
            'original_from': '109X5678',
            'refer_from': '6000',
            'to_number': '3000'
        }
    ]
    
    for i, case in enumerate(test_cases, 1):
        print(f"\n테스트 케이스 {i}:")
        print(f"  Call-ID: {case['call_id']}")
        print(f"  원본 발신번호: {case['original_from']}")
        print(f"  REFER 후 발신번호: {case['refer_from']}")
        
        # REFER 매핑 설정
        grouper.set_refer_mapping(case['call_id'], case['refer_from'])
        
        # 매핑 확인
        if case['call_id'] in grouper.refer_mapping:
            mapped_number = grouper.refer_mapping[case['call_id']]
            print(f"  [OK] 매핑 성공: {mapped_number}")
        else:
            print(f"  [FAIL] 매핑 실패")
    
    # 전체 매핑 상태 출력
    print(f"\n현재 REFER 매핑 상태:")
    for call_id, from_number in grouper.refer_mapping.items():
        print(f"  {call_id} → {from_number}")
    
    # 매핑 정리 테스트
    print(f"\n매핑 정리 테스트:")
    grouper.clear_refer_mapping(test_cases[0]['call_id'])
    print(f"  남은 매핑 수: {len(grouper.refer_mapping)}")
    
    grouper.clear_refer_mapping()  # 전체 정리
    print(f"  전체 정리 후 매핑 수: {len(grouper.refer_mapping)}")

def test_extension_number_extraction_with_refer():
    """내선번호 추출과 REFER 매핑 조합 테스트"""
    print("\n=== 내선번호 추출 + REFER 매핑 테스트 ===")
    
    grouper = SipRtpSessionGrouper()
    
    test_scenarios = [
        {
            'name': 'REFER 매핑 있음',
            'call_id': 'call-with-refer@server.com',
            'original_from': '109Q1427',  # 내선번호 포함
            'refer_mapped': '5000',       # REFER 매핑된 번호
            'to_number': '109X2000',
            'expected_folder': '5000_2000'  # REFER 번호 + 추출된 내선번호
        },
        {
            'name': 'REFER 매핑 없음',
            'call_id': 'call-without-refer@server.com', 
            'original_from': '109Q1427',
            'refer_mapped': None,
            'to_number': '109X2000',
            'expected_folder': '1427_2000'  # 둘 다 추출된 내선번호
        },
        {
            'name': '순수 숫자',
            'call_id': 'call-numeric@server.com',
            'original_from': '1427',
            'refer_mapped': None, 
            'to_number': '2000',
            'expected_folder': '1427_2000'
        }
    ]
    
    for scenario in test_scenarios:
        print(f"\n시나리오: {scenario['name']}")
        print(f"  Call-ID: {scenario['call_id']}")
        print(f"  원본 발신번호: {scenario['original_from']}")
        print(f"  REFER 매핑: {scenario['refer_mapped']}")
        print(f"  수신번호: {scenario['to_number']}")
        
        # REFER 매핑 설정 (있는 경우만)
        if scenario['refer_mapped']:
            grouper.set_refer_mapping(scenario['call_id'], scenario['refer_mapped'])
        
        # 실제 처리 시뮬레이션
        call_id = scenario['call_id']
        original_from = scenario['original_from']
        to_number = scenario['to_number']
        
        # REFER 매핑 확인 (sip_rtp_session_grouper.py의 로직과 동일)
        if call_id in grouper.refer_mapping:
            from_num = grouper.refer_mapping[call_id]
            print(f"  REFER 적용된 발신번호: {from_num}")
        else:
            from_num = original_from
            print(f"  원본 발신번호 사용: {from_num}")
        
        # 내선번호 추출
        extracted_from = grouper._extract_extension_number(from_num)
        extracted_to = grouper._extract_extension_number(to_number)
        
        # 폴더명 생성
        folder_name = f"{extracted_from}_{extracted_to}"
        
        print(f"  추출된 발신번호: {extracted_from}")
        print(f"  추출된 수신번호: {extracted_to}")
        print(f"  생성될 폴더명: {folder_name}")
        print(f"  예상 폴더명: {scenario['expected_folder']}")
        
        if folder_name == scenario['expected_folder']:
            print(f"  [OK] 성공!")
        else:
            print(f"  [FAIL] 실패! (예상: {scenario['expected_folder']}, 실제: {folder_name})")
        
        # 정리
        grouper.clear_refer_mapping()

def test_extension_recording_manager_integration():
    """ExtensionRecordingManager와의 통합 테스트"""
    print("\n=== ExtensionRecordingManager 통합 테스트 ===")
    
    # ExtensionRecordingManager 인스턴스 생성
    manager = ExtensionRecordingManager()
    
    test_call_id = "integration-test@server.com"
    test_refer_number = "7000"
    
    print(f"Call-ID: {test_call_id}")
    print(f"REFER 번호: {test_refer_number}")
    
    # REFER 매핑 설정
    manager.set_refer_mapping(test_call_id, test_refer_number)
    
    # SipRtpSessionGrouper에 제대로 전달되었는지 확인
    if test_call_id in manager.session_grouper.refer_mapping:
        mapped = manager.session_grouper.refer_mapping[test_call_id] 
        print(f"[OK] ExtensionRecordingManager → SipRtpSessionGrouper 매핑 성공: {mapped}")
    else:
        print(f"[FAIL] 매핑 실패")
    
    # 정리
    manager.clear_refer_mapping()
    print(f"매핑 정리 후 상태: {len(manager.session_grouper.refer_mapping)}개")

if __name__ == "__main__":
    try:
        test_refer_mapping()
        test_extension_number_extraction_with_refer()
        test_extension_recording_manager_integration()
        print("\n=== 모든 테스트 완료 ===")
        
    except Exception as e:
        print(f"테스트 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()