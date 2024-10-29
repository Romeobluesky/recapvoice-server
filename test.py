import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel

class TestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Test Window')
        self.setGeometry(100, 100, 300, 200)
        self.label = QLabel('테스트', self)
        self.label.move(100, 80)

if __name__ == '__main__':
    try:
        app = QApplication(sys.argv)
        window = TestWindow()
        window.show()
        sys.exit(app.exec_())
    except Exception as e:
        print(f"Error: {str(e)}") 