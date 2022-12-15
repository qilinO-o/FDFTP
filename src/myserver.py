import socket
import threading
import sys
import importlib
importlib.reload(sys)
from file_sender import file_sender
from file_receiver import file_receiver
from const import *

class myserver:
    def __init__(self,ip,port) -> None:
        self.IP = ip
        self.SERVER_PORT = port  
        self.s = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        self.s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, SOCKET_BUF_SIZE)
        self.s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, SOCKET_BUF_SIZE)
        self.s.bind((self.IP, self.SERVER_PORT))
        self.recp_port = 20000
    
    def start(self):
        # listening
        while True:
            cmd_data, client_addr = self.s.recvfrom(DATA_PACKET_SIZE)
            unpacked_cmd_data = data_packet_struct.unpack(cmd_data)
            if unpacked_cmd_data[2] != 0: # not syn
                continue
            commond, filename = self.parse_cmd(unpacked_cmd_data[3])
            filename = filename.rstrip('\x00')
            if commond == 'download':
                print('start send file: ',filename,'to client: ',client_addr)
                new_s = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
                new_s.bind((self.IP,0))
                recp_port = new_s.getsockname()[1]
                self.s.sendto(ack_packet_struct.pack(*(0,0,recp_port)),client_addr)
                t = threading.Thread(target=self.new_sender,args=(new_s,client_addr,int(unpacked_cmd_data[0]),filename))
                t.start()
            elif commond == 'upload':
                print('start receive file: ',filename,'from client: ',client_addr)
                new_s = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
                new_s.bind((self.IP,0))
                recp_port = new_s.getsockname()[1]
                self.s.sendto(ack_packet_struct.pack(*(0,0,recp_port)),client_addr)
                t = threading.Thread(target=self.new_receiver,args=(new_s,client_addr,filename))
                t.start()
            else:
                print('wrong command or parse cmd error from client: ',client_addr)
                continue

    def new_sender(self, s, to_addr, seq_to_ack, filename):
        fs = file_sender(s, to_addr, True, seq_to_ack)
        fs.start(filename)

    def new_receiver(self, s, to_addr, filename):
        fr = file_receiver(s, to_addr, True)
        fr.start(filename)

    def parse_cmd(self, data):
        words = data.decode('utf-8').split(':')
        if len(words) != 2:
            return ('error_cmd', 'error_filename')
        command = words[0]
        filename = words[1].strip('\x00')
        return (command, filename)

if __name__ == "__main__":
    # set up server
    ms = myserver(socket.gethostname(),12345)
    ms.start()