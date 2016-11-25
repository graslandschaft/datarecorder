from PIL import Image as image
import numpy as np
from PIL import ImageQt as iqt
try:
    from PyQt4 import QtGui, QtCore, Qt
except Exception, details:
    print 'Unfortunately, your system misses the PyQt4 packages.'
    quit()


class VideoTab(QtGui.QWidget):
    """This class creates the a Tab for Camera data"""
    def __init__(self, parent=None):
        QtGui.QLabel.__init__(self, parent)
        self.setAlignment(Qt.Qt.AlignVCenter | Qt.Qt.AlignHCenter)
        self.setSizePolicy(Qt.QSizePolicy.Maximum, Qt.QSizePolicy.Maximum)
        self.setFrameStyle(Qt.QFrame.Panel | Qt.QFrame.Sunken)

        


class VideoCanvas(QtGui.QLabel):
    """This class creates the video-canvas-widget in the mainwindow by subclassing the QLabel-Widget"""
    def __init__(self, parent=None):
        QtGui.QLabel.__init__(self, parent)
        self.setAlignment(Qt.Qt.AlignVCenter | Qt.Qt.AlignHCenter)
        self.setSizePolicy(Qt.QSizePolicy.Maximum, Qt.QSizePolicy.Maximum)
        # self.setSizePolicy(Qt.QSizePolicy.Expanding, Qt.QSizePolicy.Expanding)
        self.setFrameStyle(Qt.QFrame.Panel | Qt.QFrame.Sunken)

        self.canvas_w = 950
        self.canvas_h = 534
        # img = image.fromarray(np.zeros((self.canvas_h, self.canvas_w))).convert('RGB')
        # self.setImage(QtGui.QPixmap.fromImage(iqt.ImageQt(img)))

    def setImage(self, pixmap):
        self.pixmap = pixmap
        self.setPixmap(self.pixmap.scaled(self.size(), Qt.Qt.KeepAspectRatio))

    # def resizeEvent(self, QResizeEvent):
    #     """ override in-built Qt function """
    #     self.resizeImage()

    # def resizeImage(self):
    #     self.setPixmap(self.pixmap.scaled(self.size(), Qt.Qt.KeepAspectRatio))
