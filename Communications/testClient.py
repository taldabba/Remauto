import comms
import time

conn = comms.twoWayConnection(comms.twoWayConnection.HostMode.CLIENT, "localhost::65489")#"2.tcp.ngrok.io::10108")

try: 
    last_message_time = time.perf_counter_ns()
    while True:
        if (time.perf_counter_ns() - last_message_time >= 1e9):
            conn.send("hello world")
            last_message_time = time.perf_counter_ns()

        message = conn.readMessage()
        if (message):
            print((time.perf_counter_ns() - last_message_time)/1e6)

        time.sleep(0)
        


except KeyboardInterrupt:
    conn.terminate()
    print("Exiting. Goodbye!")