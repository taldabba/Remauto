import sys
import socket
import selectors
import json
import struct
import io
from time import time
from tokenize import String

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


    def __init__(self, hostMode, addr, port):
        self.selector = selectors.DefaultSelector() # selector
        self.hostMode = hostMode
        self.addr = addr #address
        self.port = port
        self._recv_buffer = b"" #send
        self._send_buffer = b"" #receive
        self._recvMessageBuffer = []
        self._jsonheader_len = None #header length
        self.send_complete = -1 #if we're done with sending a response: -1 means nothing sent, 1 is yes, 0 is no/ 
        self.recv_complete = 0
     
        self._listen()

    def _listen(self):
        if self.hostMode == twoWayConnection.HostMode.SERVER:
            
            self.socket = socket.socket(
                socket.AF_INET, socket.SOCK_STREAM)
            
            #Bind it to the address and port
            self.socket.bind((self.addr, self.port))

            print(f"Listening on {self.addr, self.port}!")
            #Listen for a while
            self.socket.settimeout(120) #120s
            self.socket.listen() #Queue up to x connection requests before denying the rest
            
            # Wait until the client initiates connection
            self.connection, (self.otherAddr, self.otherPort) = self.socket.accept()

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
    def loop(self):
        events = []
        try:
            events = self.selector.select(timeout=100*1e-3) #100ms timeout
        except Exception as e:
            self._closeHandler()

        for key, mask in events:  

            #data is ready to read, send it to the buffer for processing later.
            if mask & selectors.EVENT_READ:

                try:
                    # Check if it's a server
                    if (hasattr(self, 'connection') and self.connection != None):
                        recv_data = self.connection.recv(1024)
                    else:
                        recv_data = self.socket.recv(1024)  # Should be ready to read

                except Exception as e:
                    print(e)
                    recv_data = b""

                debugPrint(f"Received data: {recv_data} {len(recv_data)}")
                               
                # If we received nothing, that meant the host sent nothing, meaning the connection was terminated.
                if recv_data:
                    self._recv_buffer += recv_data
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

    
    def _closeHandler(self):
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
        
        
        try:
            if self.hostMode == twoWayConnection.HostMode.SERVER:
                self.selector.unregister(self.connection)
            else:
                self.selector.unregister(self.socket)
        except Exception as e:
            print(
                f"Error: selector.unregister() exception for "
                f"{self.addr}: {e!r}"
            )

        try:
            if self.hostMode == twoWayConnection.HostMode.SERVER:
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
                
            else:
                self.socket.shutdown(socket.SHUT_RDWR)
                self.socket.close()

        except OSError as e:
            print(f"Error: socket.close() exception for {self.addr}: {e!r}")
        finally:
            # Delete reference to socket object for garbage collection
            self.socket = None
            self.connection = None