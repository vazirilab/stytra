import numpy as np
from PyQt5.QtGui import QImage, QTransform
import qimage2ndarray
from PyQt5.QtGui import QPainter, QImage, QBrush, QPen, QColor
from PyQt5.QtCore import QPoint, QRect
import cv2
from time import sleep
try:
    from stytra.hardware.serial import PyboardConnection
except ImportError:
    print('Serial pyboard connection not installed')

from itertools import product

class Stimulus:
    """ General class for a stimulus."""
    def __init__(self, duration=0.0):
        """ Make a stimulus, with the basic properties common to all stimuli
        Initial values which do not change during the stimulus
        are prefixed with _, so that they are not logged
        at every time step

        :param duration: duration of the stimulus (s)
        """
        self._started = None
        self.elapsed = 0.0
        self.duration = duration
        self.name = ''

    def get_state(self):
        """ Returns a dictionary with stimulus features
        """
        state_dict = dict()
        for key, value in self.__dict__.items():
            if not callable(value) and key[0] != '_':
                state_dict[key] = value

        return state_dict

    def update(self):
        pass

    def start(self):
        pass


class DynamicStimulus(Stimulus):
    """ Stimuli where parameters change during stimulation, used
    to record form stimuli which react to the fish

    """
    def __init__(self, *args, dynamic_parameters=None, **kwargs):
        """

        :param args:
        :param dynamic_parameters: A list of all parameters that are to be recorded
        :param kwargs:
        """
        super().__init__(*args, **kwargs)
        if dynamic_parameters is None:
            self.dynamic_parameters = []
        else:
            self.dynamic_parameters = dynamic_parameters

    def get_dynamic_state(self):
        return tuple(getattr(self, param, 0) for param in self.dynamic_parameters)


class ImageStimulus(Stimulus):
    """Generic visual stimulus
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def get_image(self, dims):
        pass


class Flash(ImageStimulus):
    """ Flash stimulus
    """
    def __init__(self, *args, color=(255, 255, 255), **kwargs):
        super(Flash, self).__init__(*args, **kwargs)
        self.color = color
        self.name = 'Whole field'
        self._imdata = np.ones(self.output_shape + (3,), dtype=np.uint8) * \
                       np.array(self.color, dtype=np.uint8)[None, None, :]


    def get_image(self, dims):
        self._imdata = np.ones(dims + (3,), dtype=np.uint8) * \
                       np.array(self.color, dtype=np.uint8)[None, None, :]

        return self._imdata


class Pause(Flash):
    def __init__(self, *args, **kwargs):
        super(Pause, self).__init__(*args, color=(0, 0, 0), **kwargs)
        self.name = 'Pause'


class PainterStimulus(Stimulus):
    def paint(self, p, w, h):
        pass


class BackgroundStimulus(Stimulus):
    def __init__(self, *args, background=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.x = 0
        self.y = 0
        self.theta = 0
        self._background = background


class SeamlessStimulus(ImageStimulus, BackgroundStimulus):
    def __init__(self, *args, background=None, **kwargs):
        super().__init__(*args, **kwargs)


    def _transform_mat(self, dims):
        if self.theta == 0:
            return np.array([[1, 0, self.y],
                             [0, 1, self.x]]).astype(np.float32)
        else:
            # shift by x and y and rotate around centre
            xc = dims[1] / 2
            yc = dims[0] / 2
            return np.array([[np.sin(self.theta), np.cos(self.theta),
                              self.y + yc - xc*np.sin(self.theta) - yc * np.cos(self.theta)],
                             [np.cos(self.theta), -np.sin(self.theta),
                              self.x + xc - xc*np.cos(self.theta) + yc * np.sin(self.theta)]]).astype(np.float32)

    def get_image(self, dims):
        self.update()
        to_display = cv2.warpAffine(self._background, self._transform_mat(dims),
                                    borderMode=cv2.BORDER_WRAP,
                                    dsize=dims)
        return to_display


class SeamlessPainterStimulus(PainterStimulus, BackgroundStimulus,
                              DynamicStimulus):
    def __init__(self, *args, dynamic_paramters=['x', 'y', 'theta'],
                 **kwargs):
        super().__init__(*args, **kwargs)
        self._background = qimage2ndarray.array2qimage(self._background)

    def rotTransform(self, w, h):
        xc = -w / 2
        yc = -h / 2
        return QTransform().translate(-xc, -yc).rotate(
            self.theta * 180 / np.pi).translate(xc, yc)

    def paint(self, p, w, h):
        p.setBrush(QBrush(QColor(0, 0, 0)))
        p.drawRect(QRect(-1, -1, w + 2, h + 2))

        display_centre = (w/ 2, h / 2)
        imw = self._background.width()
        imh = self._background.height()
        image_centre = (imw / 2, imh / 2)

        cx = self.x - np.floor(self.x / imw) * imw
        cy = self.y - np.floor(
            self.y / imh) * imh

        dx = display_centre[0] - image_centre[0] + cx
        dy = display_centre[1] - image_centre[1] - cy

        # rotate the coordinate transform around the position of the fish
        p.setTransform(self.rotTransform(w, h))

        for idx, idy in product(range(-1, 2), range(-1, 2)):
            p.drawImage(QPoint(dx + imw * idx,
                               dy + imh * idy), self._background)



class RandomDotKinematogram(PainterStimulus):
    def __init__(self, *args, dot_density, coherence, velocity, direction, **kwargs):
        super().__init__(*args, **kwargs)
        self.dot_density = dot_density
        self.coherence = coherence
        self.velocity = velocity
        self.direction = direction
        self.dots = None

    def paint(self, p, w, h):
        # TODO implement dot painting and update
        pass


class MovingSeamless(SeamlessPainterStimulus):
    def __init__(self, *args, motion=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.motion = motion

    def update(self):
        for attr in ['x', 'y', 'theta']:
            try:
                setattr(self, attr, np.interp(self.elapsed, self.motion.t, self.motion[attr]))
            except (AttributeError, KeyError):
                pass


class MovingConstantly(SeamlessStimulus):
    def __init__(self, *args, x_vel=0, y_vel=0, mm_px=1, monitor_rate=60, **kwargs):
        """
        :param x_vel: x drift velocity (mm/s)
        :param y_vel: x drift velocity (mm/s)
        :param mm_px: mm per pixel
        :param monitor_rate: monitor rate (in Hz)
        """
        super().__init__(*args, **kwargs)
        self.x_vel = x_vel
        self.y_vel = y_vel
        self.x_shift_frame = (x_vel/mm_px)/monitor_rate
        self.y_shift_frame = (y_vel/mm_px)/monitor_rate

    def update(self):
        self.x += self.x_shift_frame
        self.y += self.y_shift_frame




class ClosedLoop1D(SeamlessStimulus, DynamicStimulus):
    def __init__(self, *args, default_velocity,
                 fish_motion_estimator, **kwargs):
        super().__init__(*args, dynamic_parameters=['x', 'vel'], **kwargs)
        self.default_vel = default_velocity
        self.fish_motion_estimator = fish_motion_estimator
        self.vel = 0
        self.past_x = self.x
        self.past_y = self.y
        self.past_theta = self.theta
        self.past_t = 0

    def update(self):
        self.vel = self.default_vel + self.fish_motion_estimator.get_velocity()
        self.x += (self.elapsed-self.past_t) * self.vel

        self.past_t = self.elapsed
        for attr in ['x', 'y', 'theta']:
            try:
                setattr(self, 'past_'+attr, getattr(self, attr))
            except (AttributeError, KeyError):
                pass


class ShockStimulus(Stimulus):
    def __init__(self, burst_freq=100, pulse_amp=3., pulse_n=5,
                 pulse_dur_ms=2, pyboard=None, **kwargs):
        """
        Burst of electric shocks through pyboard (Anki's code)
        :param burst_freq: burst frequency (Hz)
        :param pulse_amp: pulse amplitude (mA)
        :param pulse_n: number of pulses
        :param pulse_dur_ms: pulses duration (ms)
        :param pyboard: PyboardConnection object
        """
        super().__init__(**kwargs)
        self.name = 'shock'
        # assert isinstance(pyboard, PyboardConnection)
        self._pyb = pyboard
        self.burst_freq = burst_freq
        self.pulse_dur_ms = pulse_dur_ms
        self.pulse_n = pulse_n
        self.pulse_amp_mA = pulse_amp

        # Pause between shocks in the burst in ms:
        self.pause = 1000/burst_freq - pulse_dur_ms

        amp_dac = str(int(255*pulse_amp/3.5))
        pulse_dur_str = str(pulse_dur_ms).zfill(3)
        self.mex = str('shock' + amp_dac + pulse_dur_str)

    def start(self):
        for i in range(self.pulse_n):
            self._pyb.write(self.mex)
            print(self.mex)
            #sleep(self.pause/1000)

        self.elapsed = 1


class StopAquisition(Stimulus):
    def __init__(self, zmq_trigger=None, **kwargs):
        super().__init__(**kwargs)
        self.name = 'stop_acquisition'
        self._zmq_trigger = zmq_trigger

    def start(self):
        print('stop')
        self._zmq_trigger.stop()


class StartAquisition(Stimulus):
    def __init__(self, zmq_trigger=None, **kwargs):
        super().__init__(**kwargs)
        self.name = 'start_acquisition'
        self._zmq_trigger = zmq_trigger

    def start(self):
        self._zmq_trigger.start_command()
        print('Acquisition started')


class PrepareAquisition(Stimulus):
    def __init__(self, zmq_trigger=None, **kwargs):
        super().__init__(**kwargs)
        self.name = 'prepare'
        self._zmq_trigger = zmq_trigger

    def start(self):
        self._zmq_trigger.prepare()
        print('Acquisition prepared')


if __name__ == '__main__':
    pyb = PyboardConnection(com_port='COM3')
    # stim = ShockStimulus(pyboard=pyb, burst_freq=100, pulse_amp=3.5,
    #                      pulse_n=5, pulse_dur_ms=2)
    # stim = ShockStimulus(pyboard=pyb, burst_freq=100, pulse_amp=3.5,
    #                      pulse_n=20, pulse_dur_ms=2)
    stim = ShockStimulus(pyboard=pyb, burst_freq=1, pulse_amp=3.5,
                         pulse_n=1, pulse_dur_ms=5)
    stim.start()
    del pyb

