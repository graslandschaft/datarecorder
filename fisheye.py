#! /usr/bin/env python
__author__ = 'Joerg Henninger; joerg.henninger@posteo.de'

"""
TODO
- config dialogs for recording devices
    - set and indicate ROI
    - set framerate
- add info on resolution
- add tool to estimate frame write speed for a chose resoution
"""

debug = True

# ######################################################

import sys, os, time
import wave

from datetime import date, datetime, timedelta
import numpy as np
from PIL import Image as image
from PIL import ImageQt as iqt

try:
    from PyQt5 import QtGui, QtCore, QtWidgets
    from PyQt5.QtCore import Qt, pyqtSignal, pyqtSlot
except ImportError as details:
    print(details)
    sys.exit('Unfortunately, your system misses the PyQt5 packages.')

# from Base import Base
from AudioDisplay import AudioDisplay
from Control import Control
from VideoCanvas import VideoTab, VideoCanvas

# ######################################################


class Main(QtWidgets.QMainWindow):

    debug = debug

    width = 1000
    height = 100
    offset_left = 100
    offset_top = 30
    max_tab_width = 1000
    min_tab_width = 480

    # HANDLES
    idle_screen = False
    idle_toggable = True

    # create signals
    sig_idle_screen = pyqtSignal(object)

    def __init__( self, app, options=None, parent=None):
        QtCore.QObject.__init__(self, parent)
        self.app = app

        if os.name == 'posix':
            self.label_font_size = 18
        else:
            self.label_font_size = 12
        
        # #################
        # INITIATE
        self.control = Control(self, self.debug)

        # #################
        # LAYOUTS
        self.init_layout()

        self.setGeometry(self.offset_left, self.offset_top, self.width, self.height)
        self.setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Maximum)
        self.setMinimumSize(self.width, self.height)
        self.setWindowTitle(self.control.name)

        # for thread in self.control.threads:
        #     print thread

        # #################
        self.control.start_capture()

    def init_layout(self):
        # main
        self.main = QtWidgets.QWidget()
        self.setCentralWidget(self.main)
        self.main_layout = QtWidgets.QVBoxLayout()
        self.main.setLayout(self.main_layout)
        self.bottom_layout = QtWidgets.QHBoxLayout()
        self.bottom_info_layout = QtWidgets.QHBoxLayout()
        
        # self.create_menu_bar()

        # optional
        if self.control.cfg['video_input']:
            self.init_video_display()
        if self.control.cfg['audio_input']:
            self.init_audio_in_display()
        if self.control.cfg['audio_output']:
            self.init_audio_out_display()

        # add control: buttons and info
        self.init_control_layout()
        # create keyboard shortcuts
        self.create_actions()

    def init_audio_in_display(self):
        # AUDIO DISPLAY
        self.height += 200
        self.audio_layout = QtWidgets.QVBoxLayout()
        self.main_layout.addLayout(self.audio_layout)

        self.audio_disp = AudioDisplay(self, self.control.devices.audiodev, 'Audio Input', 
            samplerate=self.control.cfg['audio_input_samplerate'])
        self.audio_layout.addWidget(self.audio_disp)

    def init_audio_out_display(self):
        self.height += 200
        self.audioout_disp = AudioDisplay(self, self.control.devices.audiodevout, 'Audio Output', 
            playback=True)
        self.audio_layout.addWidget(self.audioout_disp)
        if self.control.options.audio_playback_list:
            self.control.exp_control.sig_exp_finished.connect(self.enable_start)
        elif self.control.options.audio_playback:
            self.control.devices.audiodevout.sig_playback_finished.connect(self.enable_start)

        self.setGeometry(self.offset_left, self.offset_top, self.width, self.height)
        self.setMinimumSize(self.width, self.height)

    def init_control_layout(self):
        self.main_layout.addLayout(self.bottom_layout)
        self.main_layout.addLayout(self.bottom_info_layout)

        # POPULATE BOTTOM LAYOUT
        self.button_record = QtWidgets.QPushButton('Start Recording')
        self.button_stop = QtWidgets.QPushButton('Stop')
        self.button_tag = QtWidgets.QPushButton('&Comment')
        self.button_idle = QtWidgets.QPushButton('Pause Display')

        self.button_stop.setDisabled(True)
        self.button_tag.setDisabled(True)

        self.button_record.setMinimumHeight(50)
        self.button_stop.setMinimumHeight(50)
        self.button_tag.setMinimumHeight(50)
        self.button_idle.setMinimumHeight(50)

        self.bottom_layout.addWidget(self.button_record)
        self.bottom_layout.addWidget(self.button_stop)
        self.bottom_layout.addWidget(self.button_tag)
        self.bottom_layout.addWidget(self.button_idle)

        self.label_time = QtWidgets.QLabel('', self)
        font = self.label_time.font()
        font.setPointSize(self.label_font_size)
        self.label_time.setFont(font)
        self.label_time.setText(self.control.default_label_text)
        self.control.sig_info_update.connect(self.update_info)

        self.bottom_info_layout.addStretch(0)
        self.bottom_info_layout.addWidget(self.label_time)
        self.bottom_info_layout.addStretch(0)

        # connect buttons
        self.button_record.clicked.connect(self.clicked_start)
        self.button_stop.clicked.connect(self.clicked_stop)
        self.button_tag.clicked.connect(self.clicked_comment)
        self.button_idle.clicked.connect(self.clicked_idle)
        

    def init_video_display(self):
        self.video_layout = QtWidgets.QHBoxLayout()
        self.main_layout.addLayout(self.video_layout)
        self.height += 500

        # POPULATE TOP LAYOUT
        self.videos = QtWidgets.QTabWidget()
        self.videos.setMinimumWidth(self.min_tab_width)
        self.videos.setMaximumWidth(self.max_tab_width)
        self.video_recordings = None
        self.video_tabs = {}
        self.video_layout.addWidget(self.videos)

        if len(self.control.devices.cameras) > 0:
            # create tabs for cameras
            for cam_name, cam in self.control.devices.cameras.items():
                self.video_tabs[cam_name] = VideoTab(self, cam_name)
                self.videos.addTab(self.video_tabs[cam_name], cam_name)

        else:
            self.videos.addTab(QtWidgets.QWidget(), "No camera found")

        # create timer for updating the video canvas
        self.canvastimer = QtCore.QTimer()
        self.canvastimer.timeout.connect(self.update_canvas)
        if len(self.control.devices.cameras):
            self.canvastimer.start(50)  # 20 Hz

    def create_menu_bar(self):
        self.statusBar()
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu('&File')
        file_menu.addAction(self.exit_action)
        help_menu = menu_bar.addMenu('&Help')

    # ACTIONS
    # Actions can be used to assign keyboard-shortcuts
    # This method is called in the __init__ method to create keyboard shortcuts
    def create_actions(self):
        # Create a start stop action for starts
        self.action_start_stop_delayed = QtWidgets.QAction('Start, stop recording',self)
        self.action_start_stop_delayed.setShortcut(Qt.Key_Space)
        self.action_start_stop_delayed.triggered.connect(self.start_stop)
        self.addAction(self.action_start_stop_delayed)

        # Create a Tag
        self.action_tag = QtWidgets.QAction('Comment recording',self)
        self.action_tag.setShortcut('Ctrl+T')
        self.action_tag.triggered.connect(self.clicked_comment)
        self.addAction(self.action_tag)

        # Change Tabs
        # self.action_change_tab_left = QtWidgets.QAction("Go one tab to the right", self)
        # self.action_change_tab_left.setShortcut(Qt.CTRL + Qt.Key_PageDown)
        # self.connect(self.action_change_tab_left, QtCore.SIGNAL('triggered()'), self.next_tab)
        # self.addAction(self.action_change_tab_left)

        # self.action_change_tab_right = QtWidgets.QAction("Go one tab to the left", self)
        # self.action_change_tab_right.setShortcut(Qt.CTRL + Qt.Key_PageUp)
        # self.connect(self.action_change_tab_right, QtCore.SIGNAL('triggered()'), self.prev_tab)
        # self.addAction(self.action_change_tab_right)

        # Exit
        self.exit_action = QtWidgets.QAction('&Exit', self)
        self.exit_action.setShortcut('Alt+Q')
        self.exit_action.triggered.connect(self.close)
        self.addAction(self.exit_action)

    def start_stop(self):
        """ for action """
        if self.debug > 0:
            print('start_stop called')
        if not self.button_record.isEnabled():
            self.clicked_stop()
        else:
            self.clicked_start()

    def clicked_start(self):
        self.disable_start()
        self.control.triggered_start()

    def clicked_stop(self):
        self.enable_start()
        self.control.triggered_stop()

    def enable_start(self):
        print('enabled start')
        self.button_record.setDisabled(False)
        self.button_stop.setDisabled(True)
        self.button_tag.setDisabled(True)

    def disable_start(self):
        print('disabled start')
        self.button_record.setDisabled(True)
        self.button_tag.setEnabled(True)
        self.button_stop.setDisabled(False)

    def clicked_comment(self):
        timestamp = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
        dlg =  QtWidgets.QInputDialog(self)
        dlg.setInputMode(QtWidgets.QInputDialog.TextInput)
        dlg.setLabelText('Comment on data:')                        
        dlg.setWindowTitle('Comment')
        dlg.resize(500,200)
        ok = dlg.exec_()  # shows the dialog
        s = u'{} \t {}'.format(timestamp, dlg.textValue())
        if ok:
            self.control.set_timestamp(s)

    def clicked_idle(self):
        if not self.idle_toggable: return
        if self.idle_screen:
            self.idle_screen = False
            self.button_idle.setText('Pause Display')
            self.sig_idle_screen.emit(False)
        else:
            self.idle_screen = True
            self.button_idle.setText('Continue Display')
            self.sig_idle_screen.emit(True)

    def next_tab(self):
        if self.tab.currentIndex() + 1 < self.tab.count():
            self.tab.setCurrentIndex(self.tab.currentIndex() + 1)
        else:
            self.tab.setCurrentIndex(0)

    def prev_tab(self):
        if self.tab.currentIndex() > 0:
            self.tab.setCurrentIndex(self.tab.currentIndex() - 1)
        else:
            self.tab.setCurrentIndex(self.tab.count() - 1)

    def update_info(self, label):
        self.label_time.setText(label)

    def closeEvent(self, event):
        self.control.stop_all_saving()
        QtCore.QThread.msleep(200)
        self.control.stop_all_capture()

        # finish threads
        for thread in self.control.threads:
            thread.quit()
        QtCore.QThread.msleep(200)
        print('See ya ...')
        self.app.quit()

    def update_canvas(self):
        # print('update canvas '+str(QtCore.QThread.currentThread()))
        # check for programmed stop-time
        if self.control.programmed_stop_dt is not None \
           and self.programmed_stop_dt < datetime.now():
            self.stop_all_recordings()
            # wait for recordings to stop
            self.wait(100)
            self.app.exit()

        # grab data from camera and display
        cam_name = str(self.videos.tabText(self.videos.currentIndex()))

        if not self.idle_screen:
            data = self.control.devices.cameras[cam_name].get_dispframe()  # grab current frame
            if data is None:
                return
            frame, dtime, fr = data
            self.video_tabs[cam_name].canvas.setImage(frame)
            
            self.last_framerate = fr
            self.video_tabs[cam_name].framerate_counter.setText('Framerate:\n{:.1f} Hz'.format(fr))

    def update_video_skipstep(self, val):
        self.mutex.lock()
        self.video_skipstep = val
        self.mutex.unlock()

# ######################################################
# ######################################################

if __name__=="__main__":
    qapp = QtWidgets.QApplication(sys.argv)  # create the main application
    main = Main(qapp)  # create the mainwindow instance
    main.show()  # show the mainwindow instance
    qapp.exec_()  # start the event-loop: no signals are sent or received without this.
