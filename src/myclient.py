import socket
import threading
import sys
import importlib
importlib.reload(sys)
from file_sender import file_sender
from file_receiver import file_receiver
from const import *

class myclient:
    def __init__(self,to_addr,my_addr) -> None:
        self.to_addr = to_addr
        self.my_addr = my_addr

    def start(self):
        cmd_raw = input("enter cmd, format = cmd:filename > ")
        command, filename = self.parse_cmd(cmd_raw)
        if command == 'download':
            new_s = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
            new_s.bind(self.my_addr)
            fr = file_receiver(new_s,self.to_addr,False)
            fr.start(filename)
        elif command == 'upload':
            new_s = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
            new_s.bind(self.my_addr)
            fs = file_sender(new_s,self.to_addr,False,0)
            fs.start(filename)
        else:
            print('wrong command!')
    
    def parse_cmd(self, data):
        words = data.split(':')
        if len(words) != 2:
            return ('error_cmd', 'error_filename')
        command = words[0]
        filename = words[1]
        return (command, filename)

if __name__ == "__main__":
    # set up server
    mc = myclient(('47.242.76.24',12345),(socket.gethostname(),0)) # to server
    #mc = myclient((socket.gethostname(),12345),(socket.gethostname(),0)) #win to win
    mc.start()