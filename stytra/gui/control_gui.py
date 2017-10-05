from PyQt5.QtCore import QRectF, pyqtSignal, Qt
from PyQt5.QtWidgets import QVBoxLayout, QPushButton, QHBoxLayout,\
    QWidget, QLayout, QComboBox, \
    QFileDialog, QLineEdit, QProgressBar, QLabel, QDoubleSpinBox
import pyqtgraph as pg
import numpy as np
import inspect

from stytra.stimulation import protocols, ProtocolRunner


class DebugLabel(QLabel):
    def __init__(self, *args, debug_on=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet('border-radius: 2px')
        self.set_debug(debug_on)
        self.setMinimumHeight(36)

    def set_debug(self, debug_on=False):
        if debug_on:
            self.setText('Debug mode is on, data will not be saved!')
            self.setStyleSheet('background-color: #dc322f;color:#fff')
        else:
            self.setText('Experiment ready, please ensure the metadata is correct')
            self.setStyleSheet('background-color: #002b36')


class ProjectorViewer(pg.GraphicsLayoutWidget):
    def __init__(self, *args, display_size=(1280, 800), ROI_desc=None,  **kwargs):
        super().__init__(*args, **kwargs)

        self.view_box = pg.ViewBox(invertY=True, lockAspect=1,
                                   enableMouse=False)
        self.addItem(self.view_box)

        self.roi_box = pg.ROI(maxBounds=QRectF(0, 0, display_size[0],
                                               display_size[1]),
                              size=ROI_desc['size'],
                              pos=ROI_desc['pos'])
        self.roi_box.addScaleHandle([0, 0], [1, 1])
        self.roi_box.addScaleHandle([1, 1], [0, 0])
        self.view_box.addItem(self.roi_box)
        self.view_box.setRange(QRectF(0, 0, display_size[0], display_size[1]),
                               update=True, disableAutoRange=True)
        self.view_box.addItem(pg.ROI(pos=(1, 1), size=(display_size[0]-1,
                              display_size[1]-1), movable=False,
                                     pen=(80, 80, 80)),
                              )
        self.calibration_points = pg.ScatterPlotItem()
        self.calibration_frame = pg.PlotCurveItem(brush=(120, 10, 10),
                                                  pen=(200, 10, 10),
                                                  fill_level=1)
        self.view_box.addItem(self.calibration_points)
        self.view_box.addItem(self.calibration_frame)

    def display_calibration_pattern(self, calibrator,
                                    camera_resolution=(480, 640),
                                    image=None):
        cw = camera_resolution[0]
        ch = camera_resolution[1]
        points_cam = np.array([[0, 0], [0, cw],
                              [ch, cw], [ch, 0], [0, 0]])

        points_cam = np.pad(points_cam, ((0, 0), (0, 1)),
                            mode='constant', constant_values=1)
        points_calib = np.pad(calibrator.points, ((0, 0), (0, 1)),
                              mode='constant', constant_values=1)
        points_proj = (points_cam @ calibrator.cam_to_proj.T)
        x0, y0 = self.roi_box.pos()
        self.calibration_frame.setData(x=points_proj[:, 0]+x0,
                                       y=points_proj[:, 1]+y0)
        self.calibration_points.setData(x=points_calib[:, 0]+x0,
                                        y=points_calib[:, 1]+y0)
        if image is not None:
            pass
            # TODO place transformed image


class ProtocolDropdown(QComboBox):
    def __init__(self):
        super().__init__()
        prot_classes = inspect.getmembers(protocols, inspect.isclass)

        self.setEditable(False)
        self.prot_classdict = {prot[1].name: prot[1]
                               for prot in prot_classes if issubclass(prot[1],
                                                                      ProtocolRunner)}

        self.addItems(list(self.prot_classdict.keys()))


class ProtocolControlWindow(QWidget):
    sig_calibrating = pyqtSignal()
    sig_closing = pyqtSignal()

    def __init__(self, display_window=None, debug_mode=False, *args):
        """
        Widget for controlling the stimulation.
        :param app: Qt5 app
        :param protocol: Protocol object with the stimulus
        :param display_window: ProjectorViewer object for the projector
        """
        super().__init__(*args)
        self.display_window = display_window
        self.label_debug = DebugLabel(debug_on=debug_mode)

        if self.display_window:
            ROI_desc = self.display_window.params
            self.widget_view = ProjectorViewer(ROI_desc=ROI_desc)
        else:
            self.widget_view = None

        # Widgets for calibration displaying
        self.layout_calibrate = QHBoxLayout()
        self.button_show_calib = QPushButton('Show calibration')
        self.button_calibrate = QPushButton('Calibrate')
        self.label_calibrate = QLabel('size of calib. pattern in mm')
        self.spin_calibrate = QDoubleSpinBox()
        self.layout_calibrate.addWidget(self.button_show_calib)
        self.layout_calibrate.addWidget(self.button_calibrate)
        self.layout_calibrate.addWidget(self.spin_calibrate)
        self.layout_calibrate.addWidget(self.label_calibrate)
        self.layout_calibrate.addWidget(self.spin_calibrate)

        # Widgets for protocol choosing
        self.layout_choose = QHBoxLayout()
        self.combo_prot = ProtocolDropdown()
        self.protocol_params_butt = QPushButton()
        self.layout_choose.addWidget(self.combo_prot)
        self.layout_choose.addWidget(self.protocol_params_butt)

        # Widgets for protocol running
        self.layout_run = QHBoxLayout()
        self.button_toggle_prot = QPushButton("▶")
        self.progress_bar = QProgressBar()
        self.progress_bar.setFormat('%p% %v/%m')
        self.layout_run.addWidget(self.button_toggle_prot)
        self.layout_run.addWidget(self.progress_bar)

        self.button_metadata = QPushButton('Edit metadata')

        self.timer = None
        self.layout = QVBoxLayout()
        for widget in [self.label_debug,
                       self.widget_view,
                        self.layout_choose,
                       self.layout_calibrate, self.layout_run,
                       self.button_metadata]:
            if isinstance(widget, QWidget):
                self.layout.addWidget(widget)
            if isinstance(widget, QLayout):
                self.layout.addLayout(widget)

        self.setLayout(self.layout)
        self.reset_ROI()
        self.widget_view.roi_box.sigRegionChangeFinished.connect(self.refresh_ROI)

    def reset_ROI(self):
        self.widget_view.roi_box.setPos(self.display_window.params['pos'], finish=False)
        self.widget_view.roi_box.setSize(self.display_window.params['size'])
        self.refresh_ROI()

    def refresh_ROI(self):
        if self.display_window:
            self.display_window.set_dims(tuple([int(p) for p in self.widget_view.roi_box.pos()]),
                                         tuple([int(p) for p in self.widget_view.roi_box.size()]))











