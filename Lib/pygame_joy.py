import pygame
import sys

class PygameJoy:
    """
    PygameJoy: A Wrapper for Handling Joysticks with Pygame

    Note: this manages a pygame instance, so is only appropriate for scripts that otherwise don't
    use pygame

    Must call update() to poll update
    """
    def __init__(self, joystick_name=None):
        """
        Initializes the joystick handler. If a joystick name is provided, attempts to find and initialize it.
        Otherwise, the caller can explicitly call prompt_for_joystick().
        """
        pygame.init()
        pygame.joystick.init()
        self.joystick = None

        if joystick_name is not None:
            self._select_joystick_by_name(joystick_name)

    def _select_joystick_by_name(self, joystick_name):
        """Searches for and initializes the joystick with the given name."""
        for i in range(pygame.joystick.get_count()):
            temp_joystick = pygame.joystick.Joystick(i)
            temp_joystick.init()
            if temp_joystick.get_name() == joystick_name:
                self.joystick = temp_joystick
                print(f"Joystick '{joystick_name}' found and initialized.")
                return

        raise ValueError(f"Joystick with name '{joystick_name}' not found.")

    def prompt_for_joystick(self):
        """Prompts the user to select a joystick from available options."""
        num_joysticks = pygame.joystick.get_count()
        if num_joysticks == 0:
            print("No joysticks detected.")
            sys.exit()

        print("Available joysticks:")
        for i in range(num_joysticks):
            temp_joystick = pygame.joystick.Joystick(i)
            temp_joystick.init()
            print(f"{i + 1}. {temp_joystick.get_name()}")

        while True:
            try:
                choice = int(input("Select a joystick by number: ")) - 1
                if 0 <= choice < num_joysticks:
                    self.joystick = pygame.joystick.Joystick(choice)
                    self.joystick.init()
                    print(f"Joystick '{self.joystick.get_name()}' selected.")
                    return
                else:
                    print(f"Invalid choice. Enter a number between 1 and {num_joysticks}.")
            except ValueError:
                print("Please enter a valid number.")

    def get_joystick_id(self):
        """Returns the ID (index) of the currently selected joystick."""
        if self.joystick is None:
            raise RuntimeError("No joystick initialized.")
        return self.joystick.get_instance_id()

    def get_joystick_name(self):
        """Returns the string name of the currently selected joystick."""
        if self.joystick is None:
            raise RuntimeError("No joystick initialized.")
        return self.joystick.get_name()

    def get_axis_value(self, axis_index):
        """Returns the current value of the specified axis."""
        if not self.joystick:
            raise RuntimeError("No joystick initialized. Use prompt_for_joystick() or provide a joystick name.")
        if axis_index >= self.joystick.get_numaxes():
            raise ValueError(f"Axis index {axis_index} out of range for joystick '{self.joystick.get_name()}'.")
        return self.joystick.get_axis(axis_index)

    def get_button_state(self, button_index):
        """Returns the current state of the specified button (1 for pressed, 0 for not pressed)."""
        if not self.joystick:
            raise RuntimeError("No joystick initialized. Use prompt_for_joystick() or provide a joystick name.")
        if button_index >= self.joystick.get_numbuttons():
            raise ValueError(f"Button index {button_index} out of range for joystick '{self.joystick.get_name()}'.")
        return self.joystick.get_button(button_index)

    def get_all_axes(self):
        """Returns a dictionary of all axes and their current values."""
        if not self.joystick:
            raise RuntimeError("No joystick initialized. Use prompt_for_joystick() or provide a joystick name.")
        axes = {i: self.joystick.get_axis(i) for i in range(self.joystick.get_numaxes())}
        return axes

    def get_all_buttons(self):
        """Returns a dictionary of all buttons and their current states."""
        if not self.joystick:
            raise RuntimeError("No joystick initialized. Use prompt_for_joystick() or provide a joystick name.")
        buttons = {i: self.joystick.get_button(i) for i in range(self.joystick.get_numbuttons())}
        return buttons

    def update(self):
        """
        Updates the Pygame event queue to refresh joystick state.
        This must be called periodically by the parent application.
        """
        pygame.event.pump()

    def input_get_axis(self, msg="Move an axis to bind:"):
        """Detects the axis currently being moved on the joystick."""
        baseline = [self.get_axis_value(i) for i in range(self.joystick.get_numaxes())]
        print(msg)
        while True:
            self.update()
            changes = {}
            for i in range(self.joystick.get_numaxes()):
                current_value = self.get_axis_value(i)
                change = abs(current_value - baseline[i])
                if change > 0.1:  # Adjust threshold as needed
                    changes[i] = change

            if changes:
                selected_axis = max(changes, key=changes.get)
                print(f"Axis {selected_axis} activated with value {self.get_axis_value(selected_axis):.2f}.")
                return selected_axis

    def input_get_button(self, msg="Press a button to bind:"):
        """Detects the button currently being pressed on the joystick."""
        baseline = [self.get_button_state(i) for i in range(self.joystick.get_numbuttons())]
        print(msg)
        while True:
            self.update()
            for i in range(self.joystick.get_numbuttons()):
                current_state = self.get_button_state(i)
                if current_state != baseline[i]:
                    print(f"Button {i} pressed. Current state: {current_state}")
                    return i
