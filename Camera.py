import sys
import warnings
from datetime import datetime
from collections import deque
from matplotlib.dates import date2num

try:
    from PyQt4 import QtGui, QtCore, Qt
except Exception, details:
    print 'Unfortunately, your system misses the PyQt4 packages.'
    quit()
from VideoRecording import VideoRecording

__author__ = 'Fabian Sinz, Joerg Henninger'
import cv2

def brg2rgb(frame):
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

def brg2grayscale(frame):
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

class Camera(QtCore.QObject):
    def __init__(self, main, device_no=0, color=False, post_processor=None, parent=None):
        """
        Initializes a new camera

        :param post_processor: function that is applies to the frame after grabbing
        """
        QtCore.QObject.__init__(self, parent)
        self.mutex = QtCore.QMutex()

        self.main = main
        self.filename = 'video'
        self.framerate = 30.
        self.triggered = False
        self.color = color
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

        self.open()

        # # create timer for independent frame acquisition
        # self.timer = QtCore.QTimer()
        # self.connect(self.timer, QtCore.SIGNAL('timeout()'), self.grab_frame)

        self.connect(self, QtCore.SIGNAL('set timestamp (PyQt_PyObject)'), main.set_timestamp)
        self.connect(self, QtCore.SIGNAL('Raise Error (PyQt_PyObject)'), main.raise_error)

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, type, value, traceback):
        self.close()

    def open(self):
        capture = cv2.VideoCapture(self.device_no)
        self.capture = capture
        
        # try to increase the resolution of the frame capture; default is 640x480
        #~ self.capture.set(cv2.cv.CV_CAP_PROP_FRAME_WIDTH, 864)
        #~ self.capture.set(cv2.cv.CV_CAP_PROP_FRAME_HEIGHT, 480)
        self.capture.set(cv2.cv.CV_CAP_PROP_FRAME_WIDTH, 1280)
        self.capture.set(cv2.cv.CV_CAP_PROP_FRAME_HEIGHT, 720)

    def is_working(self):
        return self.capture.isOpened()

    def get_properties(self):
        """
        :returns: the properties (cv2.cv.CV_CAP_PROP_*) from the camera
        :rtype: dict
        """
        if self.capture is not None:
            properties = [e for e in dir(cv2.cv) if "CV_CAP_PROP" in e]
            ret = {}
            for e in properties:
                ret[e[12:].lower()] = self.capture.get(getattr(cv2.cv, e))
            return ret
        else:
            warnings.warn("Camera needs to be opened first!")
            return None

    def get_resolution(self):
        if self.capture is not None:
            return int(self.capture.get(cv2.cv.CV_CAP_PROP_FRAME_WIDTH)), \
                   int(self.capture.get(cv2.cv.CV_CAP_PROP_FRAME_HEIGHT))
        else:
            raise ValueError("Camera is not opened or not functional! Capture is None")

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
            # print(len(self.recframes))
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
        # grab frame
        flag, frame = self.capture.read()
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
        
        # post-processing
        if self.color:
            frame = brg2rgb(frame)
        else:
            frame = brg2grayscale(frame)

        # DEBUG
        # gap = 1000.*(dtime - self.last_frame).total_seconds()
        # if self.min > gap:
        #     self.min = gap
        # sys.stdout.write('\rframerate: {0:3.2f} ms{1:s}; min:{2:3.2f}'.format(gap, 5*' ', self.min,5*' '))
        # sys.stdout.flush()
        # self.last_frame = dtime

        if not flag:
            warnings.warn("Coulnd't grab frame from camera!")
            return None

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
            self.emit(QtCore.SIGNAL("NewFrame"))

    def new_recording(self, save_dir, file_counter, framerate=0):

        if not self.triggered:
            framerate = self.framerate

        self.recording = VideoRecording(self, save_dir, file_counter,
                                        self.get_resolution(),
                                        framerate)

        if not self.recording.isOpened():
            error = 'Video-recording could not be started.'
            self.emit(QtCore.SIGNAL('Raise Error (PyQt_PyObject)'), error)
            return False

        self.recordingThread = QtCore.QThread()
        self.recording.moveToThread(self.recordingThread)
        self.recordingThread.start()
        self.connect(self, QtCore.SIGNAL("NewFrame"), self.recording.write)

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

    def stop_recording(self):
        self.mutex.lock()
        self.continuous = False
        self.mutex.unlock()

    def start_capture(self):
        """ for continuous frame acquisition """
        self.continuous = True
        while self.is_recording():
            self.grab_frame()

    def start_saving(self):
        self.mutex.lock()
        self.saving = True
        self.mutex.unlock()

    def stop_saving(self, triggered_frames):
        self.mutex.lock()
        self.saving = False
        self.disconnect(self, QtCore.SIGNAL("NewFrame"), self.recording.write)
        self.mutex.unlock()
        
        last = self.recording.get_write_count()
        double_counter = -1
        while self.get_recframesize() > 0:
            print('Writing: {} of {}'.format(self.recording.get_write_count(), triggered_frames))
            print(self.get_recframesize())
            if last == self.recording.get_write_count(): double_counter += 1
            if double_counter == 10:
                error = 'Frames cannot be saved.'
                self.emit(QtCore.SIGNAL('Raise Error (PyQt_PyObject)'), error)
                break
            QtCore.QThread.msleep(100)

        # wait until all frames are written, then close the recording
        # if triggered_frames == self.recording.get_write_count():
        timestamp = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
        s = timestamp + ' \t ' + 'All frames written: '
        s += '{} of {}'.format(self.recording.get_write_count(), triggered_frames)
        self.emit(QtCore.SIGNAL('set timestamp (PyQt_PyObject)'), s)

        self.recording.release()
        self.recordingThread.quit()
        self.recordingThread.wait()
        self.recording = None
        self.recordingThread = None

    def close(self):
        # release camera
        self.capture.release()
        pass

