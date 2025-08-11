# -*- coding: utf-8 -*-
"""
PacketWave 유틸리티 헬퍼 함수들
"""

def is_extension(number):
    """내선번호인지 확인"""
    return len(str(number)) == 4 and str(number)[0] in '123456789'