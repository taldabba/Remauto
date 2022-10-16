import subprocess
import os
import time
import json
import requests


#ngrok = subprocess.Popen([f"communications\\server_bridge\\ngrok_amd64.exe", "tcp", "65535"], 
#    stdout=subprocess.PIPE, bufsize=0)

try:
    count = 0
    while count == 0:
        localhost_url = "http://localhost:4040/api/tunnels" #Url with tunnel details
        try:
            tunnel_url = requests.get(localhost_url).text #Get the tunnel information
            j = json.loads(tunnel_url)
            count = len(j)
            if (count != 0):
                tunnel_url = j['tunnels'][0]['public_url'] #Do the parsing of the get

            print(j)
        except Exception as e:
            print(e)
        

    #TODO: Add ngrok into terminate function, begin function. Add error message for when ngrok fucks up.

except Exception as e:
    #ngrok.terminate()
    print(e)

# except KeyboardInterrupt:
#     #ngrok.terminate()


#ngrok.terminate()









