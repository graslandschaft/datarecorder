import sys, os, time
import pyaudio
import wave
import numpy as np
from datetime import date, datetime, timedelta
from collections import deque

try:
    from PyQt5 import QtGui, QtCore, QtWidgets
    from PyQt5.QtCore import Qt, pyqtSignal, pyqtSlot
except ImportError, details:
    sys.exit('Unfortunately, your system misses the PyQt5 packages.')

def show_available_output_devices():
    audio = pyaudio.PyAudio()
    info = audio.get_host_api_info_by_index(0)
    numdevices = info.get('deviceCount')
    print('\n## Output Devices ##')
    for i in range (0,numdevices):
        if audio.get_device_info_by_host_api_device_index(0,i).get('maxOutputChannels')>0:
            chans = audio.get_device_info_by_host_api_device_index(0,i).get('maxOutputChannels')
            name = audio.get_device_info_by_host_api_device_index(0,i).get('name')
            print("Output Device id: {} - {} - channels: {}".format(i, name, chans))

class AudioDevOut(QtCore.QObject):
    # signals
    sig_set_timestamp = pyqtSignal(object)
    sig_raise_error = pyqtSignal(object)
    sig_playback_finished = pyqtSignal()
    sig_new_data = pyqtSignal()

    mutex = QtCore.QMutex()
    dispdatachunks = deque()
    fileindex = 0
    display = None

    def __init__(self, main, debug=0, parent=None):
        """
        Initializes audio output.

        Returns:
            audio: a handle for subsequent calls of play() and close_audio()
        """
        QtCore.QObject.__init__(self, parent)
        self.playing = False
        self.main = main
        self.debug = debug

        self.output_factor = 1.

        # some code to enable audio output
        oldstderr = os.dup( 2 )
        os.close( 2 )
        tmpfile = 'tmpfile.tmp'
        os.open( tmpfile, os.O_WRONLY | os.O_CREAT )
        audio = pyaudio.PyAudio()
        os.close( 2 )
        os.dup( oldstderr )
        os.close( oldstderr )
        os.remove( tmpfile )
        self.audio = audio

        if os.name == 'posix':
            self.output_device_name = 'pulse'
        else:
            self.output_device_name = 'Realtek'

        # timestamps
        self.sig_set_timestamp.connect(main.set_timestamp)
        self.sig_raise_error.connect(main.raise_error)
        # self.connect(self, QtCore.SIGNAL('set timestamp (PyQt_PyObject)'), main.set_timestamp)
        # self.connect(self, QtCore.SIGNAL('Raise Error (PyQt_PyObject)'), main.raise_error)

    def get_output_device_index_by_name(self, devname):
        info = self.audio.get_host_api_info_by_index(0)
        numdevices = info.get('deviceCount')
        for i in range (0,numdevices):
            if self.audio.get_device_info_by_host_api_device_index(0,i).get('maxOutputChannels')>0:
                name = self.audio.get_device_info_by_host_api_device_index(0,i).get('name')
                print( "Output Device id ", i, " - ", name)
                if devname in name:
                    return i, True
        else:
            return -1, False

    def is_playing(self):
        self.mutex.lock()
        playing = self.playing
        self.mutex.unlock()
        return playing

    def stop_playing(self):
        if self.debug > 0:
            print('stop playing')
        self.mutex.lock()
        self.playing = False
        self.mutex.unlock()

    def callback_file(self, in_data, frame_count, time_info, status):
        if not self.is_playing():
            return (None, pyaudio.paComplete)
        if self.fileindex+frame_count < self.audioreader.params['nframes']:
            # read data from file
            data = self.audioreader.readframes(frame_count)
            if data is None: 
                print('End of playback file reached')
                return (None, pyaudio.paComplete)
            self.fileindex += frame_count
            # print('reading', data.shape)

            # store data for other threads
            self.mutex.lock()
            self.dispdatachunks.append(data)
            self.mutex.unlock()

            # control output amplitude
            data  = (data*self.output_factor).astype(np.int16)  ## !!! DEAL WITH TOO LARGE OR SMALL VALUES
            data = data.ravel().tostring()

            return (data, pyaudio.paContinue)
        return (None, pyaudio.paComplete)

    def open(self, filename):
        self.audioreader = AudioReader()
        self.audioreader.open(filename, from_buffer=True)
        params = self.audioreader.getparams()

        self.dispdatachunks = deque()  # container for display data

        self.display.samplerate = self.audioreader.params['rate']

        # select input device
        index, ok = self.get_output_device_index_by_name(self.output_device_name)
        if ok:
            self.out_device = self.audio.get_device_info_by_index(index)
        else:
            self.out_device = self.audio.get_default_output_device_info()

        # DROP TIMESTAMP
        timestamp = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
        s = timestamp + ' \t ' + 'selected output device: {}'.format(self.out_device['name'])
        self.sig_set_timestamp.emit(s)
        # self.emit(QtCore.SIGNAL('set timestamp (PyQt_PyObject)'), s)

        # audio instance
        self.stream = self.audio.open(output_device_index=self.out_device["index"],
            format=pyaudio.paInt16,
            channels=params['nchannels'], rate=params['rate'], output=True, start=False,
            stream_callback=self.callback_file, frames_per_buffer=4096)
        
        self.playing = True
        self.fileindex = 0

    def play(self):
        print('start audio stream')
        # QtCore.QThread.msleep(300)
        self.stream.start_stream()
        while self.stream.is_active():
            QtCore.QThread.msleep(100)  # Qt-function: keeps the thread responsive
        print('audio stream finished')
        self.sig_playback_finished.emit()
        print('audiodevout: playback finished')
        self.stream.stop_stream()
        self.stream.close()
        self.audioreader.close()
        self.audioreader = None

    def close(self):
        self.audio.terminate()

    def get_dispdatachunk(self):
        self.mutex.lock()
        data = [self.dispdatachunks.popleft() for i in xrange(len(self.dispdatachunks))]
        self.mutex.unlock()
        return data

    # def get_dispdatachunk(self):
    #     self.mutex.lock()
    #     if len(self.dispdatachunks):
    #         data = self.dispdatachunks.popleft()
    #         self.mutex.unlock()
    #         return data
    #     else:
    #         self.mutex.unlock()
    #         return None


class AudioReader(QtCore.QObject):
    """ very basic wav-file reader """
    data = None
    from_buffer = False

    def __init__( self, parent=None):
        QtCore.QObject.__init__(self, parent)

    def open(self, filename, from_buffer=False):
        self.from_buffer = from_buffer
        self.wf = wave.open(filename, 'r' )
        (nchannels, sampwidth, rate, nframes, comptype, compname) = self.wf.getparams()

        self.params = dict(nchannels=nchannels,
                           sampwidth=sampwidth,
                           rate=rate,
                           nframes=nframes,
                           comptype=comptype,
                           compname=compname)

        if self.from_buffer:
            self.load_buffer()

    def load_buffer(self):
        # read al data into buffer
        print('pre-loading playback-data')
        buf = self.wf.readframes(self.params['nframes'])
        dformat = 'i%d' % self.params['sampwidth']
        self.data = np.fromstring(buf, dtype=dformat).reshape(-1, self.params['nchannels'])
        self.dx = 0

    def getparams(self):
        return self.params

    def readframes(self, nframes):
        if self.from_buffer:
            if self.dx >= self.params['nframes']:
                self.dx = 0
                return None
            nframes = np.min((nframes, self.params['nframes']-self.dx))
            self.dx += nframes
            return self.data[self.dx:self.dx+nframes,:]
            pass
        else:
            buf = self.wf.readframes(nframes)
            dformat = 'i%d' % self.params['sampwidth']
            return np.fromstring(buf, dtype=dformat).reshape(-1, self.params['nchannels'])

    def close(self):
        self.wf.close()
