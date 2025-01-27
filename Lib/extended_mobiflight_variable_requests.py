# extended_mobiflight_variable_requests.py - Extends the MobiFlightVariableRequests library to
# support multiple clients
# https://github.com/Koseng/MSFSPythonSimConnectMobiFlightExtension/blob/main/README.md

from ctypes import sizeof
import ctypes
import struct
import time
from ctypes.wintypes import FLOAT
from simconnect_mobiflight.mobiflight_variable_requests import MobiFlightVariableRequests
from simconnect_mobiflight.simconnect_mobiflight import SimConnectMobiFlight
from SimConnect.Enum import SIMCONNECT_CLIENT_DATA_PERIOD, SIMCONNECT_UNUSED

# Borrow 'Mobiclient' idea from 'prototype' version of the library
# https://github.com/Koseng/MSFSPythonSimConnectMobiFlightExtension/blob/main/prototype/mobiflight_variable_requests.py
class MobiClient:

    def __init__(self, client_name):
        self.CLIENT_NAME = client_name
        self.CLIENT_DATA_AREA_LVARS    = None
        self.CLIENT_DATA_AREA_CMD      = None
        self.CLIENT_DATA_AREA_RESPONSE = None
        self.DATA_STRING_DEFINITION_ID = None
    def __str__(self):
        s = f"Name={self.CLIENT_NAME}, LVARS_ID={self.CLIENT_DATA_AREA_LVARS}, CMD_ID={self.CLIENT_DATA_AREA_CMD}, "
        return s + f"RESPONSE_ID={self.CLIENT_DATA_AREA_RESPONSE}, DEF_ID={self.DATA_STRING_DEFINITION_ID}"

class SimVariable:
    def __init__(self, id, name, float_value = 0):
        self.id = id
        self.name = name
        self.float_value = float_value
    def __str__(self):
        return f"Id={self.id}, value={self.float_value}, name={self.name}"

class ExtendedMobiFlightVariableRequests(MobiFlightVariableRequests):
    def __init__(self, simConnect, client_name=None):
        print("ExtendedMobiFlightVariableRequests __init__")
        self.init_ready = False
        self.sm = simConnect
        self.sim_vars = {}
        self.sim_var_name_to_id = {}
        self.FLAG_DEFAULT = 0
        self.FLAG_CHANGED = 1
        self.DATA_STRING_SIZE = 256
        self.DATA_STRING_OFFSET = 0
        self.definition_counter = 0

        self.SIMVAR_DEF_OFFSET = 1000

        self.init_client = MobiClient("MobiFlight")
        self.init_client.CLIENT_DATA_AREA_LVARS = 0
        self.init_client.CLIENT_DATA_AREA_CMD = 1
        self.init_client.CLIENT_DATA_AREA_RESPONSE = 2
        self.init_client.DATA_STRING_DEFINITION_ID = 0

        self.my_client = MobiClient(client_name)
        self.my_client.CLIENT_DATA_AREA_LVARS = 3
        self.my_client.CLIENT_DATA_AREA_CMD = 4
        self.my_client.CLIENT_DATA_AREA_RESPONSE = 5
        self.my_client.DATA_STRING_DEFINITION_ID = 1

        # First add init_client
        self.sm.register_client_data_handler(self.client_data_callback_handler)
        self.initialize_client_data_areas(self.init_client)
        self.send_command("Do Nothing", self.init_client)
        self.send_command(("MF.Clients.Add." + client_name), self.init_client)
        while not self.init_ready:
           time.sleep(0.05)

    def register_client(self):
        print(f"register_client: Registering client '{self.client_name}'")
        self.send_command("Do Nothing")
        self.send_command(f"MF.Clients.Add.{self.client_name}")
        time.sleep(0.1)

    def get(self, variableString):
        client = self.my_client
        if variableString not in self.sim_var_name_to_id:
            # add new variable
            id = len(self.sim_vars) + self.SIMVAR_DEF_OFFSET
            self.sim_vars[id] = SimVariable(id, variableString)
            self.sim_var_name_to_id[variableString] = id
            # subscribe to variable data change
            offset = (id-self.SIMVAR_DEF_OFFSET)*sizeof(FLOAT)
            self.add_to_client_data_definition(id, offset, sizeof(FLOAT))
            self.subscribe_to_data_change(client.CLIENT_DATA_AREA_LVARS, id, id)
            self.send_command(("MF.SimVars.Add." + variableString), client)
        # determine id and return value
        variable_id = self.sim_var_name_to_id[variableString]
        float_value = self.sim_vars[variable_id].float_value
        #print("get: %s. Return=%s", variableString, float_value)
        return float_value

    def set(self, variableString):
        #print("set: %s", variableString)
        self.send_command(("MF.SimVars.Set." + variableString), self.my_client)

    def subscribe_to_mobiflight_response(self):
        definition_id = self.new_definition_id()
        print(f"Subscribing to 'MobiFlight.Response' with Definition ID {definition_id}")
        self.add_to_client_data_definition(definition_id, self.DATA_STRING_OFFSET, self.DATA_STRING_SIZE)
        self.subscribe_to_data_change(2, definition_id, definition_id)

    def client_registration_confirmed(self):
        """Check for confirmation of client registration."""
        for sim_var in self.sim_vars.values():
            if f"MF.Clients.Add.{self.client_name}.Finished" in sim_var.name:
                return True
        return False

    def initialize_client_data_areas(self, client):
        print("Initializing client channels...")
        self.map_client_data_name_to_id(f"{client.CLIENT_NAME}.LVars", client.CLIENT_DATA_AREA_LVARS)
        self.create_client_data(client.CLIENT_DATA_AREA_LVARS, 4096, self.FLAG_DEFAULT)

        self.map_client_data_name_to_id(f"{client.CLIENT_NAME}.Command", client.CLIENT_DATA_AREA_CMD)
        self.create_client_data(client.CLIENT_DATA_AREA_CMD, self.DATA_STRING_SIZE, self.FLAG_DEFAULT)

        self.map_client_data_name_to_id(f"{client.CLIENT_NAME}.Response",client.CLIENT_DATA_AREA_RESPONSE)
        self.create_client_data(client.CLIENT_DATA_AREA_RESPONSE, self.DATA_STRING_SIZE, self.FLAG_DEFAULT)

        self.add_to_client_data_definition(client.DATA_STRING_DEFINITION_ID, self.DATA_STRING_OFFSET, self.DATA_STRING_SIZE)
        self.subscribe_to_data_change(client.CLIENT_DATA_AREA_RESPONSE, client.DATA_STRING_DEFINITION_ID, client.DATA_STRING_DEFINITION_ID)

    def send_command(self, command, client):
        print("send_command: command=%s", command)
        data_byte_array = bytearray(command, "ascii")
        data_byte_array.extend(bytearray(self.DATA_STRING_SIZE - len(data_byte_array)))  # extend to fix DATA_STRING_SIZE
        my_bytes = bytes(data_byte_array)
        self.send_data(client, self.DATA_STRING_SIZE, my_bytes)

    def send_data(self, client, size, dataBytes):
        #print("send_data: client: %s, size=%s, dataBytes=%s", client, size, dataBytes)
        self.sm.dll.SetClientData(
            self.sm.hSimConnect,
            client.CLIENT_DATA_AREA_CMD,
            client.DATA_STRING_DEFINITION_ID,
            self.FLAG_DEFAULT,
            0, # dwReserved
            size,
            dataBytes)

    def client_data_callback_handler(self, callback_data):
        # SimVar Data
        if callback_data.dwDefineID in self.sim_vars:
            data_bytes = struct.pack("I", callback_data.dwData[0])
            float_data = struct.unpack('<f', data_bytes)[0]   # unpack delivers a tuple -> [0]
            self.sim_vars[callback_data.dwDefineID].float_value = round(float_data, 5)
            print("client_data_callback_handler: %s", self.sim_vars[callback_data.dwDefineID])

        # Response string of init_client
        elif callback_data.dwDefineID == self.init_client.DATA_STRING_DEFINITION_ID:
            response =  self._c_string_bytes_to_string(bytes(callback_data.dwData))
            print("client_data_callback_handler: init_client response string: %s", response)
            # Check for response of registering new client
            if (self.my_client.CLIENT_NAME in response):
                self.initialize_client_data_areas(self.my_client)
                self.init_ready = True

        # Response string of my_client
        elif callback_data.dwDefineID == self.my_client.DATA_STRING_DEFINITION_ID:
            response =  self._c_string_bytes_to_string(bytes(callback_data.dwData))
            print("client_data_callback_handler: get my_client response string: %s", response)
        else:
            print("client_data_callback_handler: DefinitionID %s not found!", callback_data.dwDefineID)

    def _c_string_bytes_to_string(self, data_bytes):
        return data_bytes[0:data_bytes.index(0)].decode(encoding='ascii') # index(0) for end of c string

    def map_client_data_name_to_id(self, name, client_data_id):
        print(f"MapClientDataNameToID: {name} {client_data_id}")
        result = self.sm.dll.MapClientDataNameToID(self.sm.hSimConnect, name.encode("ascii"), client_data_id)
        if result != 0:
            raise RuntimeError(f"Failed to map '{name}' to ID {client_data_id}. HRESULT: {result}")

    def create_client_data(self, client_data_id, size, flags):
        print(f"CreateClientData: {client_data_id}")
        result = self.sm.dll.CreateClientData(self.sm.hSimConnect, client_data_id, size, flags)
        if result != 0:
            raise RuntimeError(f"Failed to create ClientData area for ID {client_data_id}. HRESULT: {result}")

    def add_to_client_data_definition(self, definition_id, offset, size):
        print(f"AddToClientDataDefinition: {definition_id}")
        self.sm.dll.AddToClientDataDefinition(self.sm.hSimConnect, definition_id, offset, size, 0, SIMCONNECT_UNUSED)

    def subscribe_to_data_change(self, data_area_id, request_id, definition_id):
        #print(f"RequestClientData: data_area_id={data_area_id}, request_id={request_id}, definition_id={definition_id}")
        result = self.sm.dll.RequestClientData(
            self.sm.hSimConnect,
            data_area_id,
            request_id,
            definition_id,
            SIMCONNECT_CLIENT_DATA_PERIOD.SIMCONNECT_CLIENT_DATA_PERIOD_ON_SET,
            self.FLAG_CHANGED,
            0,
            0,
            0
        )
        if result != 0:
            raise RuntimeError(f"Failed to subscribe to data changes for data_area_id={data_area_id}. HRESULT: {result}")

    def clear_sim_variables(self):
        print("clear_sim_variables")
        self.sim_vars.clear()
        self.sim_var_name_to_id.clear()
        self.send_command("MF.SimVars.Clear", self.my_client)