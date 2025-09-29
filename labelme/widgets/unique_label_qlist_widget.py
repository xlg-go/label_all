import html
from typing import Optional

from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt

from .label_list_widget import HTMLDelegate


class _EscapableQListWidget(QtWidgets.QListWidget):
    def keyPressEvent(self, event):
        super().keyPressEvent(event)
        if event.key() == Qt.Key_Escape:
            self.clearSelection()


class UniqueLabelQListWidget(_EscapableQListWidget):
    def __init__(self, get_rgb_by_label=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setItemDelegate(HTMLDelegate(parent=self))
        self.get_rgb_by_label = get_rgb_by_label

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if not self.indexAt(event.pos()).isValid():
            self.clearSelection()

    def find_label_item(self, label: str) -> Optional[QtWidgets.QListWidgetItem]:
        for row in range(self.count()):
            item = self.item(row)
            if item and item.data(Qt.UserRole) == label:
                return item
        return None

    def add_label_item(self, label: str) -> None:
        if self.find_label_item(label):
            raise ValueError(f"Item for label '{label}' already exists")

        item = QtWidgets.QListWidgetItem()
        item.setData(Qt.UserRole, label)  # for find_label_item

        r, g, b = self.get_rgb_by_label(label)
        item.setText(
            f"{html.escape(label)} "
            f"<font color='#{r:02x}{g:02x}{b:02x}'>●</font>"
        )
        self.addItem(item)
