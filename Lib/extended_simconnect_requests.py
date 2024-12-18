from SimConnect.RequestList import AircraftRequests
from SimConnect.RequestList import RequestHelper

# Extended AircraftRequests to include CameraData
class ExtendedAircraftRequests(AircraftRequests):
    def __init__(self, _sm, _time=10, _attempts=10):
        # Call the base class constructor
        super().__init__(_sm, _time, _attempts)

        # Add the CameraData without modifying the base library
        self.CameraData = self.__Camera(_sm, _time, _attempts)
        self.list.append(self.CameraData)
        
    class __Camera(RequestHelper):
        list = {
            "CAMERA_GAMEPLAY_PITCH_YAW:index": [
                "Returns either the pitch (index 0) or the yaw (index 1) of the current gameplay camera.",
                b'CAMERA GAMEPLAY PITCH YAW:index', b'Radians', 'N'
            ],
            "CAMERA_REQUEST_ACTION": [
                "This can be used to have the currently active camera perform a predefined action.",
                b'CAMERA REQUEST ACTION', b'Enum', 'Y'
            ],
            "CAMERA_STATE": [
                "This can be used to get or set the camera 'state', which will be one of the listed enum values.",
                b'CAMERA STATE', b'Enum', 'Y'
            ],
            "CAMERA_SUBSTATE": [
                "This variable can be used to get or set the camera 'sub-state'.",
                b'CAMERA SUBSTATE', b'Enum', 'Y'
            ],
            "CAMERA_VIEW_TYPE_AND_INDEX_MAX:index": [
                "Get the number of option indices related to a specific camera view type.",
                b'CAMERA VIEW TYPE AND INDEX MAX:index', b'Number', 'Y'
            ],
            "CAMERA_VIEW_TYPE_AND_INDEX:index": [
                "Get or set both the type of view for the current camera, as well as the option index.",
                b'CAMERA VIEW TYPE AND INDEX:index', b'Enum', 'Y'
            ],
            "GAMEPLAY_CAMERA_FOCUS": [
                "This gets/sets the focus for the camera zoom.",
                b'GAMEPLAY CAMERA FOCUS', b'Number', 'Y'
            ],
            "IS_CAMERA_RAY_INTERSECT_WITH_NODE": [
                "Check for a collision along a ray from the center of the user FOV and a model node.",
                b'IS CAMERA RAY INTERSECT WITH NODE', b'Bool', 'N'
            ],
        }
