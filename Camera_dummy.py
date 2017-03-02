import sys, os
import warnings
from datetime import datetime
from collections import deque
from matplotlib.dates import date2num
import numpy as np

try:
    from PyQt5 import QtGui, QtCore, QtWidgets
    from PyQt5.QtCore import Qt, pyqtSignal, pyqtSlot
except ImportError, details:
    sys.exit('Unfortunately, your system misses the PyQt5 packages.')

from VideoRecording import VideoRecording

__author__ = 'Joerg Henninger'

class Camera(QtCore.QObject):
    # signals
    sig_start_rec = pyqtSignal()
    sig_set_timestamp = pyqtSignal(object)
    sig_raise_error = pyqtSignal(object)

    def __init__(self, control, device_no=0, post_processor=None, parent=None):
        """
        Initializes a new camera

        :param post_processor: function that is applies to the frame after grabbing
        """
        QtCore.QObject.__init__(self, parent)
        self.mutex = QtCore.QMutex()

        self.control = control
        self.filename = 'video'
        self.framerate = 30.
        self.triggered = False
        self.capture = None
        self.device_no = device_no
        self.name = None
        self.recording = None
        self.post_processor = post_processor
        if post_processor is None:
            self.post_processor = lambda *args:  args

        self.saving = False

        self.frame_dts = deque()
        self.recframes = deque()
        self.dispframe = None

        self.x_resolution = 800
        self.y_resolution = 800

        # self.open()

        # create timer for independent frame acquisition
        # self.timer = QtCore.QTimer()
        # self.timer.timeout.connect(self.grab_frame)

        self.sig_set_timestamp.connect(self.control.set_timestamp)
        self.sig_raise_error.connect(self.control.raise_error)

    def __exit__(self, type, value, traceback):
        self.close()

    def is_working(self):
        return True

    def get_resolution(self):
        return self.x_resolution, self.y_resolution

    def get_dispframe(self):
        self.mutex.lock()
        dispframe = self.dispframe
        self.mutex.unlock()
        self.dispframe = None
        return dispframe

    def get_recframe(self):
        if len(self.recframes):
            self.mutex.lock()
            recframe = self.recframes.popleft()
            self.mutex.unlock()
            return recframe
        else:
            return None

    def get_recframesize(self):
        self.mutex.lock()
        s = len(self.recframes)
        # print(len(self.recframes))
        self.mutex.unlock()
        return s

    def grab_frame(self, saving=False):
        QtCore.QThread.msleep(int(1000./self.framerate))
        # grab frame
        frame = (np.random.random(self.y_resolution*self.x_resolution)*255).reshape((self.y_resolution,self.x_resolution))
        frame=np.require(frame, np.uint8, 'C')
        dtime = datetime.now()

        # calculate framerate
        self.frame_dts.append(dtime)
        if len(self.frame_dts) > 100:
            self.frame_dts.popleft()
        if len(self.frame_dts) > 1:
            dur = (self.frame_dts[-1]-self.frame_dts[0]).total_seconds()
            fr = len(self.frame_dts)/dur if dur > 0 else 0
        else:
            fr = 0

        # store frames for other threads
        self.mutex.lock()
        self.dispframe = (frame, dtime, fr)
        self.mutex.unlock()

        if self.is_saving():
            self.mutex.lock()
            dtime = '{:.10f}\n'.format(date2num(dtime))  # change datetime format to float
            self.recframes.append((frame, dtime))
            self.mutex.unlock()
            # emit signal for recording thread
            # self.sig_new_frame.emit()
            # self.emit(QtCore.SIGNAL("NewFrame"))

    def new_recording(self, save_dir, file_counter, framerate=0):

        if not self.triggered:
            framerate = self.framerate

        self.recording = VideoRecording(self, save_dir, file_counter,
                                        self.get_resolution(),
                                        framerate)

        if not self.recording.isOpened():
            error = 'Video-recording could not be started.'
            self.sig_raise_error.emit(error)
            return False

        self.recordingThread = QtCore.QThread()
        self.recording.moveToThread(self.recordingThread)
        self.recordingThread.start()
        self.sig_start_rec.connect(self.recording.start_rec)
        self.sig_start_rec.emit()

    def is_recording(self):
        self.mutex.lock()
        c = self.continuous
        self.mutex.unlock()
        return c

    def is_saving(self):
        self.mutex.lock()
        sav = self.saving
        self.mutex.unlock()
        return sav

    def stop_capture(self):
        self.mutex.lock()
        self.continuous = False
        self.mutex.unlock()

    def start_capture(self):
        """ for continuous frame acquisition """
        print('video capture started')
        self.continuous = True
        while self.is_recording():
            self.grab_frame()

    # def stop_capture(self):
    #     self.timer.stop()

    def start_saving(self):
        self.mutex.lock()
        self.saving = True
        self.mutex.unlock()

    def stop_saving(self):
        self.mutex.lock()
        self.saving = False
        # self.disconnect(self, QtCore.SIGNAL("NewFrame"), self.recording.write)
        self.mutex.unlock()
        
        # last = self.recording.get_write_count()
        # double_counter = -1
        # while self.get_recframesize() > 0:
        #     if self.triggered:
        #         total = triggered_frames
        #     else:
        #         total = self.recording.get_write_count() + self.get_recframesize()
        #     print('Writing: {} of {}'.format(self.get_recframesize(), total))
        #     if last == self.recording.get_write_count(): double_counter += 1
        #     if double_counter == 10:
        #         error = 'Frames cannot be saved.'
        #         self.sig_raise_error.emit(error)
        #         # self.emit(QtCore.SIGNAL('Raise Error (PyQt_PyObject)'), error)
        #         break
        #     QtCore.QThread.msleep(100)

        self.recording.stop_recording()
        # reset
        self.recframes = deque()

        # wait until all frames are written, then close the recording
        # if triggered_frames == self.recording.get_write_count():
        timestamp = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
        s = timestamp + ' \t ' + 'Frames written: '
        if self.control.cfg['trigger'] is None:
            s += '{}'.format(self.recording.get_write_count())
        else:
            # debug:
            triggered_frames = 0
            s += '{} of {}'.format(self.recording.get_write_count(), triggered_frames)
        self.sig_set_timestamp.emit(s)

        self.recording.release()
        self.recordingThread.quit()
        self.recordingThread.wait()
        self.recording = None
        self.recordingThread = None

    def close(self):
        # release camera
        pass

