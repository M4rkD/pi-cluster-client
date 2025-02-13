from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *
import sys
from display.video_capture import VideoCaptureThread
from display.control_window import ControlWindow
from display.viewfinder import ViewfinderWindow
from controller import Controller

from settings import local_path


if __name__ == '__main__':
    app = QApplication(sys.argv)
    #app.setStyle(QStyleFactory.create("Fusion"))
    # initialise another thread for video capture

    video_source = VideoCaptureThread()

    controller = Controller()

    viewfinder = ViewfinderWindow(video_source)

    window = ControlWindow(controller, viewfinder, video_source)

    video_source.setParent(window)
    video_source.start()

    window.show()
    viewfinder.show()
    sys.exit(app.exec_())
