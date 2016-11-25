import sys, os, time
import pyaudio
import wave
import numpy as np
from datetime import date, datetime, timedelta

try:
    from PyQt4 import QtGui, QtCore, Qt
except Exception, details:
    print 'Unfortunately, your system misses the PyQt4 packages.'
    quit()

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
    def __init__(self, main, debug=0, parent=None):
        """
        Initializes audio output.

        Returns:
            audio: a handle for subsequent calls of play() and close_audio()
        """
        QtCore.QObject.__init__(self, parent)
        self.mutex = QtCore.QMutex()
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
        self.i = 0

        if os.name == 'posix':
            self.output_device_name = 'pulse'
        else:
            self.output_device_name = 'Realtek'

        # timestamps
        self.connect(self, QtCore.SIGNAL('set timestamp (PyQt_PyObject)'), main.set_timestamp)
        self.connect(self, QtCore.SIGNAL('Raise Error (PyQt_PyObject)'), main.raise_error)

    def get_output_device_index_by_name(self, devname):
        info = self.audio.get_host_api_info_by_index(0)
        numdevices = info.get('deviceCount')
        for i in range (0,numdevices):
            if self.audio.get_device_info_by_host_api_device_index(0,i).get('maxOutputChannels')>0:
                name = self.audio.get_device_info_by_host_api_device_index(0,i).get('name')
                print "Output Device id ", i, " - ", name
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
        if self.i+frame_count < self.audioreader.params['nframes']:
            # read data from file
            data = self.audioreader.readframes(frame_count)
            self.emit(QtCore.SIGNAL("new data (PyQt_PyObject)"), data)
            self.i += frame_count
            # control output amplitude
            data  = (data*self.output_factor).astype(int)
            data = data.ravel().tostring()
            return (data, pyaudio.paContinue)
        print('end of output audio file reached')
        return (None, pyaudio.paComplete)

    def open(self, filename):
        self.audioreader = AudioReader()
        self.audioreader.open(filename)
        params = self.audioreader.getparams()

        self.main.audioout_disp.set_samplerate(self.audioreader.samplerate)

        # select input device
        index, ok = self.get_output_device_index_by_name(self.output_device_name)
        if ok:
            self.out_device = self.audio.get_device_info_by_index(index)
        else:
            self.out_device = self.audio.get_default_output_device_info()

        # DROP TIMESTAMP
        timestamp = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
        s = timestamp + ' \t ' + 'selected output device: {}'.format(self.out_device['name'])
        self.emit(QtCore.SIGNAL('set timestamp (PyQt_PyObject)'), s)

        # audio instance
        self.stream = self.audio.open(output_device_index=self.out_device["index"],
            format=pyaudio.paInt16,
            channels=params['nchannels'], rate=params['rate'], output=True, 
            stream_callback=self.callback_file)

    def play(self):
        # play stream
        self.playing = True
        QtCore.QThread.msleep(200)  # 
        self.stream.start_stream()
        while self.stream.is_active():
            QtCore.QThread.msleep(100)  # Qt-function: keeps the thread responsive
        self.emit(QtCore.SIGNAL("playback finished"))
        self.stream.stop_stream()
        self.stream.close()
        self.audioreader.close()

    def close(self):
        self.audio.terminate()


class AudioReader(QtCore.QObject):
    """ very basic wav-file reader """
    def __init__( self, parent=None):
        QtCore.QObject.__init__(self, parent)

    def open(self, filename):
        self.wf = wave.open(filename, 'r' )
        (nchannels, sampwidth, rate, nframes, comptype, compname) = self.wf.getparams()

        self.params = dict(nchannels=nchannels,
                                   sampwidth=sampwidth,
                                   rate=rate,
                                   nframes=nframes,
                                   comptype=comptype,
                                   compname=compname)

    def getparams(self):
        return self.params

    def readframes(self, nframes):
        buf = self.wf.readframes( nframes )
        dformat = 'i%d' % self.params['sampwidth']
        data = np.fromstring(buf, dtype=dformat).reshape(-1, self.params['nchannels'])
        return data

    def close(self):
        self.wf.close()
