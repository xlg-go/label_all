from typing import cast, Optional, List, Dict, Any
import html
from PyQt5 import QtCore
from PyQt5 import QtGui
from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPalette
from PyQt5.QtWidgets import QStyle, QTreeView, QHeaderView

from labelme.shape import Shape


# HTML渲染代理
class HTMLDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__()
        self.doc = QtGui.QTextDocument(self)

    def paint(self, painter, option, index):
        painter.save()

        options = QtWidgets.QStyleOptionViewItem(option)

        self.initStyleOption(options, index)
        self.doc.setHtml(options.text)
        options.text = ""

        style = (
            QtWidgets.QApplication.style()
            if options.widget is None
            else options.widget.style()
        )
        style.drawControl(QStyle.CE_ItemViewItem, options, painter)

        ctx = QtGui.QAbstractTextDocumentLayout.PaintContext()

        if option.state & QStyle.State_Selected:
            ctx.palette.setColor(
                QPalette.Text,
                option.palette.color(QPalette.Active, QPalette.HighlightedText),
            )
        else:
            ctx.palette.setColor(
                QPalette.Text,
                option.palette.color(QPalette.Active, QPalette.Text),
            )

        textRect = style.subElementRect(QStyle.SE_ItemViewItemText, options)

        if index.column() != 0:
            textRect.adjust(5, 0, 0, 0)

        margin = (option.rect.height() - options.fontMetrics.height()) // 2
        margin = margin - 4
        textRect.setTop(textRect.top() + margin)

        painter.translate(textRect.topLeft())
        painter.setClipRect(textRect.translated(-textRect.topLeft()))
        self.doc.documentLayout().draw(painter, ctx)

        painter.restore()

    def sizeHint(self, option, index):
        return QtCore.QSize(
            int(self.doc.idealWidth()),
            int(self.doc.size().height() - 4),
        )


# 嵌套标签树项
class NestedShapeTreeItem(QtGui.QStandardItem):
    def __init__(self, text=None, shape=None, parent_shape=None):
        super().__init__()
        self.setText(text or "")
        self.setShape(shape)
        self.parent_shape = parent_shape

        self.setCheckable(True)
        self.setCheckState(Qt.Checked)
        self.setEditable(False)
        self.setTextAlignment(Qt.AlignBottom)
        
    def updateDisplay(self):
        """更新显示内容"""
        if self.shape():
            # 设置第一列为 label_idx
            shape = self.shape()
            if shape.label and shape.idx is not None:
                label_text = f"{shape.label}_{shape.idx}"
            else:
                label_text = shape.label if shape.label else f"_{shape.idx}" if shape.idx is not None else ""
            
            self.setText(f'{html.escape(label_text)}')

    def clone(self):
        return NestedShapeTreeItem(self.text(), self.shape(), self.parent_shape)

    def setShape(self, shape):
        self.setData(shape, Qt.UserRole)

    def shape(self):
        return self.data(Qt.UserRole)

    def __hash__(self):
        return id(self)

    def __repr__(self):
        return f'{self.__class__.__name__}("{self.text()}")'


# 嵌套标签树模型
class NestedShapeTreeModel(QtGui.QStandardItemModel):
    itemDropped = QtCore.pyqtSignal()
    
    def __init__(self):
        super().__init__()
        self.setColumnCount(2)  # 第一列显示label_idx，第二列显示ocr_text
        self.setHorizontalHeaderLabels(["标签", "文本"])
        
    def removeRows(self, *args, **kwargs):
        ret = super().removeRows(*args, **kwargs)
        self.itemDropped.emit()
        return ret

    def dropMimeData(self, data, action, row: int, column: int, parent):
        if not parent.isValid():
            # 只允许在同一父节点下拖动
            return False
            
        # 如果row是-1，我们是在一个项目上放置（这会覆盖）
        # 相反，我们希望在它之后插入
        if row == -1 and parent.isValid():
            row = parent.row() + 1
            parent = parent.parent()

        # 如果仍然是-1，则附加到末尾
        if row == -1:
            row = self.rowCount(parent)

        result = super().dropMimeData(data, action, row, column, parent)
        
        if result:
            # 更新拖放后的idx
            self.updateShapeIndices(parent)
            
        return result
    
    def updateShapeIndices(self, parent):
        """更新指定父节点下所有子节点的idx"""
        if not parent.isValid():
            return
            
        parent_item = self.itemFromIndex(parent)
        if not hasattr(parent_item, 'shape'):
            return
            
        parent_shape = parent_item.shape()
        if parent_shape is None:
            return
            
        # 更新所有子shape的idx
        for i in range(self.rowCount(parent)):
            child_index = self.index(i, 0, parent)
            child_item = self.itemFromIndex(child_index)
            if hasattr(child_item, 'shape'):
                child_shape = child_item.shape()
                if child_shape:
                    child_shape.idx = i
                
        # 更新父shape的ocr_text
        parent_shape.updateOcrText()
        
        # 更新UI显示
        self.updateShapeDisplay(parent_item)
    
    def updateShapeDisplay(self, item):
        """更新Shape在UI中的显示"""
        if not hasattr(item, 'shape'):
            return
            
        shape = item.shape()
        if shape:
            # 更新第一列：label_idx
            label_text = html.escape(f"{shape.label}_{shape.idx}")
            r, g, b = shape.line_color.getRgb()[:3]
            item.setText(f'{label_text} <font color="#{r:02x}{g:02x}{b:02x}">●</font>')


# 嵌套标签树视图
class NestedShapeTreeWidget(QTreeView):
    itemDoubleClicked = QtCore.pyqtSignal(NestedShapeTreeItem)
    itemSelectionChanged = QtCore.pyqtSignal(list, list)
    itemChanged = QtCore.pyqtSignal(object)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._selectedItems = []

        self.setWindowFlags(Qt.Window)

        self._model = NestedShapeTreeModel()
        self.setModel(self._model)

        # 设置列宽
        self.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.header().setSectionResizeMode(1, QHeaderView.Stretch)
        
        # 设置代理
        self.setItemDelegate(HTMLDelegate())
        
        # 设置选择模式
        self.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.setUniformRowHeights(True)
        
        # 设置拖放
        self.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        
        # 启用排序
        self.setSortingEnabled(True)
        self.sortByColumn(0, Qt.AscendingOrder)  # 默认按第一列升序排序

        # 连接信号
        self.doubleClicked.connect(self.itemDoubleClickedEvent)
        self.selectionModel().selectionChanged.connect(self.itemSelectionChangedEvent)

    def itemSelectionChangedEvent(self, selected, deselected):
        selected = [self._model.itemFromIndex(i) for i in selected.indexes() if i.column() == 0]
        deselected = [self._model.itemFromIndex(i) for i in deselected.indexes() if i.column() == 0]
        self.itemSelectionChanged.emit(selected, deselected)

    def itemDoubleClickedEvent(self, index):
        if index.column() == 0:
            item = self._model.itemFromIndex(index)
            # 只有当item是NestedShapeTreeItem类型时才发送信号
            if hasattr(item, 'shape'):
                self.itemDoubleClicked.emit(item)

    def selectedItems(self):
        return [self._model.itemFromIndex(i) for i in self.selectedIndexes() if i.column() == 0]

    def scrollToItem(self, item):
        self.scrollTo(self._model.indexFromItem(item))

    def addShape(self, shape, parent_item=None):
        """添加Shape到树中"""
        # 创建标签项
        label_text = html.escape(f"{shape.label}_{shape.idx}")
        r, g, b = shape.line_color.getRgb()[:3]
        item = NestedShapeTreeItem(
            f'{label_text} <font color="#{r:02x}{g:02x}{b:02x}">●</font>', 
            shape,
            parent_item.shape() if parent_item else None
        )
        
        # 创建文本项
        ocr_item = QtGui.QStandardItem(shape.ocr_text or "")
        ocr_item.setEditable(False)
        
        # 添加到模型
        if parent_item:
            parent_item.appendRow([item, ocr_item])
        else:
            self._model.appendRow([item, ocr_item])
        
        # 递归添加子Shape
        for child_shape in shape.shapes:
            self.addShape(child_shape, item)
            
        return item

    def removeItem(self, item):
        """从树中移除项"""
        parent = item.parent()
        if parent:
            parent.removeRow(item.row())
        else:
            self._model.removeRow(item.row())
            
        # 如果有父Shape，更新父Shape的索引和ocr_text
        if item.parent_shape:
            # 更新所有兄弟Shape的idx
            siblings = item.parent_shape.shapes
            for i, s in enumerate(siblings):
                s.idx = i
            # 更新父Shape的ocr_text
            item.parent_shape.updateOcrText()
            
            # 更新UI显示
            for i in range(self._model.rowCount()):
                parent_item = self._model.item(i, 0)
                if parent_item and parent_item.shape() == item.parent_shape:
                    self._model.updateShapeDisplay(parent_item)
                    break

    def findItemByShape(self, shape, parent_index=None):
        """根据Shape查找项"""
        if parent_index is None:
            parent_index = QtCore.QModelIndex()
            
        for row in range(self._model.rowCount(parent_index)):
            index = self._model.index(row, 0, parent_index)
            item = self._model.itemFromIndex(index)
            
            if hasattr(item, 'shape') and item.shape() == shape:
                return item
                
            # 递归查找子项
            child_item = self.findItemByShape(shape, index)
            if child_item:
                return child_item
                
        return None

    def clear(self):
        """清空树"""
        self._model.clear()
        self._model.setColumnCount(2)
        self._model.setHorizontalHeaderLabels(["标签", "文本"])

    @property
    def itemDropped(self):
        return self._model.itemDropped
        
    def selectItem(self, item):
        """选择指定项目"""
        if item:
            index = self._model.indexFromItem(item)
            self.selectionModel().select(index, QtCore.QItemSelectionModel.ClearAndSelect | QtCore.QItemSelectionModel.Rows)