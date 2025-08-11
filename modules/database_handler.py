# -*- coding: utf-8 -*-
"""
데이터베이스 처리 모듈
Dashboard 클래스에서 MongoDB 관련 기능을 분리
"""

import datetime
import os
import re
from pymongo import MongoClient
from pydub import AudioSegment
from config_loader import load_config
from utils.helpers import is_extension


class DatabaseHandler:
    """데이터베이스 관련 유틸리티 함수들"""
    
    def __init__(self, dashboard_instance):
        self.dashboard = dashboard_instance
        self.mongo_client = None
        self.db = None
        self.members = None
        self.filesinfo = None
        self.internalnumber = None
    
    def retry_mongodb_connection(self):
        """MongoDB 재연결 시도"""
        try:
            # MongoDB 설정 읽기
            config = load_config()
            mongo_host = config.get('MongoDB', 'host', fallback='localhost')
            mongo_port = config.getint('MongoDB', 'port', fallback=27017)
            mongo_database = config.get('MongoDB', 'database', fallback='packetwave')
            mongo_username = config.get('MongoDB', 'username', fallback='')
            mongo_password = config.get('MongoDB', 'password', fallback='')

            # MongoDB 연결 문자열 생성
            if mongo_username and mongo_password:
                mongo_uri = f"mongodb://{mongo_username}:{mongo_password}@{mongo_host}:{mongo_port}/"
            else:
                mongo_uri = f"mongodb://{mongo_host}:{mongo_port}/"

            # 짧은 타임아웃으로 연결 시도
            self.mongo_client = MongoClient(
                mongo_uri,
                serverSelectionTimeoutMS=3000,  # 3초 타임아웃
                connectTimeoutMS=3000,
                socketTimeoutMS=3000
            )
            self.db = self.mongo_client[mongo_database]
            self.members = self.db['members']
            self.filesinfo = self.db['filesinfo']
            self.internalnumber = self.db['internalnumber']

            # 연결 테스트
            self.mongo_client.admin.command('ping')
            self.dashboard.log_error("MongoDB 연결 성공", level="info")
            
            # Dashboard 인스턴스에도 참조 설정
            self.dashboard.mongo_client = self.mongo_client
            self.dashboard.db = self.db
            self.dashboard.members = self.members
            self.dashboard.filesinfo = self.filesinfo
            self.dashboard.internalnumber = self.internalnumber

        except Exception as e:
            # 재시도도 실패한 경우에만 로그 기록
            self.dashboard.log_error("MongoDB 연결 최종 실패", e)
            # 연결이 계속 실패하면 MongoDB 없이 동작
            self.mongo_client = None
            self.db = None
            self.members = None
            self.filesinfo = None
            self.internalnumber = None
            
            # Dashboard 인스턴스도 None으로 설정
            self.dashboard.mongo_client = None
            self.dashboard.db = None
            self.dashboard.members = None
            self.dashboard.filesinfo = None
            self.dashboard.internalnumber = None

    def save_to_mongodb(self, merged_file, html_file, local_num, remote_num, call_id, packet):
        """MongoDB에 파일 정보 저장"""
        try:
            if not self.filesinfo:
                self.dashboard.log_error("MongoDB 연결이 없어 저장을 건너뜁니다", level="warning")
                return

            max_id_doc = self.filesinfo.find_one(sort=[("id", -1)])
            next_id = 1 if max_id_doc is None else max_id_doc["id"] + 1
            now_kst = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
            audio = AudioSegment.from_wav(merged_file)
            duration_seconds = int(len(audio) / 1000.0)
            hours = duration_seconds // 3600
            minutes = (duration_seconds % 3600) // 60
            seconds = duration_seconds % 60
            duration_formatted = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            filesize = os.path.getsize(merged_file)

            # per_lv8, per_lv9 값 가져오기
            per_lv8 = ""
            per_lv9 = ""
            per_lv8_update = ""
            per_lv9_update = ""

            if packet and hasattr(packet, 'sip'):
                sip_layer = packet.sip
                # 통화 유형에 따른 권한 설정
                # 내선 간 통화인 경우
                if is_extension(local_num) and is_extension(remote_num):
                    if hasattr(sip_layer, 'method') and sip_layer.method == 'INVITE':
                        if hasattr(sip_layer, 'msg_hdr'):
                            msg_hdr = sip_layer.msg_hdr

                            # X-xfer-pressed: True 찾기
                            if 'X-xfer-pressed: True' in msg_hdr:
                                # 내선 -> 내선 통화일때 데이타베이스 수신내선,발신내선,파일명 같은 데이타 찾기
                                file_path_str = merged_file
                                file_name_str = os.path.basename(file_path_str)
                                # wav 파일명만 추출
                                fileinfo_doc = self.filesinfo.find_one({
                                    "from_number": local_num, 
                                    "to_number": remote_num, 
                                    "filename": {"$regex": file_name_str}
                                })

                                if fileinfo_doc:
                                    member_doc_update = self.members.find_one({"extension_num": local_num})
                                    if member_doc_update:
                                        per_lv8_update = member_doc_update.get('per_lv8', '')
                                        per_lv9_update = member_doc_update.get('per_lv9', '')

                                        result = self.filesinfo.update_one(
                                            {"from_number": local_num, "to_number": remote_num, "filename": {"$regex": file_name_str}}, 
                                            {"$set": {"per_lv8": per_lv8_update, "per_lv9": per_lv9_update}}
                                        )

                                    member_doc = self.members.find_one({"extension_num": remote_num})
                                    if member_doc:
                                        if member_doc_update:
                                            per_lv8 = member_doc.get('per_lv8', '')
                                            per_lv9 = member_doc.get('per_lv9', '')

                                    # 로깅 추가
                                    self.dashboard.log_error("SIP 메시지 헤더 확인3", level="info", additional_info={
                                        "msg_hdr": msg_hdr,
                                        "from_number": local_num,
                                        "to_number": remote_num,
                                        "filename": {"$regex": file_name_str},
                                        "per_lv8_update": per_lv8_update,
                                        "per_lv9_update": per_lv9_update,
                                        "per_lv8": per_lv8,
                                        "per_lv9": per_lv9
                                    })

                elif is_extension(remote_num) and not is_extension(local_num):
                    # 외부 -> 내선 통화
                    if hasattr(sip_layer, 'method') and sip_layer.method == 'REFER':
                        # 외부에서 온 전화를 돌려주기
                        if len(sip_layer.from_user) > 4 and len(sip_layer.from_user) < 9:
                            local_num_str = re.split(r'[a-zA-Z]+', sip_layer.from_user)
                            remote_num_str = re.split(r'[a-zA-Z]+', sip_layer.to_user)

                            if hasattr(sip_layer, 'msg_hdr'):
                                msg_hdr = sip_layer.msg_hdr

                                member_doc = self.members.find_one({"extension_num": remote_num_str})
                                if member_doc:
                                    per_lv8 = member_doc.get('per_lv8', '')
                                    per_lv9 = member_doc.get('per_lv9', '')
                                    local_num = local_num_str
                                    remote_num = remote_num_str
                            # 로깅 추가
                            self.dashboard.log_error("SIP 메시지 헤더 확인4", level="info", additional_info={
                                "msg_hdr": msg_hdr,
                                "from_number": local_num,
                                "to_number": remote_num,
                                "per_lv8": per_lv8,
                                "per_lv9": per_lv9
                            })
                    else:
                        member_doc = self.members.find_one({"extension_num": remote_num})
                        if member_doc:
                            per_lv8 = member_doc.get('per_lv8', '')
                            per_lv9 = member_doc.get('per_lv9', '')

                elif is_extension(local_num) and not is_extension(remote_num):
                    if hasattr(sip_layer, 'method') and sip_layer.method == 'REFER':
                        # 내선 -> 외부 통화
                        if len(sip_layer.to_user) > 9 and len(sip_layer.to_user) < 12:
                            local_num_str = re.split(r'[a-zA-Z]+', sip_layer.from_user)
                            remote_num_str = re.split(r'[a-zA-Z]+', sip_layer.to_user)

                            if hasattr(sip_layer, 'msg_hdr'):
                                msg_hdr = sip_layer.msg_hdr

                                member_doc = self.members.find_one({"extension_num": local_num_str})
                                if member_doc:
                                    per_lv8 = member_doc.get('per_lv8', '')
                                    per_lv9 = member_doc.get('per_lv9', '')
                                    local_num = local_num_str
                                    remote_num = remote_num_str
                    else:
                        member_doc = self.members.find_one({"extension_num": local_num})
                        if member_doc:
                            per_lv8 = member_doc.get('per_lv8', '')
                            per_lv9 = member_doc.get('per_lv9', '')

            # 파일 정보 문서 생성
            file_doc = {
                "id": next_id,
                "filename": os.path.basename(merged_file),
                "filepath": merged_file,
                "htmlpath": html_file,
                "from_number": local_num,
                "to_number": remote_num,
                "call_id": call_id,
                "duration": duration_formatted,
                "filesize": filesize,
                "created_at": now_kst,
                "per_lv8": per_lv8,
                "per_lv9": per_lv9
            }

            # MongoDB에 삽입
            result = self.filesinfo.insert_one(file_doc)
            self.dashboard.log_error("MongoDB 파일 정보 저장 완료", level="info", additional_info={
                "id": next_id,
                "filename": os.path.basename(merged_file),
                "from_number": local_num,
                "to_number": remote_num,
                "duration": duration_formatted
            })

        except Exception as e:
            self.dashboard.log_error("MongoDB 저장 중 오류", e)

    def cleanup(self):
        """데이터베이스 연결 정리"""
        try:
            if self.mongo_client:
                self.mongo_client.close()
                self.mongo_client = None
                self.db = None
                self.members = None
                self.filesinfo = None
                self.internalnumber = None
        except Exception as e:
            self.dashboard.log_error("MongoDB 연결 정리 중 오류", e)