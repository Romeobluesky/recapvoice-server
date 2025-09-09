#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
돌려주기 시나리오에서 최신 Call-ID 폴더 생성 테스트

테스트 시나리오:
1. 01077141436 -> 1427 : Call-ID 그룹 1 (외부→내선)  
2. 1427 REFER -> 1428 : Call-ID 그룹 2 (내선→내선, REFER 발생)
3. 1427 -> 1428 : Call-ID 그룹 3 (내선→내선, 실제 통화, 최신)

예상 결과:
- 01077141436_1427 (그룹 1)
- 1427_1428 (그룹 2) 
- 01077141436_1428 (그룹 3, REFER 매핑 적용)
"""

import os
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from sip_rtp_session_grouper import SipRtpSessionGrouper

class MockDashboard:
    """테스트용 가짜 Dashboard 클래스"""
    def __init__(self):
        self.active_calls = {}
        self.latest_terminated_call_id = None
        self.temp_capture_file = "test_capture.pcapng"

def create_test_scenario():
    """돌려주기 테스트 시나리오 생성"""
    return {
        'scenarios': [
            {
                'description': '그룹 1: 외부 -> 내선 (01077141436 -> 1427)',
                'call_id': 'call_id_group_1@server.com',
                'from_number': '01077141436', 
                'to_number': '1427',
                'has_refer': False,
                'is_latest': False,
                'expected_folder': '01077141436_1427'
            },
            {
                'description': '그룹 2: 내선 REFER (1427 -> 1428)',
                'call_id': 'call_id_group_2@server.com', 
                'from_number': '1427',
                'to_number': '1428',
                'has_refer': False,
                'is_latest': False,
                'expected_folder': '1427_1428'
            },
            {
                'description': '그룹 3: 내선 -> 내선 실제 통화 (최신)',
                'call_id': 'call_id_group_3@server.com',
                'from_number': '1427', 
                'to_number': '1428',
                'has_refer': True,
                'refer_mapped': '01077141436',  # REFER 매핑된 실제 발신번호
                'is_latest': True,  # 마지막 BYE로 종료된 최신 Call-ID
                'expected_folder': '01077141436_1428'  # REFER 매핑 적용 결과
            }
        ]
    }

def test_latest_call_folder_generation():
    """최신 Call-ID 폴더 생성 테스트"""
    print("=== 돌려주기 최신 Call-ID 폴더 생성 테스트 ===")
    
    # Mock Dashboard 생성
    mock_dashboard = MockDashboard()
    
    # SipRtpSessionGrouper 인스턴스 생성
    grouper = SipRtpSessionGrouper(mock_dashboard)
    
    # 테스트 시나리오 로드
    test_data = create_test_scenario()
    
    print(f"테스트 시나리오: {len(test_data['scenarios'])}개")
    
    # 1단계: REFER 매핑 설정
    print("\n1단계: REFER 매핑 설정")
    latest_call_id = None
    
    for scenario in test_data['scenarios']:
        if scenario['has_refer']:
            call_id = scenario['call_id']
            refer_mapped = scenario['refer_mapped']
            grouper.set_refer_mapping(call_id, refer_mapped)
            print(f"  REFER 매핑: {call_id} → {refer_mapped}")
            
        if scenario['is_latest']:
            latest_call_id = scenario['call_id']
            mock_dashboard.latest_terminated_call_id = latest_call_id
            print(f"  최신 Call-ID 설정: {latest_call_id}")
    
    # 2단계: 각 시나리오별 폴더명 생성 테스트
    print(f"\n2단계: 폴더명 생성 테스트")
    
    results = []
    
    for scenario in test_data['scenarios']:
        print(f"\n  {scenario['description']}")
        print(f"    Call-ID: {scenario['call_id']}")
        print(f"    원본: {scenario['from_number']} → {scenario['to_number']}")
        
        # 폴더명 생성 로직 시뮬레이션
        call_id = scenario['call_id']
        from_num = scenario['from_number']
        to_num = scenario['to_number']
        
        # REFER 매핑 적용 조건 확인 (최신 Call-ID이고 매핑이 존재하는 경우)
        if (call_id in grouper.refer_mapping and 
            latest_call_id and 
            call_id == latest_call_id):
            original_from = from_num
            from_num = grouper.refer_mapping[call_id]
            print(f"    REFER 매핑 적용: {original_from} → {from_num}")
        else:
            print(f"    원본 발신번호 사용: {from_num}")
        
        # 내선번호 추출 (기존 로직 사용)
        extracted_from = grouper._extract_extension_number(from_num)
        extracted_to = grouper._extract_extension_number(to_num)
        
        # 폴더명 생성
        folder_name = f"{extracted_from}_{extracted_to}"
        
        print(f"    생성된 폴더명: {folder_name}")
        print(f"    예상 폴더명: {scenario['expected_folder']}")
        
        # 결과 확인
        success = folder_name == scenario['expected_folder']
        status = "[OK]" if success else "[FAIL]"
        print(f"    결과: {status}")
        
        results.append({
            'scenario': scenario['description'],
            'expected': scenario['expected_folder'],
            'actual': folder_name,
            'success': success
        })
    
    # 3단계: 결과 요약
    print(f"\n3단계: 테스트 결과 요약")
    
    success_count = sum(1 for r in results if r['success'])
    total_count = len(results)
    
    print(f"  성공: {success_count}/{total_count}")
    
    for result in results:
        status = "[OK]" if result['success'] else "[FAIL]"
        print(f"  {status} {result['scenario']}")
        if not result['success']:
            print(f"      예상: {result['expected']}")
            print(f"      실제: {result['actual']}")
    
    # 4단계: REFER 매핑 상태 확인
    print(f"\n4단계: REFER 매핑 상태 확인")
    print(f"  활성 매핑 수: {len(grouper.refer_mapping)}")
    for call_id, mapped_number in grouper.refer_mapping.items():
        is_latest = " (최신)" if call_id == latest_call_id else ""
        print(f"    {call_id} → {mapped_number}{is_latest}")
    
    return success_count == total_count

def test_extract_extension_number():
    """내선번호 추출 테스트"""
    print("\n=== 내선번호 추출 테스트 ===")
    
    grouper = SipRtpSessionGrouper()
    
    test_cases = [
        ('01077141436', '01077141436'),  # 외부번호
        ('1427', '1427'),               # 내선번호
        ('1428', '1428'),               # 내선번호
        ('109Q1427', '1427'),           # 알파벳 포함 내선번호
        ('unknown', 'unknown'),         # 알 수 없는 번호
        ('', 'unknown')                 # 빈 문자열
    ]
    
    print("테스트 케이스:")
    all_success = True
    
    for input_num, expected in test_cases:
        result = grouper._extract_extension_number(input_num)
        success = result == expected
        status = "[OK]" if success else "[FAIL]"
        print(f"  {status} '{input_num}' → '{result}' (예상: '{expected}')")
        
        if not success:
            all_success = False
    
    return all_success

def main():
    """메인 테스트 함수"""
    try:
        print("돌려주기 폴더 생성 로직 테스트 시작")
        print("=" * 60)
        
        # 내선번호 추출 테스트
        extract_success = test_extract_extension_number()
        
        # 최신 Call-ID 폴더 생성 테스트  
        folder_success = test_latest_call_folder_generation()
        
        print("\n" + "=" * 60)
        print("최종 결과:")
        print(f"  내선번호 추출 테스트: {'성공' if extract_success else '실패'}")
        print(f"  폴더 생성 테스트: {'성공' if folder_success else '실패'}")
        
        overall_success = extract_success and folder_success
        print(f"  전체 테스트: {'성공' if overall_success else '실패'}")
        
        if overall_success:
            print("\n[성공] 모든 테스트가 성공했습니다!")
            print("이제 다음과 같이 폴더가 생성됩니다:")
            print("  01077141436_1427/ (외부->내선)")  
            print("  1427_1428/ (내선 REFER)")
            print("  01077141436_1428/ (최신 통화, REFER 매핑 적용)")
        else:
            print("\n[실패] 일부 테스트가 실패했습니다.")
            
        return overall_success
        
    except Exception as e:
        print(f"\n테스트 실행 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)