import sys
import ctypes
import os

def is_admin():
    """현재 프로세스가 관리자 권한으로 실행 중인지 확인"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def run_as_admin():
    """현재 스크립트를 관리자 권한으로 다시 실행"""
    if is_admin():
        # 이미 관리자 권한으로 실행 중
        return True
    else:
        # 관리자 권한으로 재실행
        try:
            ctypes.windll.shell32.ShellExecuteW(
                None,
                "runas",
                sys.executable,
                " ".join(sys.argv),
                None,
                1
            )
            return True
        except:
            return False

def request_admin_for_operation(operation_name):
    """특정 작업을 위해 관리자 권한 요청"""
    if not is_admin():
        import tkinter.messagebox as msgbox
        result = msgbox.askyesno(
            "관리자 권한 필요",
            f"{operation_name} 작업을 수행하려면 관리자 권한이 필요합니다.\n"
            f"관리자 권한으로 다시 시작하시겠습니까?"
        )
        if result:
            return run_as_admin()
        else:
            return False
    return True

def check_write_permission(path):
    """경로에 대한 쓰기 권한 확인"""
    try:
        test_file = os.path.join(path, 'test_write_permission.tmp')
        with open(test_file, 'w') as f:
            f.write('test')
        os.remove(test_file)
        return True
    except:
        return False