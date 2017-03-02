"""
a class for connecting gui, hardware and experiments
"""

import shutil
import os
import sys

try:
    from PyQt5 import QtGui, QtCore, QtWidgets
    from PyQt5.QtCore import Qt, pyqtSignal, pyqtSlot
except ImportError, details:
    sys.exit('Unfortunately, your system misses the PyQt5 packages.')

from AudioDev import AudioDev
from AudioDevOut import AudioDevOut

from cameramodules import *
from Camera_dummy import Camera as DummyCamera
if camera_modules['opencv']:
    from Camera_cv import Camera as CvCamera
if camera_modules['pointgrey']:
    from Camera_pointgrey import Camera as pgCamera
    from Camera_pointgrey import get_available_flycap_cameras

from ExperimentControl import ExperimentControl

class Devices(QtCore.QObject):
    audiodev = None
    audiodevout = None
    cameras = dict()  # container for cameras
    camera_threads = dict()

    def __init__(self, control, parent=None,
            audio_input=True, audio_output=False, video_input=False):
        QtCore.QObject.__init__(self, parent)

        self.control = control
        self.cfg = control.cfg

        # init
        if control.cfg['audio_input']:
            self.init_audio_input()
        if control.cfg['audio_output']:
            self.init_audio_output()
        if control.cfg['video_input']:
            self.init_video_input()

    def init_audio_input(self):
        # Audio Input
        self.audiodev = AudioDev(self.control)
        self.threadAudio = QtCore.QThread(self)
        self.audiodev.moveToThread(self.threadAudio)
        self.control.threads.append(self.threadAudio)
        self.threadAudio.start()

        # start stop
        self.control.sig_start_saving.connect(self.audiodev.start_saving)
        self.control.sig_start_capture.connect(self.audiodev.start_capture)

        print('audio input initialized')

    def init_audio_output(self):
        # Audio Output
        self.audiodevout = AudioDevOut(self.control)
        self.threadAudioOut = QtCore.QThread(self)
        self.audiodevout.moveToThread(self.threadAudioOut)
        self.control.threads.append(self.threadAudioOut)
        self.threadAudioOut.start()

        self.control.sig_start_playback.connect(self.audiodevout.play)
        self.audiodevout.sig_playback_finished.connect(self.control.playback_finished)
        print('audio output initialized')

    def init_video_input(self):
        # Video
        if self.control.main.debug:
                cam = DummyCamera(self.control)
                cam.name = 'DummyCam'
                self.cameras[cam.name] = cam

        elif self.control.cfg['pointgrey']:
            if not camera_modules['pointgrey']:
                sys.exit('No Pointgrey-camera found')
            cam_num = get_available_flycap_cameras()
            print('Number of flycap-cameras: {}'.format(cam_num))

            # put cameras into dictionary
            for j in xrange(cam_num):
                cam = pgCamera(self.control, j, fast_and_small_video=self.control.cfg['fast_and_small_video'],
                             triggered=self.control.cfg['trigger'])
                cam.name = str(j)
                self.cameras[str(j)] = cam 

        else:
            if not camera_modules['opencv']:
                sys.exit('No OpenCV-cameras found')
            camera_device_search_range = range(0, 20)
            camera_name_format = 'cv_camera%02i'
            cams = [CvCamera(self.control, device_no=i) for i in camera_device_search_range]
            tmp = [cam for cam in cams if cam.is_working()]
            # tmp = [cam for cam in [CvCamera(self.control, device_no=i) for i in camera_device_search_range] if cam.is_working()]

            # put cameras into dictionary
            for j, cam in enumerate(tmp):
                cam.name = camera_name_format % j
                self.cameras[cam.name] = cam

        # create threads for cameras
        for cam_name, cam in self.cameras.items():
            self.camera_threads[cam_name] = QtCore.QThread()
            cam.moveToThread(self.camera_threads[cam_name])
            self.camera_threads[cam_name].start()
            self.control.threads.append(self.camera_threads[cam_name])
            
            # connections
            self.control.sig_start_capture.connect(cam.start_capture)
            self.control.sig_start_recordings.connect(cam.new_recording)
            self.control.sig_stop_recordings.connect(cam.stop_saving)
            print('cam: {} connected'.format(cam_name))


        print('video input initialized')

    def connect_trigger(self):
        # connect cameras to audio trigger
        if self.control.triggered_video:
            for cam_name, cam in self.cameras.items():
                self.audiodev.sig_grab_frame.connect(cam.grab_frame)
        else:
            for cam_name, cam in self.cameras.items():
                self.sig_start_capture.connect(cam.start_capture)


