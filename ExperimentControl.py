"""
a class for controlling experiments like bulk playbacks of videofiles
"""

import shutil
import os
from datetime import date, datetime, timedelta

try:
    from PyQt5 import QtGui, QtCore, QtWidgets
    from PyQt5.QtCore import Qt, pyqtSignal, pyqtSlot
except ImportError, details:
    sys.exit('Unfortunately, your system misses the PyQt5 packages.')


class ExperimentControl(QtCore.QObject):
    # signals

    save_dir = ''
    exp_running = False
    sig_exp_finished = pyqtSignal()

    def __init__(self, main, debug=0, parent=None):
        QtCore.QObject.__init__(self, parent)
        """
        - redirect start and stop button to experiment control

        - for each list, generate a new output folder
        - read playback file and play files according to list
        - start playback-recording (with or without delay) for each file
        """
        self.main = main
        self.main.default_label_text = 'Experiment mode: press start to run'
        self.main.label_time.setText(self.main.default_label_text)

        # connect to start signals
        # self.main.button_record.clicked.connect(self.clicked_start)
        # self.main.action_start_stop_delayed.triggered.connect(self.clicked_start)
        # self.main.sig_start_experiment.connect(self.clicked_start)

        # read playback file
        # generate and set output directory
        # indicate playback of list: 'experiment mode: press start to run'

    def clicked_start(self):
        self.run_experiment()

    def prepare_experiment(self):
        # read and test all files
        self.playback_files = list()
        with open(self.main.options.audio_playback_list, 'r') as f:
            for line in f.readlines():
                path = line.strip()
                if path[0] == '#': continue
                self.playback_files.append(path)
        files_missing = [f for f in self.playback_files if not os.path.exists(f)]  # check if files exist
        fm = len(files_missing)
        print('\n'+50*'#'+'\n'+'# New playback experiment')
        print('{} of {} files found\n'.format(len(self.playback_files)-fm, len(self.playback_files)))
        if fm > 0:
            for f in files_missing:
                print(f)
            sys.exit('go and check on your files ...')

        # create a new directory for the data
        self.starttime = datetime.now()
        save_dirname = self.starttime.strftime("%Y-%m-%d__%H-%M-%S")
        if self.main.options.output_dir is None:
            self.main.output_dir = os.path.join(self.working_dir, self.main.name+'_experiment_'+ save_dirname)
        else:
            self.main.output_dir = os.path.join(self.main.options.output_dir, self.main.name+'_experiment_'+ save_dirname)

        # create playback directory
        try:
            os.mkdir(self.main.output_dir)
        except:
            print 'start new recording:', self.main.output_dir
            sys.exit('creation of output directory failed')

        # copy playback file to experiment directory for documentation purposes
        shutil.copy2(self.main.options.audio_playback_list, self.main.output_dir)

    def run_experiment(self):
        self.prepare_experiment()

        print('\n'+50*'#'+'\n'+'# Starting Experiment\n')
        self.exp_running = True
        for file in self.playback_files:
            if not self.exp_running: break
            self.main.audio_playback_file = file
            self.main.start_new_recording_session(delay=0, query=False)
            while self.main.saving:
                QtCore.QThread.msleep(100)
            print( self.exp_running)
            QtCore.QThread.msleep(1000)
        self.exp_running = False
        # reset
        self.playback_files = list()
        self.main.audio_playback_file = ''  
        self.sig_exp_finished.emit()
