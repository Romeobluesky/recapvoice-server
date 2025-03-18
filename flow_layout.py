from PySide6.QtWidgets import QLayout
from PySide6.QtCore import QSize, QRect, QPoint
from PySide6.QtCore import Qt

class FlowLayout(QLayout):
		def __init__(self, parent=None, margin=0, spacing=-1):
				super().__init__(parent)
				self._items = []
				self.setContentsMargins(margin, margin, margin, margin)
				self.setSpacing(spacing)

		def addItem(self, item):
				self._items.append(item)

		def count(self):
				return len(self._items)

		def itemAt(self, index):
				if 0 <= index < len(self._items):
						return self._items[index]
				return None

		def takeAt(self, index):
				if 0 <= index < len(self._items):
						return self._items.pop(index)
				return None

		def expandingDirections(self):
				return Qt.Orientations()

		def hasHeightForWidth(self):
				return True

		def heightForWidth(self, width):
				height = self._doLayout(QRect(0, 0, width, 0), True)
				return height

		def setGeometry(self, rect):
				super().setGeometry(rect)
				self._doLayout(rect, False)

		def sizeHint(self):
				return self.minimumSize()

		def minimumSize(self):
				size = QSize()
				for item in self._items:
						size = size.expandedTo(item.minimumSize())
				margin = self.contentsMargins()
				size += QSize(2 * margin.top(), 2 * margin.bottom())
				return size

		def _doLayout(self, rect, testOnly):
				x = rect.x()
				y = rect.y()
				lineHeight = 0
				spacing = self.spacing()
				for item in self._items:
						widget = item.widget()
						spaceX = spacing
						spaceY = spacing
						nextX = x + item.sizeHint().width() + spaceX
						if nextX - spaceX > rect.right() and lineHeight > 0:
								x = rect.x()
								y = y + lineHeight + spaceY
								nextX = x + item.sizeHint().width() + spaceX
								lineHeight = 0
						if not testOnly:
								item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))
						x = nextX
						lineHeight = max(lineHeight, item.sizeHint().height())
				return y + lineHeight - rect.y()