import comms
from comms import twoWayConnection

conn = comms.twoWayConnection(comms.twoWayConnection.HostMode.SERVER, "127.0.0.1::65489")
print("hi")
ngrokKey = conn.get_ngrok_key()
while (ngrokKey is None):
    ngrokKey = conn.get_ngrok_key()
print(ngrokKey)

try:
    while conn.get_state() > twoWayConnection.State.ERROR:
        message = conn.readMessage()
        if message:    
            conn.send(message)
            print(message)
except KeyboardInterrupt:
    conn.terminate()
    print("Shutting down server. Goodbye!")
