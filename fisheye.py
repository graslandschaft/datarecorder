#! /usr/bin/env python

"""
TODO
- config dialogs for recording devices
    - set and indicate ROI
    - set framerate
"""

# ######################################################

import sys, os, time
import wave
from optparse import OptionParser
from datetime import date, datetime, timedelta
import numpy as np
from PIL import Image as image
from PIL import ImageQt as iqt

from AudioDev import AudioDev
from AudioDevOut import AudioDevOut
from AudioDisplay import AudioDisplay

try:
    from PyQt4 import QtGui, QtCore, Qt
except Exception, details:
    print 'Unfortunately, your system misses the PyQt4 packages.'
    quit()

from VideoCanvas import VideoTab, VideoCanvas
from Camera_pointgrey import Camera as pgCamera
from Camera_pointgrey import get_available_flycap_cameras
from Camera import Camera

# ######################################################

width, height = 1000, 800
offset_left, offset_top = 100, 100
max_tab_width, min_tab_width = 1000, 480

# ######################################################

class Main(QtGui.QMainWindow):
    def __init__( self, app, options=None, parent=None):
        QtCore.QObject.__init__(self, parent)
        self.app = app
        self.name = 'fisheye'

        self.width = 1000
        self.height = 400
        self.offset_left = 100
        self.offset_top = 100
        self.max_tab_width = 1000
        self.min_tab_width = 400

        self.setGeometry(offset_left, offset_top, width, height)
        self.setSizePolicy(Qt.QSizePolicy.Maximum, Qt.QSizePolicy.Maximum)
        self.setMinimumSize(width, height)
        self.setWindowTitle('FishEye')

        # #################

        # HANDLES
        self.idle_screen = False
        self.audio_playback = False
        self.starttime = None
        self.saving = False
        self.working_dir = os.path.abspath(os.path.curdir)
        self.save_dir = None
        self.output_dir = None
        self.start_delay = 1
        self.last_framerate = 0
        self.rec_info = dict(rec_info='',
                             rec_start='',
                             rec_end='',
                             comments=list())

        self.pointgrey = False
        self.use_hydro = False
        self.fast_and_small_video = False
        self.triggered_video = False

        ############
        self.debug = 0
        ############

        # #################

        self.handle_options(options)

        # #################

        if os.name == 'posix':
            self.label_font_size = 18
        else:
            self.label_font_size = 12

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

        self.top_layout = QtGui.QHBoxLayout()
        self.audio_layout = QtGui.QHBoxLayout()
        self.bottom_layout = QtGui.QHBoxLayout()
        self.bottom_info_layout = QtGui.QHBoxLayout()

        self.main_layout.addLayout(self.top_layout)
        
        audioinput_group = QtGui.QGroupBox('Audio Input')
        audioinput_group.setLayout(self.audio_layout)
        self.main_layout.addWidget(audioinput_group)

        if self.audio_playback:
            self.audioout_layout = QtGui.QHBoxLayout()
            audioout_group = QtGui.QGroupBox('Audio Output')
            audioout_group.setLayout(self.audioout_layout)
            self.main_layout.addWidget(audioout_group)

        self.main_layout.addLayout(self.bottom_layout)
        self.main_layout.addLayout(self.bottom_info_layout)

        # #################

        # POPULATE TOP LAYOUT
        self.videos = QtGui.QTabWidget()
        self.videos.setMinimumWidth(min_tab_width)
        self.videos.setMaximumWidth(max_tab_width)
        self.video_recordings = None
        self.video_tabs = {}

        self.top_layout.addWidget(self.videos)

        # VIDEO
        self.populate_video_tabs()
        # time.sleep(1)

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
        self.button_audio_minus.setMinimumHeight(xy)
        self.button_audio_minus.setMaximumWidth(xy)

        # #################

        # AUDIO OUTPUT DISPLAY
        if self.audio_playback:
            self.init_replay()  # initialize replay

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

        self.audioDev = AudioDev(self, use_hydro=self.use_hydro, debug=self.debug, 
                            fast_and_small_video=self.fast_and_small_video, triggering=self.triggered_video)
        self.threadAudio = QtCore.QThread(self)
        self.audioDev.moveToThread( self.threadAudio )
        self.threads.append(self.threadAudio)
        self.threadAudio.start()

        # #################

        # connect cameras to audio trigger
        if self.triggered_video:
            for cam_name, cam in self.cameras.items():
                self.connect(self.audioDev, 
                    QtCore.SIGNAL("grab frame (PyQt_PyObject)"), cam.grab_frame)
        else:
            for cam_name, cam in self.cameras.items():
                self.connect(self, QtCore.SIGNAL('start_capture'), cam.start_capture)

        # #################

        # start stop
        self.connect(self, QtCore.SIGNAL('start_saving'), self.audioDev.start_saving)
        self.connect(self, QtCore.SIGNAL('start_capture'), self.audioDev.start_capture)

        # data connections
        self.connect(self.audioDev, QtCore.SIGNAL('new data (PyQt_PyObject)'), self.audio_disp.update_data)

        # #################

        # connect buttons
        self.connect(self.button_cancel, QtCore.SIGNAL('clicked()'), self.clicked_cancel)
        self.connect(self.button_record, QtCore.SIGNAL('clicked()'), self.clicked_start)
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
            self.clicked_start(0)

    def start_stop_delayed(self):
        """ for action """
        if self.debug > 0:
            print('start_stop called')
        if not self.button_record.isEnabled():
            self.clicked_stop()
        else:
            self.clicked_start(self.start_delay)

    def clicked_start(self, delay=-1):
        if delay == -1: delay = self.start_delay
        ok = self.start_new_recording_session(delay)
        if not ok:
            return
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
        s = u'{} \t {}'.format(timestamp, dlg.textValue())
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

    def init_replay(self):
        # initialize audio playback and add playback display and increase widget size by 200 points 
        self.audiodevout = AudioDevOut(self, debug=self.debug)
        self.threadAudioOut = QtCore.QThread(self)
        self.audiodevout.moveToThread( self.threadAudioOut )
        self.threads.append(self.threadAudioOut)
        self.threadAudioOut.start()

        self.audioout_disp = AudioDisplay(self, self.debug)
        self.button_audioout_plus = QtGui.QPushButton('+ Vol')
        self.button_audioout_minus = QtGui.QPushButton('- Vol')
        self.audioout_pm_layout = QtGui.QVBoxLayout()
        
        xy = 110
        self.button_audioout_plus.setMinimumHeight(xy)
        self.button_audioout_plus.setMaximumWidth(xy)
        self.button_audioout_plus.setMinimumWidth(xy)
        self.button_audioout_minus.setMinimumHeight(xy)
        self.button_audioout_minus.setMaximumWidth(xy)
        self.button_audioout_minus.setMinimumWidth(xy)

        self.audioout_layout.addWidget(self.audioout_disp.canvas)
        self.audioout_layout.addLayout(self.audioout_pm_layout)
        self.audioout_pm_layout.addWidget(self.button_audioout_plus)
        self.audioout_pm_layout.addWidget(self.button_audioout_minus)

        self.height +=  300
        self.setGeometry(self.offset_left, self.offset_top, self.width, self.height)
        self.setMinimumSize(self.width, self.height)

        # connections
        # self.connect(self.button_audioout_plus, QtCore.SIGNAL('clicked()'), self.clicked_button_audioout_plus)
        # self.connect(self.button_audioout_minus, QtCore.SIGNAL('clicked()'), self.clicked_button_audioout_minus)
        self.connect(self, QtCore.SIGNAL('start playback'), self.audiodevout.play)
        self.connect(self.audiodevout, QtCore.SIGNAL("playback finished"), self.clicked_stop)
        self.connect(self.audiodevout, QtCore.SIGNAL('new data (PyQt_PyObject)'),
             self.audioout_disp.update_data)

    def clicked_button_audio_plus(self):
        if self.debug > 0:
            print('clicked_button_audio_plus')
        self.emit(QtCore.SIGNAL("audioout_plus"))

    def clicked_button_audio_minus(self):
        if self.debug > 0:
            print('clicked_button_audio_minus')
        self.emit(QtCore.SIGNAL("audioout_minus"))

    def handle_options(self, options):
        if options:
            # # programmed stop-time
            # if options.stop_time:
            #     try:
            #         a = datetime.strptime(options.stop_time, '%H:%M:%S')
            #         b = datetime.now()
            #         c = datetime(b.year, b.month, b.day, a.hour, a.minute, a.second)
            #         if c < b:
            #             c += timedelta(days=1)
            #     except ValueError:
            #         pass
            #     else:
            #         self.programmed_stop = True
            #         self.programmed_stop_datetime = c

            #     try:
            #         a = datetime.strptime(options.stop_time, '%Y-%m-%d %H:%M:%S')
            #     except ValueError:
            #         pass
            #     else:
            #         self.programmed_stop = True
            #         self.programmed_stop_datetime = a

            #     if not self.programmed_stop is True:
            #         print 'Error: allowed stop-time formats are:' \
            #               '\n"HH:MM:SS" and "YY-mm-dd HH:MM:SS"'
            #         quit()
            #     else:
            #         print 'Automated Stop activated: {0:s}'.format(str(self.programmed_stop_datetime))

            # output directory
            if options.output_dir:
                if os.path.exists(options.output_dir):
                    self.output_dir = os.path.realpath(options.output_dir)
                    print('Output Directory: {0:s}'.format(self.output_dir))
                else:
                    print 'Error: output directory does not exist'
                    self.close()

            if options.audio_playback:
                if os.path.exists(options.audio_playback):
                    self.audio_playback_file =options.audio_playback
                    if not os.path.exists(self.audio_playback_file):
                        sys.exit('Output audio-file does not exist')                    
                    self.audio_playback = True
            if options.show_devices:
                from AudioDev import show_available_input_devices
                from AudioDevOut import show_available_output_devices

                show_available_input_devices()
                show_available_output_devices()
                sys.exit()

    def start_new_recording_session(self, delay):

        ok = self.query_recording_info()
        if not ok:
            return False
        self.starttime = datetime.now() + timedelta(seconds=delay)
        self.rec_info['rec_start'] = self.starttime.strftime("%Y-%m-%d  %H:%M:%S")

        # create a new directory for the data
        save_dirname = self.starttime.strftime("%Y-%m-%d__%H-%M-%S")
        if self.output_dir is None:
            self.save_dir = os.path.join(self.working_dir, self.name+'_'+save_dirname)
        else:
            self.save_dir = os.path.join(self.output_dir, self.name+'_'+save_dirname)

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
        return True

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

        if self.audio_playback:
            self.audiodevout.open(self.audio_playback_file)
            # DROP TIMESTAMP
            timestamp = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
            s = timestamp + ' \t ' + 'Playback - Using stimulus file: {}'.format(self.audio_playback_file)
            self.set_timestamp(s)

        self.saving = True
        self.start_other_recordings()
        self.audioDev.start_saving()

        if self.audio_playback:
            self.emit(QtCore.SIGNAL("start playback"))

        # DROP TIMESTAMP
        timestamp = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
        s = timestamp + ' \t ' + 'recording started'
        self.set_timestamp(s)

        self.displaytimer.start(1000)  # msec interval
        self.update_timelabel()

    def recording_restart(self):

        self.stop_all_saving(restart=True)
        self.start_recordings()

        self.set_restart_times() ## debug

    def set_restart_times(self):

        # do nothing if there are defined restart times
        if len(self.restart_dts) or self.audio_playback:
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
        self.restart_dts = [datetime.now()+timedelta(seconds=20)]

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
            if self.audio_playback:
                self.rec_info['rec_info'] += ' -- Playback of: {:}'.format(self.audio_playback_file)
            return True
        else:
            return False

    def write_recording_info(self):
        recording_info_fn = 'recording_info.txt'
        fn = os.path.join(self.save_dir, recording_info_fn)
        with open(fn, 'w') as f:
            f.write(u'recording info: {0}\n'.format(self.rec_info['rec_info']).encode("utf-8"))
            f.write(u'starttime: {0}\n'.format(self.rec_info['rec_start']).encode("utf-8"))
            f.write(u'endtime: {0}\n'.format(self.rec_info['rec_end']).encode("utf-8"))
            for c in self.rec_info['comments']:
                f.write(u'comment: {0}\n'.format(c).encode("utf-8"))

    def stop_all_saving(self, restart=False):
        print('stopping recording')
        if not self.saving:
            return
        self.saving = False
        self.displaytimer.stop()
        self.label_time.setText('no recording')

        self.audioDev.stop_saving()
        self.stop_other_recordings()

        if self.audio_playback:
            self.audiodevout.stop_playing()
            self.audioout_disp.reset_plot()

        # DROP TIMESTAMP
        timestamp = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
        s = timestamp + ' \t ' + 'recording stopped'
        self.set_timestamp(s)

        if not restart:
            # document stop
            self.rec_info['rec_end'] = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
            self.write_recording_info()
            self.rec_info = dict(rec_info='',
                                 rec_start='',
                                 rec_end='',
                                 comments=list())

    def stop_all_capture(self):
        self.canvastimer.stop()
        self.audioDev.stop_recording()
        self.close_other_recordings()

    def set_timestamp(self, s):
        print(u'Timestamp: {}'.format(s))
        
        if self.save_dir is None:
            return
        if self.debug > 0:
            print(u'timestamp: {}'.format(s))
        timestamp_fn = u'{:04d}_timestamps.txt'.format(self.file_counter)
        fn = os.path.join(self.save_dir, timestamp_fn)
        with open(fn, 'a') as f:
            f.write(s.encode("utf-8")+'\n')
        self.rec_info['comments'].append(s)

    def raise_warning(self, s):
        e = '\n'+80*'#'+'\n'
        print(e+u'Warning raised: {}'.format(s)+e)

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
        if self.triggered_video:
            framerate = self.audioDev.get_defined_framerate()
            if self.last_framerate < self.audioDev.get_defined_framerate()*.8:
                framerate = self.last_framerate
                self.raise_warning('Actual video framerate much smaller than defined framerate!')

            for cam_name, cam in self.cameras.items():
                cam.new_recording(self.save_dir, self.file_counter, framerate)
        else:
            for cam_name, cam in self.cameras.items():
                    cam.new_recording(self.save_dir, self.file_counter)

    def start_other_recordings(self):
        for cam_name, cam in self.cameras.items():
            cam.start_saving()

    def stop_other_recordings(self):
        for cam_name, cam in self.cameras.items():
            cam.stop_saving(self.audioDev.grabframe_counter)

    def close_other_recordings(self):
        QtCore.QThread.msleep(500)
        for cam_name, cam in self.cameras.items():
            if not self.triggered_video:
                cam.stop_recording()
                QtCore.QThread.msleep(100)
            cam.close()

    def populate_video_tabs(self):

        if self.pointgrey:
            cam_num = get_available_flycap_cameras()
            print('Number of flycap-cameras: {}'.format(cam_num))

            # put cameras into dictionary
            self.cameras = dict()
            for j in xrange(cam_num):
                cam = pgCamera(self, j, fast_and_small_video=self.fast_and_small_video,
                             triggered=self.triggered_video)
                cam.name = str(j)
                self.cameras[str(j)] = cam 

        else:
            camera_device_search_range = range(0, 20)
            camera_name_format = 'camera%02i'
            tmp = [cam for cam in [Camera(self, device_no=i) for i in camera_device_search_range] if cam.is_working()]

            # put cameras into dictionary
            self.cameras = dict()
            for j, cam in enumerate(tmp):
                cam.name = camera_name_format % j
                self.cameras[cam.name] = cam

        if len(self.cameras) > 0:

            # create tabs for cameras
            for cam_name, cam in self.cameras.items():
                self.video_tabs[cam_name] = VideoTab(self, cam_name, parent=self)
                self.videos.addTab(self.video_tabs[cam_name], cam_name)

            # create threads for cameras
            self.camera_threads = dict()
            for cam_name, cam in self.cameras.items():
                self.camera_threads[cam_name] = QtCore.QThread(parent=self)
                cam.moveToThread(self.camera_threads[cam_name])
                self.camera_threads[cam_name].start()
                self.threads.append(self.camera_threads[cam_name])
                # connections
                # self.connect(cam, QtCore.SIGNAL("NewFrame(PyQt_PyObject)"), self.update_canvas)
                self.connect(self, QtCore.SIGNAL("start_recordings ( PyQt_PyObject ) "), cam.new_recording)
                self.connect(self, QtCore.SIGNAL("stop_recordings"), cam.stop_saving)

        else:
            self.videos.addTab(QtGui.QWidget(), "No camera found")

        # create timer for updating the video canvas
        self.canvastimer = QtCore.QTimer()
        self.connect(self.canvastimer, QtCore.SIGNAL('timeout()'), self.update_canvas)
        self.canvastimer.start(50)  # 20 Hz

    def update_canvas(self):
        # check for programmed stop-time
        if self.programmed_stop_dt is not None \
           and self.programmed_stop_dt < datetime.now():
            self.stop_all_recordings()
            # wait for recordings to stop
            self.wait(100)
            self.app.exit()

        # grab data from camera and display
        cam_name = str(self.videos.tabText(self.videos.currentIndex()))

        if not self.idle_screen:
            data = self.cameras[cam_name].get_dispframe()  # grab current frame
            if data == None:
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
    # app = QtCore.QCoreApplication(sys.argv)
    # main = Main( app )
    # QtCore.QTimer().singleShot( 0, main.run )
    # sys.exit(app.exec_()) # start eventloop

    args = sys.argv
    to_be_parsed = args[1:]

    # define options parser
    parser = OptionParser()
    # parser.add_option("-k", "--stop_time", action="store", type="string", dest="stop_time", default='')
    parser.add_option("-o", "--output_directory", action="store", type="string", dest="output_dir", default='')
    parser.add_option("-a", "--audio_playback", action="store", type="string", dest="audio_playback", default='')
    parser.add_option("-d", "--devices", action="store_true", dest="show_devices", default=False)
    # parser.add_option("-s", "--instant_start", action="store_true", dest="instant_start", default=False)
    # parser.add_option("-i", "--idle_screen", action="store_true", dest="idle_screen", default=False)
    (options, args) = parser.parse_args(args)

    qapp = QtGui.QApplication(sys.argv)  # create the main application
    main = Main(qapp, options=options)  # create the mainwindow instance
    main.show()  # show the mainwindow instance
    exit(qapp.exec_())  # start the event-loop: no signals are sent or received without this.
