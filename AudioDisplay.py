import sys, os, time
import numpy as np
import matplotlib
# matplotlib.use('Qt4Agg')  # this prevents hickups in new matplotlib versions
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.ticker import MultipleLocator
import matplotlib.pyplot as plt

try:
    from PyQt5 import QtGui, QtCore, QtWidgets
    from PyQt5.QtCore import Qt, pyqtSignal, pyqtSlot
except ImportError, details:
    sys.exit('Unfortunately, your system misses the PyQt5 packages.')

class AudioDisplay(QtWidgets.QGroupBox):
    mutex = QtCore.QMutex()
    sig_start_capture = pyqtSignal()
    sig_stop_capture = pyqtSignal()
    
    def __init__(self, main, source, name, channel_control=False, samplerate=44100, 
        playback=True, parent=None):
        QtWidgets.QGroupBox.__init__(self, name, parent=None)

        # generate layout
        self.setLayout(QtWidgets.QHBoxLayout())
        self.source = source

        # ##############################
        
        self.main = main
        self.source.display = self
        self.debug = self.main.debug
        self.idle_screen = False
        self.audio_diplay_time = 10.
        self.audio_samplerate = samplerate
        self.disp_samplerate = 200

        # bufferqt
        self.audio_t = np.arange(-self.audio_diplay_time, 0., 1./self.audio_samplerate)
        self.audiodata = np.zeros(int(self.audio_t.size), dtype=float)
        self.stepsize = 500
        self.mask = np.zeros(self.audiodata.size, dtype=bool)
        self.mask[::self.stepsize] = 1.
        self.ymax = 1.

        # THE PLOT

        self.figure = plt.figure()
        self.canvas = Canvas(self.figure, parent=self)
        self.layout().addWidget(self.canvas)

        # setup plot
        params = {'axes.labelsize': 22,
                  'font.size': 14,
                  'ytick.labelsize': 16,
                  'xtick.labelsize': 16}
        plt.rcParams.update(params)

        # self.toolbar = NavigationToolbar( self.canvas, parent=self)
        plt.subplots_adjust(left=0., right=1., bottom=0.2, top=1.)
        self.ax = self.figure.add_subplot(111)
        self.ax.set_axis_off()
        # prepare axes
        # self.ax.set_ylim(-1000, 1000)
        self.ax.set_ylim(-self.ymax, self.ymax)
        self.ax.set_xlim(-self.audio_diplay_time-.25, 0.1)
        self.lines, = self.ax.plot(self.audio_t[self.mask], self.audiodata[self.mask], '-', color='k')

        # ##############################
        # buttons and channel control

        optionLayout = QtWidgets.QVBoxLayout()
        self.layout().addLayout(optionLayout)
        # volume buttons
        self.button_audio_plus = QtWidgets.QPushButton('+ Vol')
        self.button_audio_minus = QtWidgets.QPushButton('- Vol')
        optionLayout.addWidget(self.button_audio_plus)
        optionLayout.addWidget(self.button_audio_minus)
        if channel_control:
            spinLayout = QtWidgets.QHBoxLayout()
            optionLayout.addLayout(spinLayout)
            spinLayout.addWidget(QtWidgets.QLabel('Ch.'))
            self.channel_control = QtWidgets.QSpinBox()
            spinLayout.addWidget(self.channel_control)
            self.channel_control.setMinimum(1)
            self.channel_control.setMaximum(1)
            self.channel_control.setEnabled(False)
            self.channel_control.valueChanged.connect(self.channel_changed)
            xy = 80
        else:
            xy = 80

        self.canvas.setMaximumHeight(200)
        self.button_audio_plus.setMinimumHeight(xy)
        self.button_audio_plus.setMaximumWidth(xy)
        self.button_audio_minus.setMinimumHeight(xy)
        self.button_audio_minus.setMaximumWidth(xy)

        # ##############################

        # self.datagrabber = DataGrabber(self)
        # self.threadDisp = QtCore.QThread()
        # self.datagrabber.moveToThread(self.threadDisp)
        # self.main.control.threads.append(self.threadDisp)
        # self.threadDisp.start()

        self.displaytimer = QtCore.QTimer()

        # connections
        self.main.sig_idle_screen.connect(self.set_idle_screen)
        self.button_audio_plus.clicked.connect(self.audio_plus)
        self.button_audio_minus.clicked.connect(self.audio_minus)
        QtCore.QTimer().singleShot(0, self.beautify)

    def start_capture(self):
        self.displaytimer.start(100)
        # self.sig_start_capture.emit()
        # print('display timer started')

    def stop_capture(self):
        self.displaytimer.stop()
        # self.sig_start_capture.emit()
        # print('display timer stopped')

    def beautify(self):
        self.ax.set_axis_on()
        adjust_spines(self.ax, ['bottom'])
        ticks_outward(self.ax)
        self.ax.xaxis.set_major_locator(MultipleLocator(2))

        self.lines, = self.ax.plot(self.audio_t[self.mask], self.audiodata[self.mask], '-', color='k')
        # self.fill_lines = self.ax.fill_between(self.audio_t, self.audiodata, facecolor='k', edgecolor='k')
        self.displaytimer.timeout.connect(self.update_plot)
        self.displaytimer.start(100)

    def update_data(self):
        data = self.source.get_dispdatachunk()
        return  # DEBUG
        if not len(data): return
        # print('audio-display: update_data called')
        data = np.fromstring(np.hstack(data), dtype=np.int16).reshape( -1, 1 )[:,0] / ((2.**16)/2.)
        # to keep the view of the data constant, roll both the data and the mask
        self.mutex.lock()
        self.audiodata = np.roll(self.audiodata, -data.size, axis=-1)
        self.mask = np.roll(self.mask, -data.size, axis=-1)
        self.audiodata[-data.size:] = data
        self.mutex.unlock()

    def update_plot(self):
        if self.debug > 1:
            print('updating audio display')
        if self.idle_screen:
            return
        self.mutex.lock()
        self.lines.set_data(self.audio_t[self.mask], self.audiodata[self.mask])
        self.canvas.draw()
        self.mutex.unlock()

    def reset_plot(self):
        self.audiodata[:] = 0.
        self.update_plot()

    def audio_plus(self):
        if self.debug > 0:
            print('received: audio_plus')
        self.ymax /= 2.
        self.ax.set_ylim(-self.ymax, self.ymax)

    def audio_minus(self):
        if self.debug > 0:
            print('received: audio_plus')

        if self.ymax*2. > 1.:
            self.ymax = 1.
        else:
            self.ymax *= 2.
        self.ax.set_ylim(-self.ymax, self.ymax)


    def set_idle_screen(self, val):
        self.idle_screen = val


class Canvas(FigureCanvas):
    """This is a QWidget (as well as a FigureCanvasAgg, etc.)."""
    def __init__(self, fig, parent=None):
        FigureCanvas.__init__(self, fig)
        FigureCanvas.setSizePolicy(self,
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Expanding)
        FigureCanvas.setMinimumSize(self, 400, 150)
        FigureCanvas.updateGeometry(self)

# class DataGrabber(QtCore.QObject):
#     datatimer = QtCore.QTimer()
#     def __init__(self, display, parent=None):
#         QtCore.QObject.__init__(self, parent)
#         self.display = display
#         self.datatimer.timeout.connect(self.display.update_data)

#     def start_capture(self):
#         self.datatimer.start(200)

#     def stop_capture(self):
#         self.datatimer.stop()


# ######################################################

# HELPERS
from matplotlib import lines as mpllines

def adjust_spines(ax, spines, dropped=False):
    for loc, spine in ax.spines.items():
        if loc in spines:
            if dropped:
                spine.set_position(('outward', 10))  # outward by 10 points
                spine.set_smart_bounds(True)
        else:
            spine.set_color('none')  # don't draw spine

    # turn off ticks where there is no spine
    if 'left' in spines:
        ax.yaxis.set_ticks_position('left')
    else:
        # no yaxis ticks
        plt.setp(ax.get_yticklabels(), visible=False)
        plt.setp(ax.get_yticklines(), visible=False)

    if 'bottom' in spines:
        ax.xaxis.set_ticks_position('bottom')
    else:
        # no xaxis ticks
        plt.setp(ax.get_xticklabels(), visible=False)
        plt.setp(ax.get_xticklines(), visible=False)


def ticks_outward(ax, tickshift = -0.015, two_y_scales=False, pad=8):
    box_off(ax, two_y_scales=two_y_scales)
    for tick in ax.get_yaxis().get_major_ticks():
        tick.set_pad(pad)
    for tick in ax.get_yaxis().get_minor_ticks():
        tick.set_pad(pad)
    for tick in ax.get_xaxis().get_major_ticks():
        tick.set_pad(pad)
    for tick in ax.get_xaxis().get_minor_ticks():
        tick.set_pad(pad)
    for line in ax.get_xticklines():
        line.set_marker(mpllines.TICKDOWN)
    for line in ax.get_yticklines():
        line.set_marker(mpllines.TICKLEFT)
    for line in ax.xaxis.get_minorticklines():
        line.set_marker(mpllines.TICKDOWN)
    for line in ax.yaxis.get_minorticklines():
        line.set_marker(mpllines.TICKLEFT)

def box_off(ax, two_y_scales=False):
    for loc, spine in ax.spines.iteritems():
        if loc in ['left', 'bottom']:
            pass
        elif loc in ['right', 'top']:
            if 'right' and two_y_scales:
                continue
            spine.set_color('none')  # don't draw spine
        else:
            raise ValueError('unknown spine location: %s'%loc)
    ax.xaxis.set_ticks_position('bottom')
    ax.yaxis.set_ticks_position('left')
