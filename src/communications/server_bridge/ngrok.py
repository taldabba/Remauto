import platform
import json
from re import sub
import string
import subprocess
import os
import time
import requests


class NgrokConnection:
    def __init__(self, port, timeout=10, ngrok_token=None):   
        assert (isinstance(port, int))
    
        if platform.system() == "Windows":
        # Spawn ngrok subprocess
            if ngrok_token is not None:
                print("Please wait, authenticating ngrok")

                os.system("./communications/server_bridge/ngrok_amd64.exe " +
                    f"config add-authtoken {ngrok_token}")

            
            self.ngrok = subprocess.Popen(["communications\\server_bridge\\ngrok_amd64.exe", "tcp", str(port)],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)

            init_time = time.time()
            self.tunnel_url = None
            while (time.time() - init_time < timeout and self.tunnel_url is None):
            
                try:
                    localhost_url = "http://localhost:4040/api/tunnels" #Url with tunnel details
                
                    res = json.loads(
                        requests.get(localhost_url).text) #Get the tunnel information
                    reslen = len(res)
                    if (reslen != 0):
                        self.tunnel_url = res['tunnels'][0]['public_url'] #Do the parsing of the get
                        assert isinstance(self.tunnel_url, str) # Tunnel url should be a string. Fix it.
                    
                except Exception as err:
                    print("Fucked up trying to get tunnel key")
                    print(err)

                
                # Wait for ngrok to launch, get the forwarding address
                # Check on ngrok in loop()


            # Timeout
            if self.tunnel_url is None:
                self.close()
                raise Exception #TODO: custom exception class for ngrokNotStarted


        else:
            print("Automatic server port-forwarding is not yet supported on this platform. Add it in, or forward manually.")
    
    def get_address(self):
        temp_url = self.tunnel_url.split(":")
        temp_url = temp_url[1].replace("//", "") + "::" + temp_url[2]
        return temp_url

    def close(self):
        self.ngrok.terminate()



