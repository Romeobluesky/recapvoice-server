from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QPen, QColor
from PySide6.QtCore import QTimer, Qt

class PacketFlowWidget(QWidget):
		def __init__(self):
				super().__init__()
				self.setMinimumHeight(100)
				self.packets = []
				self.timer = QTimer(self)
				self.timer.timeout.connect(self.update)
				self.timer.start(1000)

		def paintEvent(self, event):
				painter = QPainter(self)
				painter.setRenderHint(QPainter.Antialiasing)
				painter.fillRect(self.rect(), QColor("#2d2d2d"))
				y_offset = 10
				for packet in self.packets:
						if y_offset >= self.height() - 10:
								break
						painter.setPen(Qt.white)
						painter.drawText(10, y_offset + 15, packet["time"])
						painter.setPen(QPen(QColor("#18508F"), 2))
						painter.drawLine(200, y_offset + 15, self.width() - 200, y_offset + 15)
						painter.setPen(Qt.white)
						painter.drawText(self.width() // 2 - 50, y_offset + 10, packet["type"])
						y_offset += 30
