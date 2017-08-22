from PyQt5.QtCore import QRect, QPoint
from PyQt5.QtGui import QPainter, QPen, QColor, QBrush
import math
import cv2
import numpy as np


class CalibrationException(Exception):
    pass


class Calibrator:
    def __init__(self, mm_px=1):
        self.enabled = False
        self.mm_px = mm_px
        self.length_to_measure = 'pixel'

    def toggle(self):
        self.enabled = ~self.enabled

    def set_physical_scale(self, measured_distance):
        self.mm_px = measured_distance

    def make_calibration_pattern(self, p, h, w):
        pass


class CrossCalibrator(Calibrator):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.line_length_px = 1
        self.length_to_measure = 'a line in the cross'

    def make_calibration_pattern(self, p, h, w):
        p.setPen(QPen(QColor(255, 0, 0)))
        p.drawRect(QRect(1, 1, w - 2, h - 2))
        p.drawLine(w // 4, h // 2, w * 3 // 4, h // 2)
        p.drawLine(w // 2, h * 3 // 4, w // 2, h // 4)
        p.drawLine(w // 2, h * 3 // 4, w // 2, h // 4)
        p.drawLine(w // 2, h * 3 // 4, w * 3 // 4, h * 3 // 4)
        self.line_length_px = h//2

    def set_physical_scale(self, measured_distance):
        self.mm_px = measured_distance/self.line_length_px


class CircleCalibrator(Calibrator):
    """" Class for a calibration pattern which displays 3 dots in a 30 60 90 triangle
    """
    def __init__(self, *args, dh=80, r=3, **kwargs):
        self.dh = dh
        self.r = r
        self.points = None
        self.points_cam = None
        self.proj_to_cam = None
        self.cam_to_proj = None
        self.length_to_measure = 'the largest distance between the points'

    def make_calibration_pattern(self, p, h, w, draw=True):
        assert isinstance(p, QPainter)

        d2h = self.dh//2
        d2w = int(self.dh*math.sqrt(3))//2
        ch = h//2
        cw = w//2
        # the three points sorted in ascending angle order (30, 60, 90)
        centres = [(cw-d2h, ch+d2w), (cw+d2h, ch+d2w), (cw - d2h, ch - d2w)]
        centres = np.array(centres)
        self.points = centres[np.argsort(CircleCalibrator._find_angles(centres)), :]

        if draw:
            p.setPen(QPen(QColor(255, 0, 0)))
            p.setBrush(QBrush(QColor(255, 0, 0)))
            for centre in centres:
                p.drawEllipse(QPoint(*centre), self.r, self.r)

    def set_physical_scale(self, measured_distance):
        self.mm_px = measured_distance/self.dh

    @staticmethod
    def _find_angles(kps):
        angles = np.empty(3)
        for i, pt in enumerate(kps):
            pt_prev = kps[(i - 1) % 3]
            pt_next = kps[(i + 1) % 3]
            # angles are calculated from the dot product
            angles[i] = np.abs(np.arccos(
                np.sum((pt_prev - pt) * (pt_next - pt)) / np.product(
                    [np.sqrt(np.sum((pt2 - pt) ** 2)) for pt2 in
                     [pt_prev, pt_next]])))
        return angles

    @staticmethod
    def _find_triangle(image, blob_params=None):
        """ Finds the three dots for calibration in the image
        (of a 30 60 90 degree triangle)

        :param image:
        :return: the three triangle points
        """
        if blob_params is None:
            blobdet = cv2.SimpleBlobDetector_create()
        else:
            blobdet = cv2.SimpleBlobDetector_create(blob_params)
        # TODO check if blob detection is robust
        scaled_im = 255 - (image.astype(np.float32)*255/np.max(image)).astype(np.uint8)
        keypoints = blobdet.detect(scaled_im)
        if len(keypoints) != 3:
            raise CalibrationException('3 points for calibration not found')
        kps = np.array([k.pt for k in keypoints])

        # Find the angles between the points
        # and return the points sorted by the angles

        return kps[np.argsort(CircleCalibrator._find_angles(kps)), :]

    def find_transform_matrix(self, image):
        self.points_cam = self._find_triangle(image)
        points_proj = self.points

        x_proj = np.vstack([points_proj.T, np.ones(3)])
        x_cam = np.vstack([self.points_cam.T, np.ones(3)])

        self.proj_to_cam = self.points_cam.T @ np.linalg.inv(x_proj)
        self.cam_to_proj = points_proj.T @ np.linalg.inv(x_cam)
