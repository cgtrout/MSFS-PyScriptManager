from simconnect_mobiflight.mobiflight_variable_requests import MobiFlightVariableRequests
from simconnect_mobiflight.simconnect_mobiflight import SimConnectMobiFlight

class ExtendedMobiFlightVariableRequests(MobiFlightVariableRequests):
    def __init__(self, simConnect, client_name):
        super().__init__(simConnect)
        self.client_name = client_name  # Store the client name
        print(f"ExtendedMobiFlightVariableRequests initialized for client: {self.client_name}")

    def send_command(self, command):
        # Prefix all commands with the client name
        client_command = f"{self.client_name}:{command}"
        #print(f"send_command: Sending command: {client_command}")
        data_byte_array = bytearray(client_command, "ascii")
        data_byte_array.extend(bytearray(self.DATA_STRING_SIZE - len(data_byte_array)))  # Pad to the required size
        self.send_data(self.CLIENT_DATA_AREA_CMD, self.DATA_STRING_DEFINITION_ID, self.DATA_STRING_SIZE, bytes(data_byte_array))

    def get(self, variableString):
        #Extend the `get` method to include the client name if necessary
        print(f"get: Requesting variable: {variableString} for client {self.client_name}")
        return super().get(variableString)

    def set(self, variableString):
        # Extend the `set` method to include the client name if necessary
        print(f"set: Setting variable: {variableString} for client {self.client_name}")
        super().set(variableString)

    def register_client(self):
        """Register the client with a unique name."""
        print(f"register_client: Registering client: {self.client_name}")
        self.send_command(f"MF.Clients.Add.{self.client_name}")
        if self.wait_for_response(f"MF.Clients.Add.{self.client_name}.Finished"):
            print(f"Client {self.client_name} registered successfully!")
        else:
            print(f"Failed to register client {self.client_name}.")



