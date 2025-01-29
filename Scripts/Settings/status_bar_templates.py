#  TEMPLATE DOCUMENTATION
# ====================================
#  Template string below defines the content and format of the data shown in the application's window,
#  including dynamic data elements such as:
# ('VAR()' and 'VARIF()' 'functions') and static text.

# Syntax:
# VAR(label, function_name, color)
# - 'label': Static text prefix.
# - 'function_name': Python function to fetch dynamic values.
# - 'color': Text color for label and value.

# VARIF(label, function_name, color, condition_function_name)
# - Same as VAR, but includes:
#   - 'condition_function_name': A Python function that determines if the block should display (True/False).

# Notes:
# - Static text can be included directly in the template.
# - Dynamic function calls in labels (e.g., ## suffix) are supported.
# - VARIF blocks are only displayed if the condition evaluates to True.

# Define your templates here in the TEMPLATES dictionary.

TEMPLATES = {
    "Default": (
        "VAR(Sim:, get_sim_time, yellow) | "
        "VAR(Zulu:, get_real_world_time, white ) |"
        "VARIF(Sim Rate:, get_sim_rate, white, is_sim_rate_accelerated) VARIF(|, '', white, is_sim_rate_accelerated)  " # Use VARIF on | to show conditionally
        "VAR(remain_label##, get_time_to_future_adjusted, red) | "
        "VAR(, get_temp, cyan)"
    ),
    "Altitude and Temp": (
        "VAR(Altitude:, get_altitude, tomato) | "
        "VAR(Temp:, get_temp, cyan)"
    ),
}

# This shows how you can also define your own functions to fetch dynamic values.
# Functions defined here will be imported so they can be referenced
# PLANE_ALTITUDE is a SimConnect variable
# Further SimConnect variables can be found at https://docs.flightsimulator.com/html/Programming_Tools/SimVars/Simulation_Variables.htm
def get_altitude():
    return get_formatted_value("PLANE_ALTITUDE", "{:.0f} ft")

## USER FUNCTIONS ##
# The following functions are hooks for user-defined behaviors and will be called by the
# custom_status_bar script.

# Runs once per display update (approx. 30 times per second).
def user_update():
    pass

# Runs approx every 500ms for less frequent, CPU-intensive tasks.
def user_slow_update():
    pass

# Runs once during startup for initialization tasks.
def user_init():
    pass