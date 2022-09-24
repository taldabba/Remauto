from pyPS4Controller.controller import Controller

"""
JOYSTICK RANGE: -32766 --> 32767
"""

class MyController(Controller):

    def __init__(self, **kwargs):
        Controller.__init__(self, **kwargs)

    def on_R3_right(self, value):
        print(super().on_R3_right(value))
        return super().on_R3_right(value)

    def on_x_release(self):
       print("BRAKE")

controller = MyController(interface="/dev/input/js0", connecting_using_ds4drv=False)
# you can start listening before controller is paired, as long as you pair it within the timeout window
controller.listen(timeout=60)