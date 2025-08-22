#설정 파일 로드 클래스
import configparser
import os

def load_config(config_path="settings.ini"):
    config = configparser.ConfigParser()
    
    # 절대 경로가 아니면 적절한 위치에서 찾기
    if not os.path.isabs(config_path):
        # 먼저 현재 디렉토리에서 확인
        if os.path.exists(config_path):
            config.read(config_path, encoding='utf-8')
            return config
        
        # 프로덕션 디렉토리에서 확인
        production_dir = os.path.join(os.environ.get('ProgramFiles(x86)', 'C:\\Program Files (x86)'), 'Recap Voice')
        production_path = os.path.join(production_dir, config_path)
        if os.path.exists(production_path):
            config.read(production_path, encoding='utf-8')
            return config
    
    # 기본 동작 (절대 경로이거나 파일을 찾지 못한 경우)
    config.read(config_path, encoding='utf-8')
    return config

def get_wireshark_path():
    config = load_config()
    return config.get('Wireshark', 'path', fallback=r'C:\Program Files\Wireshark')
