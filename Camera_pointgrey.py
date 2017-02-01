import sys
import warnings
from datetime import datetime
import flycapture2 as fc2
import numpy as np
from collections import deque
from matplotlib.dates import date2num

try:
    from PyQt4 import QtGui, QtCore, Qt
except Exception, details:
    print 'Unfortunately, your system misses the PyQt4 packages.'
    quit()
from VideoRecording import VideoRecording

__author__ = 'Joerg Henninger'

# #########################################################

framerate_focus = 30
framerate_full = 30

# #########################################################


def brg2rgb(frame):
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

def brg2grayscale(frame):
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

def get_available_flycap_cameras():
    return fc2.Context().get_num_of_cameras()


class Camera(QtCore.QObject):
    def __init__(self, main, device_no=0, fast_and_small_video=False, 
        triggered=False, post_processor=None, parent=None):
        """
        Initializes a new camera

        :param post_processor: function that is applies to the frame after grabbing
        """
        QtCore.QObject.__init__(self, parent)

        self.main = main
        self.fast_and_small_video = fast_and_small_video
        self.triggered = triggered
        self.mutex = QtCore.QMutex()

        self.filename = 'video'
        self.context = None
        self.device_no = device_no
        self.name = None
        self.post_processor = post_processor
        if post_processor is None:
            self.post_processor = lambda *args:  args

        self.saving = False

        self.frame_dts = deque()
        self.mode = 0

        self.frame_dts = deque()
        self.recframes = deque()
        self.dispframe = None

        self.open()

        self.connect(self, QtCore.SIGNAL('set timestamp (PyQt_PyObject)'), main.set_timestamp)
        self.connect(self, QtCore.SIGNAL('Raise Error (PyQt_PyObject)'), main.raise_error)

    def start_capture(self):
        if not self.triggered:
            QtCore.QTimer().singleShot( 1000, self.continuous_framegrab )

    def open(self):
        self.context = fc2.Context()
        self.context.connect(*self.context.get_camera_from_index(self.device_no))

        # self.reset_camera()

        if self.fast_and_small_video:
            width, height = self.set_resolution(2*480, 2*480)
            self.framerate = framerate_focus
        else:
            self.framerate = framerate_full
            self.set_resolution()  # maximize resolution

        if self.triggered:
            self.set_software_trigger()
            print('Framerate set to: {:.1f} Hz'.format(self.framerate))

        self.context.start_capture()
        self.im = fc2.Image()

    def set_software_trigger(self):
        # set camera to software trigger
        ## source = 7 indicates software trigger
        self.context.set_trigger_mode(True, 0, 7, 0, 0)

    def get_resolution(self):
        if self.context is not None:
            f7config = self.context.get_format7_configuration()
            return f7config['height'], f7config['width']
        else:
            raise ValueError("Camera is not opened or not functional!")

    def get_resolution_params(self):
        form = self.context.get_format7_info(self.mode)[0]
        wsteps = form['image_h_step_size']
        hsteps = form['image_v_step_size']
        max_w = form['max_width']
        max_h = form['max_height']
        return wsteps, hsteps, max_w, max_h

    def set_resolution(self, w=0, h=0):

        ws, hs, mw, mh = self.get_resolution_params()
        w = mw if w == 0 else w
        h = mh if h == 0 else h
        
        # make sure new resolution fits the requirements
        wi = int(w / ws)  # devide by stepsize to get a multiplicator
        hi = int(h / hs)
        w = min([wi*ws, mw])  # the use the multiplicator to get a valid value that is lower than the maximum value
        h = min([hi*hs, mh])
        f7config = self.context.get_format7_configuration()
        if w == 0 and h == 0:
            f7config['height'] = mh
            f7config['width'] = mw
        else:
            f7config['height'] = h
            f7config['width'] = w

        # center new ROI
        off_w = max([(mw-w)/2, 0])
        f7config['offset_x'] = off_w if off_w % 2 == 0 else off_w -1
        off_h = max([(mh-h)/2, 0])
        f7config['offset_y'] = off_h if off_h % 2 == 0 else off_h -1

        self.context.set_format7_configuration(f7config['mode'], f7config['offset_x'], 
            f7config['offset_y'], f7config['width'], 
            f7config['height'], f7config['pixel_format'])

        print('Resolution set to: {}, {}'.format(f7config['width'], f7config['height']))
        return w, h

    def set_exposure(self):
        pass

    def set_gain(self):
        pass

    def set_framerate(self, val=22):
        p = self.context.get_property(fc2.FRAME_RATE)
        p['abs_value'] = val
        p['auto_manual_mode'] = False
        self.context.set_property(p['type'], p['present'], p['on_off'], p['auto_manual_mode'],
                p['abs_control'], p['one_push'], p['abs_value'], p['value_a'], p['value_b'])

    def reset_camera(self):
        # reset to maximum resolution
        ws, hs, mw, mh = self.get_resolution_params()
        f7config = self.context.get_format7_configuration()
        f7config['width'] = mw
        f7config['height'] = mh
        self.context.set_format7_configuration(f7config['mode'], f7config['offset_x'], 
            f7config['offset_y'], f7config['width'], 
            f7config['height'], f7config['pixel_format'])

        # reset framerate to automatic
        p = self.context.get_property(fc2.FRAME_RATE)
        p['auto_manual_mode'] = True
        self.context.set_property(p['type'], p['present'], p['on_off'], p['auto_manual_mode'],
                p['abs_control'], p['one_push'], p['abs_value'], p['value_a'], p['value_b'])

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
        # print('cam grab'+str(QtCore.QThread.currentThread()))
        # triggered frame grab: update buffer
        if self.triggered:
            ret = self.context.fire_software_trigger()
        frame = np.array(self.context.retrieve_buffer(self.im))
        dtime = datetime.now()        # store frames for other threads
 
        # calculate framerate
        self.frame_dts.append(datetime.now())
        if len(self.frame_dts) > 100:
            self.frame_dts.popleft()
        if len(self.frame_dts) > 1:
            dur = (self.frame_dts[-1]-self.frame_dts[0]).total_seconds()
            fr = len(self.frame_dts)/dur if dur > 0 else 0
        else:
            fr = 0

        self.mutex.lock()
        self.dispframe = (frame, dtime, fr)
        self.mutex.unlock()
        
        if self.is_saving():
            self.mutex.lock()
            dtime = '{:.10f}\n'.format(date2num(dtime))  # change datetime format to float
            self.recframes.append((frame, dtime))
            self.mutex.unlock()
            # emit signal for recording thread
            # self.emit(QtCore.SIGNAL("NewFrame"))        # store frames for other threads

    def is_recording(self):
        self.mutex.lock()
        c = self.continuous
        self.mutex.unlock()
        return c

    def stop_recording(self):
        self.mutex.lock()
        self.continuous = False
        self.mutex.unlock()

    def start_capture(self):
        """ for continuous frame acquisition """
        self.continuous = True
        self.set_framerate(self.framerate)
        while self.is_recording():
            self.grab_frame()

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
        self.connect(self, QtCore.SIGNAL("StartRec"), self.recording.start_rec)
        self.emit(QtCore.SIGNAL('StartRec'))

    def is_saving(self):
        self.mutex.lock()
        sav = self.saving
        self.mutex.unlock()
        return sav

    def start_saving(self):
        self.mutex.lock()
        self.saving = True
        self.mutex.unlock()

    def stop_saving(self, triggered_frames):
        self.mutex.lock()
        self.saving = False
        # self.disconnect(self, QtCore.SIGNAL("NewFrame"), self.recording.write)
        self.mutex.unlock()
        
        last = self.recording.get_write_count()
        double_counter = -1
        while self.get_recframesize() > 0:
            if self.triggered:
                total = triggered_frames
            else:
                total = self.recording.get_write_count() + self.get_recframesize()
            print('Writing: {} of {}'.format(self.get_recframesize(), total))
            if last == self.recording.get_write_count(): double_counter += 1
            if double_counter == 10:
                error = 'Frames cannot be saved.'
                self.emit(QtCore.SIGNAL('Raise Error (PyQt_PyObject)'), error)
                break
            QtCore.QThread.msleep(100)

        self.recording.stop_recording()
        # reset
        self.recframes = deque()

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
        self.context.set_trigger_mode(False, 0, 7, 0, 0)
        self.context.stop_capture()
        self.context.disconnect()
