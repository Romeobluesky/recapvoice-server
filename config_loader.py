#설정 파일 로드 클래스
import configparser

def load_config(config_path="settings.ini"):
    config = configparser.ConfigParser()
    config.read(config_path)
    return config

def get_wireshark_path():
    config = load_config()
    return config.get('Wireshark', 'path', fallback=r'C:\Program Files\Wireshark')
