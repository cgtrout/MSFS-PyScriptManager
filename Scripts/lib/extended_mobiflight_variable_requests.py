from simconnect_mobiflight.mobiflight_variable_requests import MobiFlightVariableRequests
from simconnect_mobiflight.simconnect_mobiflight import SimConnectMobiFlight

class ExtendedMobiFlightVariableRequests(MobiFlightVariableRequests):
    def __init__(self, simConnect, client_name):
        print("ExtendedMobiFlightVariableRequests __init__")
        # Directly copy the parent class __init__ logic here
        self.sm = simConnect
        self.sim_vars = {}
        self.sim_var_name_to_id = {}
        self.CLIENT_DATA_AREA_LVARS    = 0
        self.CLIENT_DATA_AREA_CMD      = 1
        self.CLIENT_DATA_AREA_RESPONSE = 2
        self.FLAG_DEFAULT = 0
        self.FLAG_CHANGED = 1
        self.DATA_STRING_SIZE = 256
        self.DATA_STRING_OFFSET = 0
        self.DATA_STRING_DEFINITION_ID = 0
        self.sm.register_client_data_handler(self.client_data_callback_handler)

        # Set client_name AFTER parent initialization logic
        self.client_name = client_name  
        self.register_client()  # Custom method for child
        self.initialize_client_data_areas()  # Safe to call now
        print(f"ExtendedMobiFlightVariableRequests initialized for client: {self.client_name}")

    def get(self, variableString):
        #Extend the `get` method to include the client name if necessary
        #print(f"get: Requesting variable: {variableString} for client {self.client_name}")
        ret_val = super().get(variableString)
        #print(f"get: returned-> {ret_val}")
        return ret_val

    def set(self, variableString):
        # Extend the `set` method to include the client name if necessary
        #print(f"set: Setting variable: {variableString} for client {self.client_name}")
        super().set(variableString)

    # Overide client name with name of our client registered on Mobiflight
    def initialize_client_data_areas(self):
        # register client data area for receiving simvars
        self.sm.dll.MapClientDataNameToID(self.sm.hSimConnect, f"{self.client_name}.LVars".encode("ascii"), self.CLIENT_DATA_AREA_LVARS)
        self.sm.dll.CreateClientData(self.sm.hSimConnect, self.CLIENT_DATA_AREA_LVARS, 4096, self.FLAG_DEFAULT)
        # register client data area for sending commands
        self.sm.dll.MapClientDataNameToID(self.sm.hSimConnect, f"{self.client_name}.Command".encode("ascii"), self.CLIENT_DATA_AREA_CMD)
        self.sm.dll.CreateClientData(self.sm.hSimConnect, self.CLIENT_DATA_AREA_CMD, self.DATA_STRING_SIZE, self.FLAG_DEFAULT)
        # register client data area for receiving responses
        self.sm.dll.MapClientDataNameToID(self.sm.hSimConnect, f"{self.client_name}.Response".encode("ascii"), self.CLIENT_DATA_AREA_RESPONSE)
        self.sm.dll.CreateClientData(self.sm.hSimConnect, self.CLIENT_DATA_AREA_RESPONSE, self.DATA_STRING_SIZE, self.FLAG_DEFAULT)
        # subscribe to WASM Module responses
        self.add_to_client_data_definition(self.DATA_STRING_DEFINITION_ID, self.DATA_STRING_OFFSET, self.DATA_STRING_SIZE)
        self.subscribe_to_data_change(self.CLIENT_DATA_AREA_RESPONSE, self.DATA_STRING_DEFINITION_ID, self.DATA_STRING_DEFINITION_ID)

    # Add client to mobiflight
    def register_client(self):
        """Register the client with a unique name."""
        print(f"register_client: Registering client: {self.client_name}")
        self.send_command(f"MF.Clients.Add.{self.client_name}")



