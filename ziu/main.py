import os
import sys
import subprocess
import traceback
import appdirs
import magic
import grpc
from collections import namedtuple
from operator import attrgetter
from send2trash import send2trash
from dieselhaze.db_util import db_connect
from dieselhaze.files import copyfile, copytree

#import uha_pb2
#import uha_pb2_grpc

from ziu.qt import *


rootdir = os.path.dirname(os.path.dirname(os.path.abspath(os.path.abspath(__file__))))
mw = None
datadir = appdirs.user_data_dir('ziu')
os.makedirs(datadir, exist_ok=True)
con = db_connect(os.path.join(datadir, 'ziu.db'))


def send_message():
    with grpc.insecure_channel('localhost:50051') as channel:
        stub = uha_pb2_grpc.UhaStub(channel)
        response = stub.SendMessage(uha_pb2.Message(message='you'))
    print("Greeter client received: " + response.message)


with con:
    con.cursor().execute(
        'create table if not exists openwith ('
        'id integer primary key,'
        'name text,'
        'ext text,'
        'cmd text,'
        'mime text,'
        'isdir integer'
    ')')

class LocationHistory:
    def __init__(self, initial_path):
        self._locations = [initial_path] 
        self._pos = 0

    @property
    def location(self):
        return self._locations[self._pos]

    @property
    def parent_enabled(self):
        return os.path.dirname(self.location) != self.location

    @property
    def back_enabled(self):
        if self._pos > 0:
            return True
        return False

    @property
    def forward_enabled(self):
        if self._pos < len(self._locations) - 1:
            return True
        return False

    def add(self, location):
        if location == self.location:
            return self.location

        self._locations = self._locations[:self._pos + 1]
        self._locations.append(location)
        self._pos = len(self._locations) - 1

        return self.location

    def back(self):
        self._pos = max(0, self._pos - 1)
        return self.location

    def forward(self):
        self._pos = min(len(self._locations) - 1, self._pos + 1)
        return self.location


folder_icon = QIcon(os.path.join(rootdir, 'pics/icons/tango/scalable/places/folder.svg'))
file_icon = QIcon(os.path.join(rootdir, 'pics/icons/tango/scalable/mimetypes/text-x-generic.svg'))


class FolderItem:
    def __init__(self, direntry):
        self.direntry = direntry
        self.path = direntry.path
        self.name = direntry.name

    @property
    def name_lower(self):
        return self.name.lower()

    @property
    def isdir(self):
        return self.direntry.is_dir(follow_symlinks=False)

    @property
    def icon(self):
        return folder_icon if self.isdir else file_icon

    @property
    def size(self):
        return self.direntry.stat(follow_symlinks=False).st_size


def get_folder_content(loc):
    try:
        for entry in os.scandir(loc):
            yield FolderItem(entry)
    except PermissionError:
        QMessageBox.critical(mw, 'Permission denied', 'Could not access location.')


def get_home():
    return os.path.expanduser('~')


class FolderModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super(FolderModel, self).__init__(parent)
        self.loc = None
        self.update()
        self.cols = ['']

    def update(self):
        self.layoutAboutToBeChanged.emit()
        if self.loc is None:
            self.items = []
        else:
            files = get_folder_content(self.loc)
            self.items = sorted(sorted(files, key=attrgetter('name_lower')),
                                key=attrgetter('isdir'), reverse=True)
        self.layoutChanged.emit()

    def rowCount(self, parent):
        return len(self.items)

    def columnCount(self, parent):
        return len(self.cols) 

    def data(self, index, role):
        item = self.items[index.row()]
        if role == Qt.DisplayRole:
            return item.name
        elif role == Qt.DecorationRole:
            return item.icon
        return QVariant()

    def headerData(self, section, orientation, role):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.cols[section]
        return QVariant()

    def set_location(self, loc):
        self.loc = loc
        self.update()

    def get_item(self, index):
        return self.items[index.row()]


class OpenWithDialog(QDialog):
    def __init__(self, parent):
        super(OpenWithDialog, self).__init__(parent)
        self.ui = loadUi('designer/openwith.ui', self)
        self.enable_ok(False)
        self.ui.openwith_cmd_edit.textChanged.connect(self.cmd_changed)

    def enable_ok(self, enable):
        self.ui.buttonBox.button(QDialogButtonBox.Ok).setEnabled(enable)

    def cmd_changed(self, value):
        if value:
            self.enable_ok(True)
        else:
            self.enable_ok(False)


class RenameDialog(QDialog):
    def __init__(self, parent, current_name):
        super(RenameDialog, self).__init__(parent)
        self.ui = loadUi('designer/rename.ui', self)
        self.enable_ok(False)
        self.ui.rename_edit.setText(current_name)
        self.ui.rename_edit.selectAll()
        self.ui.rename_edit.textChanged.connect(self.name_changed)

    def enable_ok(self, enable):
        self.ui.buttonBox.button(QDialogButtonBox.Ok).setEnabled(enable)

    def name_changed(self, value):
        if value:
            self.enable_ok(True)
        else:
            self.enable_ok(False)


class NewFolderDialog(QDialog):
    def __init__(self, parent):
        super(NewFolderDialog, self).__init__(parent)
        self.ui = loadUi('designer/newfolder.ui', self)
        self.enable_ok(False)
        self.ui.name_edit.textChanged.connect(self.name_changed)

    def enable_ok(self, enable):
        self.ui.buttonBox.button(QDialogButtonBox.Ok).setEnabled(enable)

    def name_changed(self, value):
        if value:
            self.enable_ok(True)
        else:
            self.enable_ok(False)


class MainWindow(QMainWindow):
    icon_sizes = [QSize(16, 16), QSize(32, 32), QSize(48, 48), QSize(64, 64),
                  QSize(80, 80), QSize(96, 96)]
    default_icon_size = QSize(48, 48)

    def __init__(self, *args):
        super(MainWindow, self).__init__(*args)
        self.ui = loadUi('designer/main.ui', self)
        self.setup_ui()

        self.foldermodel = FolderModel()
        self.ui.listView.setModel(self.foldermodel)
    
        self.history = LocationHistory(get_home())
        self.set_location(self.history.location)

    def setup_ui(self):
        self.ui.locationEdit = QLineEdit()
        self.ui.locationEdit.returnPressed.connect(self.go_location)
        self.ui.toolBar.insertWidget(self.ui.actionGoLocation, self.ui.locationEdit)

        self.ui.actionGoParent.triggered.connect(self.go_parent)
        self.ui.actionGoParent.setShortcuts(['Alt+Up', 'Backspace'])

        self.ui.actionGoHome.triggered.connect(self.go_home)
        self.ui.actionGoLocation.triggered.connect(self.go_location)
        self.ui.actionGoBack.triggered.connect(self.go_back)
        self.ui.actionGoForward.triggered.connect(self.go_forward)
        self.ui.action_Restart.triggered.connect(self.restart)
        self.ui.actionZoomIn.triggered.connect(self.zoom_in)
        self.ui.actionZoomOut.triggered.connect(self.zoom_out)
        self.ui.actionNormalSize.triggered.connect(self.normal_size)
        self.ui.actionAbout.triggered.connect(self.about)
        self.ui.actionOpenWith.triggered.connect(self.open_with_triggered)

        QShortcut(QKeySequence('Ctrl+L'), self, self.edit_location)
        QShortcut(QKeySequence('Return'), self, self.enter_pressed)
        QShortcut(QKeySequence('Enter'), self, self.enter_pressed)
        QShortcut(QKeySequence('Del'), self, self.del_pressed)
        QShortcut(QKeySequence('F2'), self, self.f2_pressed)
        QShortcut(QKeySequence('F4'), self, self.f4_pressed)
        QShortcut(QKeySequence('F5'), self, self.f5_pressed)
        QShortcut(QKeySequence('Ctrl+W'), self, QApplication.quit)
        QShortcut(QKeySequence('Ctrl+C'), self, self.to_clipboard)
        QShortcut(QKeySequence('Ctrl+V'), self, self.from_clipboard)
        QShortcut(QKeySequence('Ctrl+Shift+N'), self, self.create_folder)

        self.ui.listView.doubleClicked.connect(self.open_selected)
        self.ui.listView.filter_triggered.connect(self.filter_triggered)
        self.ui.listView.customContextMenuRequested.connect(self.listview_contextmenu_requested)

        self.current_icon_size = self.default_icon_size

        self.ui.edit_filter.setVisible(False)
        self.ui.edit_filter.close_filter.connect(self.close_filter)
        self.ui.edit_filter.textChanged.connect(self.filter_changed)

    def listview_contextmenu_requested(self, pos):
        globalpos = self.ui.listView.mapToGlobal(pos)
        index = self.ui.listView.indexAt(pos)
        item = self.ui.listView.model().get_item(index)
        _, ext = os.path.splitext(item.path)
        if index.row() != -1:
            menu = QMenu()
            openwith_menu = menu.addMenu('Open with')
            if item.isdir:
                apps = con.cursor().execute('select * from openwith where isdir = 1')
            elif ext:
                apps = con.cursor().execute('select * from openwith where ext = ?', (ext,))
            else:
                mime = magic.from_file(item.path)
                apps = con.cursor().execute('select * from openwith where mime = ?', (mime,))
            apps = apps.fetchall()
            app = None
            for app in apps:
                action = QAction(app['name'], self)
                action.triggered.connect(lambda: self.open_file_custom(app['cmd'], item.path))
                openwith_menu.addAction(action)

            if app is not None:
                openwith_menu.addSeparator()
                
            self.ui.actionOpenWith.setData(index)
            openwith_menu.addAction(self.ui.actionOpenWith)

            menu.exec_(globalpos)

    def create_folder(self):
        dialog = NewFolderDialog(self)

        if dialog.exec_():
            name = dialog.name_edit.text()
            path = os.path.join(self.current_location(), name)
            try:
                os.makedirs(path)
            except:
                QMessageBox.critical(self, 'Error creating folder', traceback.format_exc())
            else:
                self.reload_folder()

    def to_clipboard(self):
        indexes = self.ui.listView.selectionModel().selectedIndexes()
        if indexes:
            data = QMimeData()
            data.setUrls([QUrl.fromLocalFile(self.ui.listView.model().get_item(x).path)
                for x in indexes])
            QApplication.clipboard().setMimeData(data)

    def from_clipboard(self):
        """Paste files from clipboard.

        Should
            - ask if dst is file and exists
            - copy content from src dir to dst dir if dst is dir and exists
            - recursively apply these rules
        """
        for url in QApplication.clipboard().mimeData().urls():
            src = url.path()
            dst = os.path.join(self.current_location(), os.path.basename(src))
            try:
                if os.path.isdir(src):
                    copytree(src, dst)
                else:
                    copyfile(src, dst)
            except:
                QMessageBox.critical(self, 'Error copying file/dir', traceback.format_exc())

    def open_with_triggered(self):
        dialog = OpenWithDialog(self)
        if dialog.exec_():
            index = self.sender().data()
            item = self.ui.listView.model().get_item(index)
            cmd = dialog.openwith_cmd_edit.text()
            self.open_file_custom(cmd, item.path)
            name = dialog.openwith_name_edit.text()
            if name:
                _, ext = os.path.splitext(item.path)
                mime = None if item.isdir else magic.from_file(item.path)
                with con:
                    con.cursor().execute('insert into openwith (name, ext, cmd, mime, isdir) values (?, ?, ?, ?, ?)',
                        (name, ext, cmd, mime, item.isdir))

    def filter_triggered(self, text):
        self.edit_filter.setText(text)
        self.edit_filter.setVisible(True)
        self.edit_filter.setFocus()

    def close_filter(self):
        self.edit_filter.setText('')
        self.edit_filter.setVisible(False)
        self.listView.setFocus()

    def filter_changed(self, value):
        self.listView.selectionModel().clearSelection()
        if not value:
            return
        rows = [x[0] for x in enumerate(self.foldermodel.items) if x[1].name_lower.startswith(value.lower())]
        if rows:
            index = self.foldermodel.index(rows[0], 0)
            self.listView.selectionModel().select(index, QItemSelectionModel.Select)
            self.listView.scrollTo(index, QAbstractItemView.EnsureVisible)

    def edit_location(self):
        self.ui.locationEdit.selectAll()
        self.ui.locationEdit.setFocus()

    def open_file_custom(self, cmd, path):
        try:
            subprocess.Popen([cmd, path])
        except:
            QMessageBox.critical(self, 'Error opening file', traceback.format_exc())

    def open_file(self, path):
        QDesktopServices.openUrl(QUrl(path))

    def open_selected(self, index):
        item = self.ui.listView.model().get_item(index)
        if item.isdir:
            self.set_location(self.history.add(item.path))
        else:
            self.open_file(item.path)

    def enter_pressed(self):
        indexes = self.ui.listView.selectionModel().selectedIndexes()
        if len(indexes) == 1:
            self.open_selected(indexes[0])
            self.close_filter()
        elif len(indexes) > 1:
            items = [self.ui.listView.model().get_item(x) for x in indexes]
            if not any(x.isdir for x in items):
                for item in items:
                    self.open_file(item.path)

    def del_pressed(self):
        index = None
        for index in self.ui.listView.selectionModel().selectedIndexes():
            item = self.ui.listView.model().get_item(index)
            send2trash(item.path)
        if index is not None:
            self.reload_folder()

    def f2_pressed(self):
        indexes = self.ui.listView.selectionModel().selectedIndexes()
        if len(indexes) == 1:
            item = self.ui.listView.model().get_item(indexes[0])
            dialog = RenameDialog(self, item.name)

            if dialog.exec_():
                new_name = dialog.rename_edit.text()
                path = os.path.join(os.path.dirname(item.path), new_name)

                # This is a race condition but it will have to do for now
                if os.path.exists(path):
                    QMessageBox.critical(self, '', 'File/directory exists')
                else:
                    os.rename(item.path, path)
                    self.reload_folder()

    def f4_pressed(self):
        subprocess.Popen(['xfce4-terminal', '--working-directory', self.current_location()])

    def f5_pressed(self):
        self.reload_folder()

    def reload_folder(self):
        self.foldermodel.update()
        self.ui.listView.clearSelection()

    def update_icon_size(self):
        self.ui.listView.setIconSize(self.current_icon_size)

    def apply_location(self):
        loc = self.current_location()

        self.close_filter()
        self.ui.listView.clearSelection()

        self.ui.actionGoBack.setEnabled(self.history.back_enabled)
        self.ui.actionGoForward.setEnabled(self.history.forward_enabled)
        self.ui.actionGoParent.setEnabled(self.history.parent_enabled)

        self.foldermodel.set_location(loc)

        self.watch_folder = QFileSystemWatcher([loc])
        self.watch_folder.directoryChanged.connect(self.reload_folder)

    def set_location(self, path):
        self.ui.locationEdit.setText(path)
        self.apply_location()

    def current_location(self):
        return self.ui.locationEdit.text()

    def go_location(self):
        if not os.path.isdir(self.current_location()):
            QMessageBox.critical(self, '', 'Invalid directory')
            return
        self.apply_location()
        self.ui.listView.setFocus()

    def go_home(self):
        self.set_location(self.history.add(get_home()))

    def go_back(self):
        self.set_location(self.history.back())

    def go_forward(self):
        self.set_location(self.history.forward())
    
    def go_parent(self):
        self.set_location(self.history.add(os.path.dirname(self.current_location())))

    def zoom_in(self):
        self.current_icon_size = self.icon_sizes[min(len(self.icon_sizes)-1, self.icon_sizes.index(self.current_icon_size)+1)]
        self.update_icon_size()

    def zoom_out(self):
        self.current_icon_size = self.icon_sizes[max(0, self.icon_sizes.index(self.current_icon_size)-1)]
        self.update_icon_size()

    def normal_size(self):
        self.current_icon_size = self.default_icon_size
        self.update_icon_size()

    def restart(self):
        print('Restarting...')
        os.execv('runziu', sys.argv)

    def about(self):
        QMessageBox.about(self, 'About ziu', 
        f"""
        <b>ziu</b>
        <p>File manager</p>
        <p></p>
        <p><table border="0" width="150">
        <tr>
        <td>Author:</td>
        <td>Kris Fris</td>
        </tr>
        <tr>
        <td>Version:</td>
        <td>0.1.0</td>
        </tr>
        <tr>
        <td>Date:</td>
        <td>2018</td>
        </tr>                        
        </table></p>
        """)


def _run():
    print('qt version: ', QT_VERSION_STR)
    print('pyqt version: ', PYQT_VERSION_STR)
    global mw

    app = QApplication(sys.argv)
    app.setApplicationName('ziu')
    app.setOrganizationName('krisfris')
    app.setOrganizationDomain('krisfris.com')
    app.setStyleSheet(open(os.path.join(rootdir, 'qss/stylesheet.qss')).read())

    mw = MainWindow()
    mw.resize(900, 600)
    mw.setWindowIcon(QIcon(os.path.join(rootdir, 'pics/icon.png')))
    mw.show()

    r = app.exec_()
    app.deleteLater()
    sys.exit(r)


def run():
    try:
        _run()
    except Exception as e:
        QMessageBox.critical(None, "Startup Error",
                             "Please notify support of this error:\n\n"+
                             traceback.format_exc())


if __name__ == '__main__':
    run()
