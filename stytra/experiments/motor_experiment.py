from stytra.experiments.tracking_experiments import TrackingExperiment
from stytra.tracking.tracking_process import TrackingProcessMotor
from stytra.collectors.namedtuplequeue import NamedTupleQueue
from stytra.hardware.motor.motor_process import ReceiverProcess
from stytra.hardware.motor.motor_calibrator import MotorCalibrator
from stytra.calibration import CircleCalibrator,CrossCalibrator, MotorCalibrator
from stytra.collectors import QueueDataAccumulator
from collections import namedtuple


class MotorExperiment(TrackingExperiment):
    """"""
    def __init__(self, *args, **kwargs):
        self.tracked_position_queue = NamedTupleQueue()
        self.calib_queue = NamedTupleQueue()

        super().__init__(*args,calibrator=MotorCalibrator(), **kwargs)

        self.motor_pos_queue = NamedTupleQueue()
        self.motor_status_queue = NamedTupleQueue()

        self.motor_process = ReceiverProcess(
            dot_position_queue=self.tracked_position_queue,
            finished_event=self.camera.kill_event,
            calib_event= self.frame_dispatcher.calibration_event,
            home_event= self.frame_dispatcher.home_event,
            motor_position_queue=self.motor_pos_queue,
            tracking_event=self.frame_dispatcher.tracking_event,
            motor_status_queue = self.motor_status_queue
        )
        self.motor_position_queue = self.motor_process.motor_position_queue

        self.acc_motor = QueueDataAccumulator(
            name="motor",
            experiment=self,
            data_queue=self.motor_position_queue,
            monitored_headers=["x_", "y_"],
        )

        self.gui_timer.timeout.connect(self.acc_motor.update_list)

        self.motor_tracking = False
        # self.recording_event = (
        #     Event() if (recording is not None or recording is False) else None
        # )

    def check_motor_status(self):
        print ("checking status")
        self.motor_status_queue.put(self.motor_tracking)
        return (self.motor_tracking)

    # def check_trigger(self):
    #     self.abort = False
    #     if self.trigger is not None and self.window_main.chk_scope.isChecked():
    #         self.logger.info("Waiting for trigger signal...")
    #         msg = QMessageBox()
    #         msg.setText("Waiting for trigger event...")
    #         msg.setStandardButtons(QMessageBox.Abort)
    #         msg.buttonClicked.connect(self.abort_start)
    #         msg.show()
    #         while True and not self.abort:
    #             if (
    #                 self.trigger.start_event.is_set()
    #                 and not self.protocol_runner.running
    #             ):
    #                 msg.close()
    #                 return
    #             else:
    #                 self.app.processEvents()


    def start_experiment(self):
        super().start_experiment()
        self.motor_process.start()


    def wrap_up(self, *args, **kwargs):
        super().wrap_up(*args, **kwargs)
        self.motor_process.join()


    def initialize_tracking_meth(self):
        self.frame_dispatcher = TrackingProcessMotor(
            second_output_queue=self.tracked_position_queue,
            calib_queue =self.calib_queue,
            in_frame_queue=self.camera.frame_queue,
            finished_signal=self.camera.kill_event,
            pipeline=self.pipeline_cls,
            processing_parameter_queue=self.processing_params_queue,
            output_queue=self.tracking_output_queue,
            recording_signal=self.recording_event,
            gui_framerate=20,
        )

    def refresh_plots(self):
        super().refresh_plots()
        self.window_main.stream_plot.add_stream(self.acc_motor)

    def save_data(self):
        super().save_data()

        if self.acc_motor is not None:
            self.save_log(
                self.acc_motor, "motor_log", "motor"
            )

