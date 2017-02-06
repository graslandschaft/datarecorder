import sys, os, time
import pyaudio
import wave
from ctypes import *
from datetime import date, datetime, timedelta
from collections import deque
from matplotlib.dates import date2num

try:
    from PyQt5 import QtGui, QtCore, QtWidgets
    from PyQt5.QtCore import Qt, pyqtSignal, pyqtSlot
except ImportError, details:
    sys.exit('Unfortunately, your system misses the PyQt5 packages.')

def show_available_input_devices():
    audio = pyaudio.PyAudio()
    info = audio.get_host_api_info_by_index(0)
    numdevices = info.get('deviceCount')
    print('\n## Input Devices ##')
    for i in range (0,numdevices):
        if audio.get_device_info_by_host_api_device_index(0,i).get('maxInputChannels')>0:
            chans = audio.get_device_info_by_host_api_device_index(0,i).get('maxInputChannels')
            name = audio.get_device_info_by_host_api_device_index(0,i).get('name')
            print("Input Device id: {} - {} - channels: {}".format(i, name, chans))

class AudioDev(QtCore.QObject):
    # signals
    sig_set_timestamp = pyqtSignal(object)
    sig_raise_error = pyqtSignal(object)
    sig_new_data = pyqtSignal()
    sig_new_meta = pyqtSignal()
    sig_grab_frame = pyqtSignal(object)

    write_counter = 0
    metadata_counter = 0
    sync_counter = 0

    dispdatachunks = deque()
    datachunks = deque()
    metachunks = deque()

    def __init__( self, main, display=None, use_hydro=False, fast_and_small_video=False, 
        triggering=False, channels=1, debug=0, parent=None):
        QtCore.QObject.__init__(self, parent)

        self.mutex = QtCore.QMutex()
        
        self.display = display
        self.triggering = triggering
        self.fast_and_small_video = fast_and_small_video
        self.use_hydro = use_hydro
        self.debug = debug
        self.main = main
        self.filename = 'audio'
        self.audio = pyaudio.PyAudio()
        self.capture_device_name = 'Steinberg UR22'

        self.saving = False
        self.recording = False

        # AUDIO PARAMETERS
        self.fmt = pyaudio.paInt16
        self.channels = channels
        
        if use_hydro:
            self.rate = 44100
        else:
            self.rate = 44100

        if self.fast_and_small_video:
            self.chunk = 1920
            self.trigger_devisor = 1
        else:
            self.chunk = 735
            self.trigger_devisor = 2
            
        self.grabframe_counter = 0
        if self.triggering:
            print('Framerate set to: {:.1f} Hz'.format(self.get_defined_framerate()))

        # timestamps
        self.sig_set_timestamp.connect(main.set_timestamp)
        self.sig_raise_error.connect(main.raise_error)
        # self.connect(self, QtCore.SIGNAL('set timestamp (PyQt_PyObject)'), main.set_timestamp)
        # self.connect(self, QtCore.SIGNAL('Raise Error (PyQt_PyObject)'), main.raise_error)

    def get_input_device_index_by_name(self, devname):
        info = self.audio.get_host_api_info_by_index(0)
        numdevices = info.get('deviceCount')
        for i in range (0,numdevices):
            if self.audio.get_device_info_by_host_api_device_index(0,i).get('maxInputChannels')>0:
                name = self.audio.get_device_info_by_host_api_device_index(0,i).get('name')
                if self.debug > 0:print("Input Device id ", i, " - ", name)
                if devname in name:
                    return i, True
        else:
            return -1, False

    def get_defined_framerate(self):
        return float(self.rate)/float(self.chunk)/float(self.trigger_devisor)

    def set_channels(self, val):
        pass

    def start_capture(self):
        if self.debug > 0:
            print('start capture is called')

        self.recording = True

        # select input device
        index, ok = self.get_input_device_index_by_name(self.capture_device_name)
        if ok:
            self.in_device = self.audio.get_device_info_by_index(index)
        else:
            if self.use_hydro:  # enforce the use of the hydrophone and break if it is not available
                error = 'Audio device not found.'
                error += '\nDevice: {}'.format(self.capture_device_name)
                self.sig_raise_error.emit(error)
                # self.emit(QtCore.SIGNAL('Raise Error (PyQt_PyObject)'), error)
                return
            else:
                try:
                    self.in_device = self.audio.get_default_input_device_info()
                except IOError as ie:
                    print('error: {}'.format(ie))
                    return

        # DROP TIMESTAMP
        timestamp = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
        s = timestamp + ' \t ' + 'selected input device: {}'.format(self.in_device['name'])
        self.sig_set_timestamp.emit(s)
        # self.emit(QtCore.SIGNAL('set timestamp (PyQt_PyObject)'), s)

        # display-device connection: max channels of input device for display button
        if self.display != None:
            maxchan = self.in_device['maxInputChannels']
            self.display.channel_control.setRange(1, maxchan)
            # self.display.channel_control.setEnabled(True)

        print('Number of channels: {}'.format(self.channels))

        # PREPARE RECORDING
        instream = self.audio.open(
                        input_device_index=self.in_device["index"],
                        format=self.fmt, channels=self.channels,
                        rate=self.rate, input=True,
                        frames_per_buffer=self.chunk)

        # send parameters to display
        self.main.audio_disp.set_samplerate(self.rate)

        # print "recording..."
        # for i in range(0, int(rate / chunk * record_seconds)):
        while self.is_recording():
            data = instream.read(self.chunk)
            # self.emit(QtCore.SIGNAL("new data (PyQt_PyObject)"), data)

            # store data for other threads
            self.mutex.lock()
            self.dispdatachunks.append(data)
            self.datachunks.append(data)
            self.mutex.unlock()
            self.sig_new_data.emit()

            # write timestamps for audio-recording
            self.metadata_counter += self.chunk
            self.write_counter += self.chunk
            if self.metadata_counter >= self.rate:
                self.metadata_counter = 0
                # store data for other threads
                self.mutex.lock()
                dtime = '{:.10f}\n'.format(date2num(datetime.now()))
                self.metachunks.append((self.write_counter,dtime))
                self.mutex.unlock()
                self.sig_new_meta.emit()

            if self.triggering:
                # trigger video camera
                sync_counter += 1
                if sync_counter == self.trigger_devisor:
                    if self.is_saving():
                        self.sig_grab_frame.emit(True)
                        # self.emit(QtCore.SIGNAL("grab frame (PyQt_PyObject)"), True)
                        self.update_wakeup_count()
                    else:
                        self.sig_grab_frame.emit(False)
                        # self.emit(QtCore.SIGNAL("grab frame (PyQt_PyObject)"), False)
                    sync_counter = 0

        # stop Recording
        instream.stop_stream()
        instream.close()
        self.audio.terminate()

        if self.debug > 0:
            print('audio finished')

    def is_recording(self):
        self.mutex.lock()
        rec = self.recording
        self.mutex.unlock()
        return rec

    def stop_recording(self):
        if self.debug > 0:
            print('stop recording')
        self.mutex.lock()
        self.recording = False
        self.saving = False
        self.mutex.unlock()

    def is_saving(self):
        self.mutex.lock()
        sav = self.saving
        self.mutex.unlock()
        return sav

    def get_wakeup_count(self):
        self.mutex.lock()
        wc = self.grabframe_counter
        self.mutex.unlock()
        return wc

    def update_wakeup_count(self):
        self.mutex.lock()
        self.grabframe_counter += 1
        self.mutex.unlock()

    def prepare_recording(self, save_dir, file_counter):
        if self.debug > 0:
            print('start saving called')

        self.write_counter = 0
        self.metadata_counter = 0
        self.sync_counter = 0

        self.dispdatachunks = deque()
        self.datachunks = deque()
        self.metachunks = deque()

        self.audioWriter = AudioWriter(self, save_dir, file_counter)
        self.recordingThread = QtCore.QThread()
        self.audioWriter.moveToThread(self.recordingThread)
        self.recordingThread.start()
        self.sig_new_data.connect(self.audioWriter.write)
        self.sig_new_meta.connect(self.audioWriter.write_metadata)

    def start_saving(self):
        self.grabframe_counter = 0

        self.sync_counter = 0
        self.mutex.lock()
        self.saving = True
        self.mutex.unlock()

    def stop_saving(self):
        if self.debug > 0:
            print('stop saving called')

        self.mutex.lock()
        self.saving = False
        self.mutex.unlock()
        
        self.audioWriter.close()
        self.recordingThread.quit()
        self.recordingThread.wait()
        self.audioWriter = None
        self.recordingThread = None

    def get_dispdatachunk(self):
        self.mutex.lock()
        if len(self.dispdatachunks):
            data = self.dispdatachunks.popleft()
            self.mutex.unlock()
            return data
        else:
            self.mutex.unlock()
            return None

    def get_datachunk(self):
        self.mutex.lock()
        if len(self.datachunks):
            data = self.datachunks.popleft()
            self.mutex.unlock()
            return data
        else:
            self.mutex.unlock()
            return None

    def get_metachunk(self):
        self.mutex.lock()
        if len(self.metachunks):
            metadata = self.metachunks.popleft()
            self.mutex.unlock()
            return metadata
        else:
            self.mutex.unlock()
            return None


class AudioWriter(QtCore.QObject):
    # signals
    sig_timestamp = pyqtSignal(object)

    def __init__( self, audiodev, save_dir, file_counter, parent=None):
        QtCore.QObject.__init__(self, parent)

        self.audiodev = audiodev
        self.save_dir = save_dir
        self.filename = audiodev.filename
        channels = audiodev.channels
        sampwidth = audiodev.audio.get_sample_size(audiodev.fmt)
        rate = audiodev.rate
        self.audio = pyaudio.PyAudio()
        self.metawrite_count = 0

        current_fn = '{:04d}__'.format(file_counter) + self.filename + '.wav'
        out_path = os.path.join(self.save_dir, current_fn)

        metadata_fn = '{:04d}__'.format(file_counter) + self.filename + '_timestamps.dat'
        self.metadata_fn = os.path.join(self.save_dir, metadata_fn)

        self.outstream = wave.open(out_path, 'wb')
        self.outstream.setnchannels(channels)
        self.outstream.setsampwidth(sampwidth)
        self.outstream.setframerate(rate)

        self.sig_timestamp.connect(audiodev.main.set_timestamp)
        self.audiodev.sig_new_data.connect(self.write)
        self.audiodev.sig_new_meta.connect(self.write_metadata)
        # self.connect(self.audiodev, QtCore.SIGNAL("new data (PyQt_PyObject)"), self.write)
        # self.connect(self, QtCore.SIGNAL('set timestamp (PyQt_PyObject)'), audiodev.main.set_timestamp)

    def write(self):
        data = self.audiodev.get_datachunk()
        if data is None: return
        self.outstream.writeframes(data)
 
    def write_metadata(self):
        data = self.audiodev.get_metachunk()
        if data is None: return
        writecount, dtime = data
        with open(self.metadata_fn, 'ab') as f:
            f.write('{} {}'.format(writecount, dtime))
            f.flush()

    def close(self):
        while len(self.audiodev.datachunks):
            self.write()
        while len(self.audiodev.metachunks):
            self.write_metadata()

        self.audiodev.sig_new_data.disconnect(self.write)
        # self.disconnect(self.audiodev, QtCore.SIGNAL("new data (PyQt_PyObject)"), self.write)
        self.outstream.close()
        self.outstream = None
