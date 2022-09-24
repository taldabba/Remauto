import comms
import time

conn = comms.twoWayConnection(comms.twoWayConnection.HostMode.CLIENT, "127.0.0.1", 65489)

try: 
    while True:
        conn.loop()
        time.sleep(1)
        conn.send("Hello World!")

except KeyboardInterrupt:
    conn.terminate()
    print("Exiting. Goodbye!")