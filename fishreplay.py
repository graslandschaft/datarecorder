#! /usr/bin/env python3

"""
TODO
- control center for stimulus und recording control
- output devices: audio, later video

- config dialogs for recording devices
"""

# ######################################################

import sys, os, time
import wave
from optparse import OptionParser
from datetime import date, datetime, timedelta
import numpy as np

from AudioDev import AudioDev
from AudioDisplay import AudioDisplay

try:
    from PyQt4 import QtGui, QtCore, Qt
except Exception, details:
    print 'Unfortunately, your system misses the PyQt4 packages.'
    quit()

# ######################################################

width, height = 1000, 400
offset_left, offset_top = 100, 100
max_tab_width, min_tab_width = 1000, 400


class Main(QtGui.QMainWindow):
    def __init__( self, app, options=None, parent=None):
        QtCore.QObject.__init__(self, parent)
        self.app = app
        self.name = 'fishear'

        self.setGeometry(offset_left, offset_top, width, height)
        self.setSizePolicy(Qt.QSizePolicy.Maximum, Qt.QSizePolicy.Maximum)
        self.setMinimumSize(width, height)
        self.setWindowTitle('FishEar')

        # #################

        # HANDLES
        self.idle_screen = False
        self.instant_start = False
        self.starttime = None
        self.saving = False
        self.working_dir = os.path.abspath(os.path.curdir)
        self.save_dir = None
        self.start_delay = 10
        self.rec_info = dict(rec_info='',
                             rec_start='',
                             rec_end='',
                             comments=list())
        
        self.use_hydro = False

        ############
        self.debug = 0
        ############

        if os.name == 'posix':
            self.label_font_size = 18
        else:
            self.label_font_size = 10

        # #################

        # time related variables
        self.recording_restart_time = 0
        self.restart_times = np.arange(3, 25, 3)  # in hours
        self.restart_dts = list()

        self.programmed_stop_dt = None
        self.starttime = None

        # #################

        self.mutex = QtCore.QMutex()
        self.threads = list()
        
        # #################

        # LAYOUTS
        self.main = QtGui.QWidget()
        self.setCentralWidget(self.main)

        self.main_layout = QtGui.QVBoxLayout()
        self.main.setLayout(self.main_layout)

        # self.top_layout = QtGui.QHBoxLayout()
        self.audio_layout = QtGui.QHBoxLayout()
        self.bottom_layout = QtGui.QHBoxLayout()
        self.bottom_info_layout = QtGui.QHBoxLayout()

        self.main_layout.addLayout(self.audio_layout)
        self.main_layout.addLayout(self.bottom_layout)
        self.main_layout.addLayout(self.bottom_info_layout)

        # #################

        # AUDIO DISPLAY
        self.audio_disp = AudioDisplay(self, self.debug)
        self.button_audio_plus = QtGui.QPushButton('+ Vol')
        self.button_audio_minus = QtGui.QPushButton('- Vol')
        self.audio_pm_layout = QtGui.QVBoxLayout()
        
        self.audio_layout.addWidget(self.audio_disp.canvas)
        self.audio_layout.addLayout(self.audio_pm_layout)
        self.audio_pm_layout.addWidget(self.button_audio_plus)
        self.audio_pm_layout.addWidget(self.button_audio_minus)
        # self.audio_layout.addWidget(self.audo_disp.toolbar)

        xy = 110
        self.audio_disp.canvas.setMaximumHeight(200)
        self.button_audio_plus.setMinimumHeight(xy)
        self.button_audio_plus.setMaximumWidth(xy)
        self.button_audio_plus.setMinimumWidth(xy)
        self.button_audio_minus.setMinimumHeight(xy)
        self.button_audio_minus.setMaximumWidth(xy)
        self.button_audio_minus.setMinimumWidth(xy)

        # #################

        # POPULATE BOTTOM LAYOUT
        self.button_record = QtGui.QPushButton('Start Recording')
        self.button_stop = QtGui.QPushButton('Stop')
        self.button_cancel = QtGui.QPushButton('Cancel')
        self.button_tag = QtGui.QPushButton('&Comment')
        self.button_idle = QtGui.QPushButton('Pause Display')

        self.button_stop.setDisabled(True)
        self.button_cancel.setDisabled(True)
        self.button_tag.setDisabled(True)

        self.button_record.setMinimumHeight(50)
        self.button_stop.setMinimumHeight(50)
        self.button_cancel.setMinimumHeight(50)
        self.button_tag.setMinimumHeight(50)
        self.button_idle.setMinimumHeight(50)

        self.bottom_layout.addWidget(self.button_record)
        self.bottom_layout.addWidget(self.button_stop)
        self.bottom_layout.addWidget(self.button_cancel)
        self.bottom_layout.addWidget(self.button_tag)
        self.bottom_layout.addWidget(self.button_idle)

        self.label_time = QtGui.QLabel('', self)
        font = self.label_time.font()
        font.setPointSize(self.label_font_size)
        self.label_time.setFont(font)

        self.bottom_info_layout.addStretch(0)
        self.bottom_info_layout.addWidget(self.label_time)
        self.bottom_info_layout.addStretch(0)

        # set initial label
        self.label_time.setText('no recording')
        self.displaytimer = QtCore.QTimer()
        self.connect(self.displaytimer, QtCore.SIGNAL('timeout()'), self.update_timelabel)
        self.connect(self.displaytimer, QtCore.SIGNAL('timeout()'), self.timecheck)

        # #################
        
        # audiodisp
        self.threadDisp = QtCore.QThread(self)
        self.audio_disp.moveToThread( self.threadDisp )
        self.threadDisp.start()
        self.threads.append(self.threadDisp)

        self.audioDev = AudioDev(self, use_hydro=self.use_hydro, debug=self.debug)
        self.threadAudio = QtCore.QThread(self)
        self.audioDev.moveToThread( self.threadAudio )
        self.threads.append(self.threadAudio)
        self.threadAudio.start()

        # #################

        # start stop
        self.connect(self, QtCore.SIGNAL('start_saving'), self.audioDev.start_saving)
        self.connect(self, QtCore.SIGNAL('start_capture'), self.audioDev.start_capture)

        # data connections        
        self.connect(self.audioDev, QtCore.SIGNAL('new data (PyQt_PyObject)'), self.audio_disp.update_data)

        # #################

        # connect buttons
        self.connect(self.button_cancel, QtCore.SIGNAL('clicked()'), self.clicked_cancel)
        self.connect(self.button_record, QtCore.SIGNAL('clicked()'), self.clicked_record)
        self.connect(self.button_stop, QtCore.SIGNAL('clicked()'), self.clicked_stop)
        self.connect(self.button_tag, QtCore.SIGNAL('clicked()'), self.clicked_comment)
        self.connect(self.button_idle, QtCore.SIGNAL('clicked()'), self.clicked_idle)
        self.connect(self.button_audio_plus, QtCore.SIGNAL('clicked()'), self.clicked_button_audio_plus)
        self.connect(self.button_audio_minus, QtCore.SIGNAL('clicked()'), self.clicked_button_audio_minus)

        # create keyboard shortcuts
        self.create_actions()
        self.create_menu_bar()

        self.emit(QtCore.SIGNAL("start_capture"))

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
        # EXAMPLE
        # Cancel Recording
        self.action_cancel = QtGui.QAction("Cancel recording", self)
        self.action_cancel.setShortcut(Qt.Qt.Key_Escape)
        self.connect(self.action_cancel, QtCore.SIGNAL('triggered()'), self.clicked_cancel)
        self.addAction(self.action_cancel)

        # Create a start stop action
        self.action_start_stop = QtGui.QAction('Start, stop recording',self)
        self.action_start_stop.setShortcut(Qt.Qt.CTRL+Qt.Qt.Key_Space)
        self.connect(self.action_start_stop, QtCore.SIGNAL('triggered()'), self.start_stop)
        self.addAction(self.action_start_stop)

        # Create a start stop action
        self.action_start_stop_delayed = QtGui.QAction('Start, stop recording',self)
        self.action_start_stop_delayed.setShortcut(Qt.Qt.Key_Space)
        self.connect(self.action_start_stop_delayed, QtCore.SIGNAL('triggered()'), self.start_stop_delayed)
        self.addAction(self.action_start_stop_delayed)

        # Create a Tag
        self.action_tag = QtGui.QAction('Comment recording',self)
        self.action_tag.setShortcut(Qt.Qt.CTRL+Qt.Qt.Key_T)
        self.connect(self.action_tag, QtCore.SIGNAL('triggered()'), self.clicked_comment)
        self.addAction(self.action_tag)

        # Change Tabs
        # self.action_change_tab_left = QtGui.QAction("Go one tab to the right", self)
        # self.action_change_tab_left.setShortcut(Qt.Qt.CTRL + Qt.Qt.Key_PageDown)
        # self.connect(self.action_change_tab_left, QtCore.SIGNAL('triggered()'), self.next_tab)
        # self.addAction(self.action_change_tab_left)

        # self.action_change_tab_right = QtGui.QAction("Go one tab to the left", self)
        # self.action_change_tab_right.setShortcut(Qt.Qt.CTRL + Qt.Qt.Key_PageUp)
        # self.connect(self.action_change_tab_right, QtCore.SIGNAL('triggered()'), self.prev_tab)
        # self.addAction(self.action_change_tab_right)

        # Exit
        exit_action = QtGui.QAction(QtGui.QIcon('exit.png'), '&Exit', self)
        exit_action.setShortcut('Alt+Q')
        exit_action.setStatusTip('Exit application')
        # exit_action.triggered.connect(QtGui.qApp.quit)
        exit_action.triggered.connect(self.close)
        self.exit_action = exit_action

    def start_stop(self):
        """ for action """
        if self.debug > 0:
            print('start_stop called')
        if not self.button_record.isEnabled():
            self.clicked_stop()
        else:
            self.clicked_record(0)

    def start_stop_delayed(self):
        """ for action """
        if self.debug > 0:
            print('start_stop called')
        if not self.button_record.isEnabled():
            self.clicked_stop()
        else:
            self.clicked_record(self.start_delay)

    def clicked_record(self, delay=-1):
        if delay == -1: delay = self.start_delay
        self.start_new_recording_session(delay)
        self.button_record.setDisabled(True)
        self.button_cancel.setEnabled(True)
        self.button_tag.setEnabled(True)
        self.button_stop.setDisabled(False)

    def clicked_cancel(self):
        self.clicked_stop()
        self.button_cancel.setEnabled(False)
        self.button_tag.setEnabled(False)

    def clicked_stop(self):
        self.stop_all_saving()
        self.button_record.setDisabled(False)
        self.button_stop.setDisabled(True)
        self.button_cancel.setDisabled(True)
        self.button_tag.setDisabled(True)

    def clicked_comment(self):
        timestamp = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
        dlg =  QtGui.QInputDialog(self)
        dlg.setInputMode(QtGui.QInputDialog.TextInput)
        dlg.setLabelText('Comment on data:')                        
        dlg.setWindowTitle('Comment')
        dlg.resize(500,200)
        ok = dlg.exec_()  # shows the dialog
        s = timestamp + ' \t ' + dlg.textValue()
        if ok:
            self.set_timestamp(s)

    def clicked_button_audio_plus(self):
        if self.debug > 0:
            print('clicked_button_audio_plus')
        self.emit(QtCore.SIGNAL("audio_plus"))

    def clicked_button_audio_minus(self):
        if self.debug > 0:
            print('clicked_button_audio_minus')
        self.emit(QtCore.SIGNAL("audio_minus"))

    def clicked_idle(self):
        if self.idle_screen:
            self.idle_screen = False
            self.button_idle.setText('Pause Display')
            self.emit(QtCore.SIGNAL("idle screen (PyQt_PyObject)"), False)
        else:
            self.idle_screen = True
            self.button_idle.setText('Continue Display')
            self.emit(QtCore.SIGNAL("idle screen (PyQt_PyObject)"), True)

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

    def update_timelabel(self):
        timestamp = self.starttime.strftime("%Y-%m-%d  %H:%M:%S")
        time_label = 'start-time: {0:s}   ---  running: {1:s}'.format(timestamp, str(datetime.now()-self.starttime)[:-7])
        self.label_time.setText(time_label)

        # check for potential recording restarts
        self.timecheck()

    # def set_saving(self, val):
    #     self.mutex.lock()
    #     self.saving = val
    #     self.mutex.unlock()

    # def is_saving(self):
    #     self.mutex.lock()
    #     s = self.saving
    #     self.mutex.unlock()
    #     return s

    def start_new_recording_session(self, delay):

        self.query_recording_info()
        self.starttime = datetime.now() + timedelta(seconds=delay)
        self.rec_info['rec_start'] = self.starttime.strftime("%Y-%m-%d__%H-%M-%S")

        # create a new directory for the data
        timestamp = self.starttime.strftime("%Y-%m-%d__%H-%M-%S")
        self.save_dir = os.path.join(self.working_dir, self.name+'_'+timestamp)
        try:
            os.mkdir(self.save_dir)
        except:
            sys.exit('creation of output directory failed')

        self.write_recording_info()
        self.file_counter = 0

        if delay > 0:
            self.delaytimer = QtCore.QTimer()
            self.connect(self.delaytimer, QtCore.SIGNAL('timeout()'), self.update_delay)
            self.delaytimer.start(1000)  # msec interval
            self.update_delay()
        else:
            self.start_recordings()

    def update_delay(self):
        countdown = self.starttime-datetime.now()
        if countdown.total_seconds() > 0:
            time_label = 'start in {:.0f} seconds'.format(countdown.total_seconds())
            self.label_time.setText(time_label)
        else:
            self.delaytimer.stop()
            self.delaytimer = None
            self.start_recordings()

    def start_recordings(self):

        self.set_restart_times()
        self.file_counter += 1

        # in case of other synced recording devices:
        ## these have to be ready when the trigger from the audio-device arrives
        self.prepare_other_recordings(self.file_counter)
        self.audioDev.prepare_recording(self.save_dir, self.file_counter)

        self.saving = True
        self.start_other_recordings()
        self.audioDev.start_saving()

        # DROP TIMESTAMP
        timestamp = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
        s = timestamp + ' \t ' + 'recording started'
        self.set_timestamp(s)

        self.displaytimer.start(1000)  # msec interval
        self.update_timelabel()

    def recording_restart(self):

        self.stop_all_saving()

        # DROP TIMESTAMP
        timestamp = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
        s = timestamp + ' \t ' + 'recording stopped'
        self.set_timestamp(s)
        self.start_recordings()

    def set_restart_times(self):

        # do nothing if there are defined restart times
        if len(self.restart_dts):
            return

        now = datetime.now()
        midnight_yesterday = datetime(now.year, now.month, now.day)
        midnight_today = datetime(now.year, now.month, now.day)+timedelta(hours=24)
        
        self.restart_dts = list()
        for hours in self.restart_times:
            new_dt = midnight_yesterday + timedelta(hours=hours)
            if new_dt > now and new_dt <= midnight_today:
                self.restart_dts.append(new_dt)

        # debug: test restart times
        # self.restart_dts = [datetime.now()+timedelta(seconds=10)]

    def timecheck(self):
        # check for next_inrecording_restart
        if len(self.restart_dts) and datetime.now() > self.restart_dts[0]:
            self.restart_dts.pop(0)
            self.recording_restart()

    def query_recording_info(self):
        # query info on recording
        dlg =  QtGui.QInputDialog(self)
        dlg.setInputMode(QtGui.QInputDialog.TextInput)
        dlg.setLabelText('Info on recording:')                        
        dlg.setWindowTitle('Info on recording')
        dlg.resize(500,200)
        ok = dlg.exec_()  # shows the dialog
        if ok:
            self.rec_info['rec_info'] = dlg.textValue()
        else:
            self.rec_info['rec_info'] = 'No info available'

    def write_recording_info(self):
        recording_info_fn = 'recording_info.txt'
        fn = os.path.join(self.save_dir, recording_info_fn)
        with open(fn, 'w') as f:
            f.write(u'recording info: {0}\n'.format(self.rec_info['rec_info']).encode("utf-8"))
            f.write(u'starttime: {0}\n'.format(self.rec_info['rec_start']).encode("utf-8"))
            f.write(u'endtime: {0}\n'.format(self.rec_info['rec_end']).encode("utf-8"))
            for c in self.rec_info['comments']:
                f.write(u'comment: {0}\n'.format(c).encode("utf-8"))

    def stop_all_saving(self):
        if not self.saving:
            return
        self.displaytimer.stop()
        self.label_time.setText('no recording')

        self.audioDev.stop_saving()
        self.stop_other_recordings()
        self.saving = False

        # document stop
        self.rec_info['rec_end'] = datetime.now().strftime("%Y-%m-%d__%H-%M-%S")
        self.write_recording_info()
        self.rec_info = dict(rec_info='',
                             rec_start='',
                             rec_end='',
                             comments=list())

    def stop_all_capture(self):
        self.audioDev.stop_recording()
        self.close_other_recordings()

    def set_timestamp(self, s):
        print('Timestamp: {}'.format(s))
        
        if self.save_dir is None:
            return
        if self.debug > 0:
            print('timestamp: {}'.format(s))
        timestamp_fn = u'{:04d}_timestamps.txt'.format(self.file_counter)
        fn = os.path.join(self.save_dir, timestamp_fn)
        with open(fn, 'a') as f:
            f.write(s.encode("utf-8")+'\n')
        self.rec_info['comments'].append(s)

    def raise_warning(self, s):
        e = '\n'+80*'#'+'\n'
        print(e+'Warning raised: {}'.format(s)+e)

    def raise_error(self, s):
        e = '\n'+80*'#'+'\n'
        print(e+'Error raised: {}'.format(s)+e)
        self.close()

    def closeEvent(self, event):
        self.stop_all_saving()
        QtCore.QThread.msleep(200)
        self.stop_all_capture()

        # finish threads
        for thread in self.threads:
            thread.quit()
        QtCore.QThread.msleep(200)
        print('See ya ...')
        self.app.quit()

    def prepare_other_recordings(self, file_counter):
        pass

    def start_other_recordings(self):
        pass

    def stop_other_recordings(self):
        pass

    def close_other_recordings(self):
        pass

    def stop_other_recordings(self):
        pass

    def close_other_recordings(self):
        pass

# ######################################################
# ######################################################

if __name__=="__main__":
    args = sys.argv
    # to_be_parsed = args[1:]

    # define options parser
    parser = OptionParser()
    parser.add_option("-k", "--stop_time", action="store", type="string", dest="stop_time", default='')
    parser.add_option("-o", "--output_directory", action="store", type="string", dest="output_dir", default='')
    parser.add_option("-s", "--instant_start", action="store_true", dest="instant_start", default=False)
    parser.add_option("-i", "--idle_screen", action="store_true", dest="idle_screen", default=False)
    (options, args) = parser.parse_args(args)

    qapp = QtGui.QApplication(sys.argv)  # create the main application
    main = Main(qapp, options=options)  # create the mainwindow instance
    main.show()  # show the mainwindow instance
    exit(qapp.exec_())  # start the event-loop: no signals are sent or received without this.
