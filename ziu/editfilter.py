from ziu.qt import *


class EditFilter(QLineEdit):
    close_filter = pyqtSignal()

    def __init__(self, parent=None):
        super(EditFilter, self).__init__(parent)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close_filter.emit()
        else:
            return super(EditFilter, self).keyPressEvent(event)
