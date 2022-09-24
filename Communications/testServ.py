import comms

conn = comms.twoWayConnection(comms.twoWayConnection.HostMode.SERVER, "127.0.0.1", 65489)

try:
    while True:
        conn.loop()

        message = conn.readMessage()
        if message:    
            print(message)
except KeyboardInterrupt:
    conn.terminate()
    print("Shutting down server. Goodbye!")
