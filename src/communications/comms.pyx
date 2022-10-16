# TODO: Incorporate doxygen after merge with other branches.

import sys
import os
import threading

# Networking libraries
import socket
import selectors
import io

# Supporting libraries
import json
import struct

# NGrok libraries
from server_bridge.ngrok import NgrokConnection

# Secrets are kept safe using
from dotenv import load_dotenv


from time import time



# Load in secrets, configuration, etc
load_dotenv()
#os.getenv('BLAH BLAH')

MAX_NGROK_WAIT = 10 #10 seconds



debug = False

def debugPrint(message):
    if debug:
        print(message)

# Uses sockets to create a two way parallel connection between two machines.
# Used to send instructions, receive diagnostic data
class twoWayConnection:

    hdrlen = 2

    class HostMode:
        SERVER = 0
        CLIENT = 1

    class State:
        TERMINATED = -1
        ERROR = 0
        LISTENING = 1
        CONNECTED = 2
        STARTING = 3
        RECONNECTING = 4

    def __init__(self, hostMode, addr):
        self.selector = selectors.DefaultSelector() # selector
        self.hostMode = hostMode

        # TODO: Add input verification
        self.addr = addr.split("::")[0] #address
        self.port = int(addr.split("::")[1]) #port
        
        
        self._recv_buffer = b"" #send
        self._send_buffer = b"" #receive
        self._recvMessageBuffer = []
        self._jsonheader_len = None #header length
        self.send_complete = -1 #if we're done with sending a response: -1 means nothing sent, 1 is yes, 0 is no/ 
        self.recv_complete = 0

        # connection (server), socket (client)
        self.connection = None
        self.socket = None


        # Used as an ngrok key
        self._ngrok_token = os.getenv("NGROK_KEY") #TODO: .env it
        self.ngrok = None
        self.running = True

        # Setup threading lock to prevent a read and a write to the state at the same time
        self._state_lock = threading.Lock()
        
        # Setup state, to ensure that the status of the connection can be reported to anything that uses this module
        self._state = self.State.STARTING
        self.init_time = 0


        # Begin new thread using _begin()
        self._background_thread = threading.Thread(target=self._begin)
        self._background_thread.start()



        # self._listen()

    def get_state(self):
        self._state_lock.acquire()
        state = self._state
        self._state_lock.release()
        return state

    def _set_state(self, state):
        self._state_lock.acquire()
        self._state = state
        self._state_lock.release()



    # Function used to spool up thread, internal loop
    def _begin(self):
        # listen
        # # Setup state
        # Begin running
        self._state = self.State.LISTENING
        self._listen()

        while (self.running and self.get_state() > self.State.ERROR):
            self._loop()



    # Spools up server service, ngrok
    # TODO: Set up state machine with states
    def _listen(self):
        if self.hostMode == twoWayConnection.HostMode.SERVER:

            self._set_state(self.State.LISTENING)
            
            self.socket = socket.socket(
                socket.AF_INET, socket.SOCK_STREAM)
            
            #Bind it to the address and port
            self.socket.bind((self.addr, self.port))

            # Spool up ngrok if it's not a thing
            if (self.ngrok is None):
                self.ngrok = NgrokConnection(self.port, ngrok_token=self._ngrok_token)

            print(f"Listening on {self.addr, self.port}!")
            #Listen for a while
            self.socket.settimeout(0.1) #10s

            has_not_connected = True

            while (has_not_connected and self.running):
                try:
                    self.socket.listen() #Queue up to x connection requests before denying the rest
                    
                    # Wait until the client initiates connection
                    self.connection, (self.otherAddr, self.otherPort) = self.socket.accept()

                    has_not_connected = False
                except Exception:
                    pass

                if self.running is False:
                    return

            self.selector.register(self.connection, selectors.EVENT_READ | selectors.EVENT_WRITE, data = "Socket"+str(time()))
            print(f"Accepted connection from {self.otherAddr}::{self.otherPort}. Any others will be rejected.")

        else:
            self.socket = socket.socket(
                socket.AF_INET, socket.SOCK_STREAM)

            self.socket.settimeout(30) #30s
            self.socket.connect((self.addr, self.port))
            print(f"Connecting to ${self.addr}::${self.port}")
            self.selector.register(self.socket, selectors.EVENT_READ | selectors.EVENT_WRITE, data = "Socket")

        # Make socket nonblocking (so that it won't block the loop)
        self.socket.setblocking(0)

        self._set_state(self.State.CONNECTED)

        

    # Reads from the receiving buffer and checks if there's a full message. If not, wait until the next cycle.
    # If so, construct a message and place it in the _recvMessageBuffer.
    def _read(self):

        #Length of receiving buffer
        bufLen = len(self._recv_buffer)

        #Check if we have enough of a message to start out with
        if bufLen < twoWayConnection.hdrlen:
            return

        messageLength = twoWayConnection.hdrlen
        jsonHeaderLength = self._get_protoheader()
        messageLength += jsonHeaderLength

        # Check if we have enough of a message to read the header
        if bufLen < messageLength:
            return

        header = self._process_jsonheader(jsonHeaderLength)
        messageLength += header["content-length"]

        # Check if we have enough of a message to read the full contents
        if bufLen < messageLength:
            return
        
        # Read the whole message into the message buffer, remove the message from the recvbuffer
        message = self._process_message(header, twoWayConnection.hdrlen + jsonHeaderLength)
        self._recv_buffer = self._recv_buffer[messageLength:]

        # If the message is in JSON and we didn't fuck something up real bad, put it on the buffer
        if (message):
            self._recvMessageBuffer.append(message)

        # The buffer should always start with the starting of a full message.()

    def _get_protoheader(self):
        return struct.unpack(
            ">H", self._recv_buffer[:twoWayConnection.hdrlen]
        )[0]
        
    def _process_jsonheader(self, jsonHeaderLength):
        
        if len(self._recv_buffer) >= twoWayConnection.hdrlen + jsonHeaderLength:
            jsonheader = self._json_decode(
                self._recv_buffer[twoWayConnection.hdrlen:twoWayConnection.hdrlen + jsonHeaderLength], "utf-8"
            )
            for reqhdr in (
                "byteorder",
                "content-length",
                "content-type",
                "content-encoding",
            ):
                if reqhdr not in jsonheader:
                    raise ValueError(f"Missing required header '{reqhdr}'.")

            return jsonheader

    def _process_message(self, jsonheader, startoffset):
        content_len = jsonheader["content-length"]
        data = self._recv_buffer[startoffset:content_len + startoffset]

        if jsonheader["content-type"] == "text/json":
            encoding = jsonheader["content-encoding"]
            message = self._json_decode(data, encoding)
            debugPrint(f"Received request {message!r} from {self.addr}")
            return message
        else:
            # Binary or unknown content-type
            message = data
            debugPrint(
                f"Received {jsonheader['content-type']} "
                f"request from {self.addr}"
            )
        # Set selector to listen for write events, we're done reading.


    def _json_encode(self, obj, encoding):
        return json.dumps(obj, ensure_ascii=False).encode(encoding)

    def _json_decode(self, json_bytes, encoding):
        tiow = io.TextIOWrapper(
            io.BytesIO(json_bytes), encoding=encoding, newline=""
        )
        obj = json.load(tiow)
        tiow.close()
        return obj

    # API call to send one message
    def send(self, message):
        self._send_buffer += self._create_message(message)
    
    # API call to read one message
    def readMessage(self):
        if (len(self._recvMessageBuffer) == 0): 
            return 0

        ret = self._recvMessageBuffer[0]
        self._recvMessageBuffer = self._recvMessageBuffer[1:]

        return ret


    # Construct a message, called by send()
    def _create_message(
        self, message, 
    ):
        message = self._create_message_json_content(message)
        message_bytes = message.get("content_bytes")
        jsonheader = {
            "byteorder": sys.byteorder,
            "content-type": message.get("content_type"),
            "content-encoding": message.get("content_encoding"),
            "content-length": len(message_bytes),
        }
        jsonheader_bytes = self._json_encode(jsonheader, "utf-8")
        message_hdr = struct.pack(">H", len(jsonheader_bytes))
        message = message_hdr + jsonheader_bytes + message_bytes
        return message


    # Called by send() to construct the contents of a message
    def _create_message_json_content(self, content):
        content_encoding = "utf-8"
        response = {
            "content_bytes": self._json_encode(content, content_encoding),
            "content_type": "text/json",
            "content_encoding": content_encoding,
        }
        return (response)
            
        
    # Event loop
    def _loop(self):
        events = []
        try:
            events = self.selector.select(timeout=100*1e-3) #100ms timeout
        except Exception as e:
            self._closeHandler()

        read_time = time()
        for key, mask in events:  

            #data is ready to read, send it to the buffer for processing later.
            if mask & selectors.EVENT_READ:

                try:
                    # Check if it's a server
                    if (hasattr(self, 'connection') and self.connection != None):
                        recv_data = self.connection.recv(32768)
                    else:
                        recv_data = self.socket.recv(32768)  # Should be ready to read

                except Exception as e:
                    print(e)
                    recv_data = b""

                debugPrint(f"Received data: {recv_data} {len(recv_data)}")
                               
                # If we received nothing, that meant the host sent nothing, meaning the connection was terminated.
                if recv_data:
                    self._recv_buffer = (b"").join([self._recv_buffer, recv_data]) # Fast string concat optimization
                else:
                    self._closeHandler()

            #data is ready to be written, write it.
            if (mask & selectors.EVENT_WRITE) and len(self._send_buffer) > 0:
                debugPrint(f"sending {self._send_buffer}")

                if (self.hostMode == twoWayConnection.HostMode.SERVER):
                    sent = self.connection.send(self._send_buffer) 
                else:
                    sent = self.socket.send(self._send_buffer) 
                self._send_buffer = self._send_buffer[sent:]

        #Process inputs
        self._read()

        #print("Reading time: " + str((time() - read_time) * 1000))

        #print("loop time: " + str((time() - self.init_time) * 1000))
        self.init_time = time()

    
    def _closeHandler(self):
        self._set_state(self.State.RECONNECTING)
        print(f"Closing connection to {self.addr}")
        try:
            if self.hostMode == twoWayConnection.HostMode.SERVER and self.connection != None :
                self.selector.unregister(self.connection)

            elif self.socket != None:
                self.selector.unregister(self.socket)

        except Exception as e:
            print(
                f"Error: selector.unregister() exception for "
                f"{self.addr}: {e!r}"
            )

        try:
            #If is client, or server has been abruptly terminated
            if self.hostMode == twoWayConnection.HostMode.CLIENT:
                self.socket.shutdown(socket.SHUT_RDWR)
                self.socket.close()
                
            else:
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()

        except OSError as e:
            print(f"Error: socket.close() exception for {self.addr}: {e!r}")
    

        finally:
            # Delete reference to socket object for garbage collection
            self.socket = None
            self.connection = None

        self._listen()

    def terminate(self):
        
        print(f"Closing connection to {self.addr}")
        self.running = False

        if self._background_thread.is_alive():
            print("Killing background thread")
            self._background_thread.join()
        
        try:
            if self.connection is not None:
                self.selector.unregister(self.connection)
            
            if self.ngrok is not None:
                self.ngrok.close()

            if self.socket is not None:
                self.selector.unregister(self.socket)

        except Exception as error:
            self._set_state(self.State.ERROR)
            print(
                f"Error: selector.unregister() exception for "
                f"{self.addr}: {error!r}"
            )

        try:
            if self.connection is not None:
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
                
            if self.socket is not None:
                self.socket.shutdown(socket.SHUT_RDWR)
                self.socket.close()

        except OSError as err:
            self._set_state(self.State.ERROR)
            print(f"Error: socket.close() exception for {self.addr}: {err!r}")
        finally:
            # Delete reference to socket object for garbage collection
            self.socket = None
            self.connection = None
            self._set_state(self.State.TERMINATED)

    # Get currently used Ngrok key
    # Only really useful to query a server device for the key to hand to a client.
    # If ngrok has not started or has ended, returns None.
    def get_ngrok_key(self):
        if (self.ngrok is None):
            return None

        return self.ngrok.get_address()

    def get_address(self):
        return socket.gethostbyname(socket.gethostname()) + str(self.port)