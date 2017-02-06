import sys
import os
import numpy as np

# if os.name == 'posix':
#     import subprocess32 as sp
# else:
#     import subprocess as sp
import subprocess as sp
import cPickle as pickle

try:
    from PyQt5 import QtGui, QtCore, QtWidgets
    from PyQt5.QtCore import Qt, pyqtSignal, pyqtSlot
except ImportError, details:
    sys.exit('Unfortunately, your system misses the PyQt5 packages.')

def get_encoder():
    if os.name == 'posix':
        pathlist = ['/usr/bin/avconv', '/usr/bin/ffmpeg']
        for p in pathlist:
            if os.path.exists(p):
                return p
        else:
            sys.exit('No encoder found')
        return p
    else:
        pathlist = ["C:/Program Files/ffmpeg/bin/ffmpeg.exe",
                    "C:/Program Files (x86)/ffmpeg/bin/ffmpeg.exe"]
        for p in pathlist:
            if os.path.exists(p):
                return p
                break
        else:
            sys.exit('No encoder found')
        # self.convert_command = "C:/Program Files/ffmpeg/bin/ffmpeg"
        # self.convert_command = "C:/Program Files (x86)/ffmpeg/bin/ffmpeg"

encoder_path = get_encoder()

class VideoRecording(QtCore.QObject):
    # signals
    sig_set_timestamp = pyqtSignal(object)
    sig_raise_error = pyqtSignal(object)

    def __init__(self, camera, save_dir, file_counter, resolution, fps, 
                 color=False, parent=None):
        QtCore.QObject.__init__(self, parent)

        self.mutex = QtCore.QMutex()
        self.saving = False
        self.camera = camera
        self.save_dir = save_dir
        self.filename = camera.filename
        current_fn = '{:04d}__'.format(file_counter) + self.filename + '.avi'
        out_path = os.path.join(self.save_dir, current_fn)
        metadata_fn = '{:04d}__'.format(file_counter) + self.filename + '_timestamps.dat'
        self.metadata_fn = os.path.join(self.save_dir, metadata_fn)

        self.write_counter = 0
        quality = 2

        # connects
        self.sig_set_timestamp.connect(camera.main.set_timestamp)
        self.sig_raise_error.connect(camera.main.raise_error)
        # self.connect(self, QtCore.SIGNAL('Raise Error (PyQt_PyObject)'), camera.main.raise_error)
        # self.connect(self, QtCore.SIGNAL('set timestamp (PyQt_PyObject)'), camera.main.set_timestamp)

        # homebrew
        self.writer = VideoWriter(out_path, 'XVID', int(fps), resolution, quality, color)
        
        # cv2
        # self.writer = cv2.VideoWriter(out_path, cv2.cv.CV_FOURCC(*'XVID'), int(fps), resolution, color)

    def start_rec(self):
        self.saving = True
        self.continuous_writing()

    def isOpened(self):
        return self.writer.isOpened()

    def get_write_count(self):
        self.mutex.lock()
        wc = self.write_counter
        self.mutex.unlock()
        return wc

    def update_write_count(self):
        self.mutex.lock()
        self.write_counter += 1
        self.mutex.unlock()

    def stop_recording(self):
        self.mutex.lock()
        self.saving = False
        self.mutex.unlock()

    def recording(self):
        self.mutex.lock()
        s = self.saving
        self.mutex.unlock()
        return s

    def write(self):
        # print('rec writing'+str(QtCore.QThread.currentThread()))
        # print('rec writing')
        data = self.camera.get_recframe()
        if data == None:
            QtCore.QThread.msleep(5)
            return
        frame, dtime = data
        self.writer.write(frame)
        self.update_write_count()
        self.write_metadata(dtime)

    def write_metadata(self, current_datetime):
        with open(self.metadata_fn, 'ab') as f:
            f.write(current_datetime)
            f.flush()

    def continuous_writing(self):
        while self.recording():
            self.write()

    def release(self):
        self.writer.release()


class VideoWriter:

    def __init__(self, filename, fourcc='H264', fps=30, frameSize=(640, 480), quality=20, color=False, ffmpeg_path=None):
        
        self.filename = filename

        # check if target file exists; if so: delete it
        if os.path.exists(filename):
            print('file exists: deleting ...')
            os.path.remove(filename)

        self.quality = quality
        self.color = color
        self.fourcc = fourcc
        self.fps = fps
        self.width, self.height = frameSize
        self.depth = 3 if color else 1
        self.proc = None
        self.open()

    def open(self):
        # 4194304 bytes
        cmd = [encoder_path, '-loglevel', 'error',
               '-f', 'rawvideo', '-pix_fmt', 'gray', 
               '-s', '{:d}x{:d}'.format(self.width, self.height),
               '-r', '{:.10f}'.format(self.fps),
               '-i', '-']
        codecs_map = {
            'XVID': 'mpeg4',
            'DIVX': 'mpeg4',
            'H264': 'libx264',
            'MJPG': 'mjpeg',
        }

        if self.fourcc in codecs_map:
            vcodec = codecs_map[self.fourcc]
        else:
            vcodec = self.fourcc
        cmd += ['-vcodec', vcodec, '-preset', 'ultrafast',]

        if self.fourcc == 'XVID':
            # variable bitrate ranging between 1 to 31
            # see: https://trac.ffmpeg.org/wiki/Encode/MPEG-4
            cmd += ['-qscale:v', str(self.quality)]
        
        cmd += [self.filename]
        self.proc = sp.Popen(cmd, stdin=sp.PIPE)

    def isOpened(self):
        return (self.proc != None)

    def write(self, image):
        # if self.color:
        #     if image.shape[1] != self.height or image.shape[0] != self.width or image.shape[2] != self.depth:
        #         raise ValueError('Image dimensions do not match')
        # else:
        #     if image.shape[1] != self.height or image.shape[0] != self.width:
        #         print image.shape, self.height, self.width
        #         raise ValueError('Image dimensions do not match')
        self.proc.stdin.write(image.astype(np.uint8).tostring())
        self.proc.stdin.flush()

    def release(self):
        QtCore.QThread.msleep(100)  # wait for pipe to finish processing
        self.proc.communicate()  # closes pipe
        self.proc = None


