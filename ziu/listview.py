from ziu.qt import *


class ListView(QListView):
    filter_triggered = pyqtSignal(str)
    close_filter = pyqtSignal()

    def __init__(self, parent=None):
        super(ListView, self).__init__(parent)

    def keyPressEvent(self, event):
        text = event.text()
        if text.isalnum() or text in tuple('_-.'):
            self.filter_triggered.emit(text)            
        else:
            super(ListView, self).keyPressEvent(event)
