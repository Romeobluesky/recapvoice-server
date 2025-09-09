#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
다중 콜 환경에서 REFER 처리 테스트
"""

import os
import sys
import tempfile
from pathlib import Path
from sip_rtp_session_grouper import SipRtpSessionGrouper
from extension_recording_manager import ExtensionRecordingManager

def test_multi_call_refer_scenario():
    """다중 콜 환경에서 REFER 매핑 테스트"""
    print("=== 다중 콜 REFER 매핑 시나리오 테스트 ===")
    
    grouper = SipRtpSessionGrouper()
    
    # 동시 진행되는 여러 콜 시나리오
    multi_call_scenario = [
        {
            'call_id': 'call-001@server.com',
            'original_from': '109Q1001',
            'to_number': '109X2001', 
            'has_refer': True,
            'refer_to': '5001',
            'expected_folder': '5001_2001',
            'description': '콜1: REFER 발생'
        },
        {
            'call_id': 'call-002@server.com',
            'original_from': '109Q1002',
            'to_number': '109X2002',
            'has_refer': False,
            'refer_to': None,
            'expected_folder': '1002_2002', 
            'description': '콜2: REFER 없음'
        },
        {
            'call_id': 'call-003@server.com',
            'original_from': '109Q1003',
            'to_number': '109X2003',
            'has_refer': True,
            'refer_to': '5003',
            'expected_folder': '5003_2003',
            'description': '콜3: REFER 발생'
        },
        {
            'call_id': 'call-004@server.com',
            'original_from': '1004',  # 순수 숫자
            'to_number': '2004',
            'has_refer': False,
            'refer_to': None,
            'expected_folder': '1004_2004',
            'description': '콜4: 순수 숫자, REFER 없음'
        }
    ]
    
    # Step 1: 모든 콜의 REFER 매핑 설정
    print("\n1단계: 다중 콜 REFER 매핑 설정")
    for scenario in multi_call_scenario:
        if scenario['has_refer']:
            grouper.set_refer_mapping(scenario['call_id'], scenario['refer_to'])
            print(f"  {scenario['description']}: {scenario['call_id']} → {scenario['refer_to']}")
        else:
            print(f"  {scenario['description']}: REFER 매핑 없음")
    
    # Step 2: 매핑 상태 확인
    print(f"\n2단계: 현재 REFER 매핑 상태")
    print(f"  총 매핑 수: {len(grouper.refer_mapping)}")
    for call_id, mapped_number in grouper.refer_mapping.items():
        print(f"  {call_id} → {mapped_number}")
    
    # Step 3: 각 콜 처리 시뮬레이션
    print(f"\n3단계: 각 콜별 폴더명 생성 테스트")
    for scenario in multi_call_scenario:
        call_id = scenario['call_id']
        original_from = scenario['original_from']
        to_number = scenario['to_number']
        
        print(f"\n  {scenario['description']}:")
        print(f"    Call-ID: {call_id}")
        print(f"    원본 발신번호: {original_from}")
        print(f"    수신번호: {to_number}")
        
        # REFER 매핑 확인 및 적용 (실제 process_captured_pcap 로직과 동일)
        if call_id in grouper.refer_mapping:
            from_num = grouper.refer_mapping[call_id]
            print(f"    REFER 적용된 발신번호: {from_num}")
        else:
            from_num = original_from
            print(f"    원본 발신번호 사용: {from_num}")
        
        # 내선번호 추출
        extracted_from = grouper._extract_extension_number(from_num)
        extracted_to = grouper._extract_extension_number(to_number)
        
        # 폴더명 생성
        folder_name = f"{extracted_from}_{extracted_to}"
        
        print(f"    추출된 발신번호: {extracted_from}")
        print(f"    추출된 수신번호: {extracted_to}")
        print(f"    생성될 폴더명: {folder_name}")
        print(f"    예상 폴더명: {scenario['expected_folder']}")
        
        if folder_name == scenario['expected_folder']:
            print(f"    [OK] 성공!")
        else:
            print(f"    [FAIL] 실패! (예상: {scenario['expected_folder']}, 실제: {folder_name})")
    
    # Step 4: 콜 종료 시뮬레이션 (REFER 매핑 자동 정리 테스트)
    print(f"\n4단계: 콜 종료 시 REFER 매핑 자동 정리 테스트")
    
    # 콜1과 콜3 종료 (REFER 매핑이 있던 콜들)
    calls_to_end = ['call-001@server.com', 'call-003@server.com']
    
    for call_id in calls_to_end:
        if call_id in grouper.refer_mapping:
            print(f"  {call_id} 종료 전 매핑 존재: {grouper.refer_mapping[call_id]}")
            grouper.clear_refer_mapping(call_id)
            print(f"  {call_id} 종료 후 매핑 정리 완료")
        else:
            print(f"  {call_id}: 매핑 없음")
    
    print(f"  현재 남은 REFER 매핑 수: {len(grouper.refer_mapping)}")
    for call_id, mapped_number in grouper.refer_mapping.items():
        print(f"    {call_id} → {mapped_number}")
    
    # Step 5: 메모리 누수 방지 테스트
    print(f"\n5단계: 메모리 누수 방지 테스트")
    initial_mapping_count = len(grouper.refer_mapping)
    
    # 새로운 콜 추가 (기존 매핑과 겹치지 않는 Call-ID)
    new_calls = [
        {'call_id': 'new-call-001@server.com', 'refer_to': '6001'},
        {'call_id': 'new-call-002@server.com', 'refer_to': '6002'},
    ]
    
    for call in new_calls:
        grouper.set_refer_mapping(call['call_id'], call['refer_to'])
        print(f"  신규 콜 매핑: {call['call_id']} → {call['refer_to']}")
    
    print(f"  신규 콜 추가 후 총 매핑 수: {len(grouper.refer_mapping)}")
    
    # 모든 신규 콜 정리
    for call in new_calls:
        grouper.clear_refer_mapping(call['call_id'])
        print(f"  신규 콜 정리: {call['call_id']}")
    
    final_mapping_count = len(grouper.refer_mapping)
    print(f"  최종 매핑 수: {final_mapping_count}")
    
    if final_mapping_count == initial_mapping_count:
        print(f"  [OK] 메모리 누수 없음 - 매핑 수가 초기 상태로 복원됨")
    else:
        print(f"  [WARN] 매핑 수 불일치 - 초기: {initial_mapping_count}, 최종: {final_mapping_count}")

def test_concurrent_refer_operations():
    """동시 REFER 작업 테스트"""
    print("\n=== 동시 REFER 작업 테스트 ===")
    
    grouper = SipRtpSessionGrouper()
    
    # 동시에 여러 REFER 매핑 설정
    concurrent_calls = [
        {'call_id': f'concurrent-{i:03d}@server.com', 'refer_to': f'700{i}'} 
        for i in range(1, 11)  # 10개 동시 콜
    ]
    
    print(f"1단계: {len(concurrent_calls)}개 동시 콜 REFER 매핑 설정")
    for call in concurrent_calls:
        grouper.set_refer_mapping(call['call_id'], call['refer_to'])
    
    print(f"  총 매핑 수: {len(grouper.refer_mapping)}")
    
    # 매핑 정확성 확인
    print(f"2단계: 매핑 정확성 확인")
    all_correct = True
    for call in concurrent_calls:
        if call['call_id'] in grouper.refer_mapping:
            if grouper.refer_mapping[call['call_id']] == call['refer_to']:
                print(f"  [OK] {call['call_id']} → {call['refer_to']}")
            else:
                print(f"  [FAIL] {call['call_id']} 매핑 오류")
                all_correct = False
        else:
            print(f"  [FAIL] {call['call_id']} 매핑 누락")
            all_correct = False
    
    if all_correct:
        print(f"  [OK] 모든 동시 콜 매핑이 정확함")
    else:
        print(f"  [FAIL] 일부 매핑에 오류 발생")
    
    # 절반 콜 종료
    print(f"3단계: 절반 콜 종료 테스트")
    calls_to_end = concurrent_calls[:5]  # 처음 5개 콜 종료
    
    for call in calls_to_end:
        grouper.clear_refer_mapping(call['call_id'])
    
    print(f"  5개 콜 종료 후 남은 매핑 수: {len(grouper.refer_mapping)}")
    
    # 남은 매핑 확인
    remaining_calls = concurrent_calls[5:]  # 나머지 5개 콜
    for call in remaining_calls:
        if call['call_id'] in grouper.refer_mapping:
            print(f"  [OK] {call['call_id']} 여전히 존재")
        else:
            print(f"  [FAIL] {call['call_id']} 잘못 정리됨")
    
    # 전체 정리
    print(f"4단계: 전체 매핑 정리")
    grouper.clear_refer_mapping()  # 전체 정리
    print(f"  전체 정리 후 매핑 수: {len(grouper.refer_mapping)}")

if __name__ == "__main__":
    try:
        test_multi_call_refer_scenario()
        test_concurrent_refer_operations()
        print("\n=== 모든 다중 콜 테스트 완료 ===")
        
    except Exception as e:
        print(f"테스트 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()