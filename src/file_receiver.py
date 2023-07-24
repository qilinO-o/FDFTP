import socket
import threading
#import os
import sys
#import random
import time
import importlib
importlib.reload(sys)
from const import *
from md5 import get_file_md5

class file_receiver:
    def __init__(self, s, to_addr, is_server) -> None:
        self.s = s
        self.receiver_host = self.s.getsockname()[0]
        self.receiver_port = self.s.getsockname()[1]
        self.is_server = is_server
        self.seq = 0 #x
        self.receive_buf_size = 2048
        self.s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, SOCKET_BUF_SIZE)
        self.s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, SOCKET_BUF_SIZE)
        self.lock = threading.Lock()
        self.is_file_open = False
        self.sendto_addr = to_addr
        self.cnt = 0
    
    def start(self, filename):
        self.filename = filename
        # open file
        try:
            self.file = open("../" + filename,'wb+')
            self.is_file_open = True
        except:
            pass
        if self.is_file_open == False:
            print('file error: ',filename,'from sender: ',self.sendto_addr)
            self.s.close()
            return
        else:
            print('start receive file: ',filename,'from sender: ',self.sendto_addr)

        # shake hand
        self.s.settimeout(5)
        try:
            if self.is_server == False:
                self.s.sendto(data_packet_struct.pack(*(0,0,0,("download:"+filename).encode('utf-8'))),self.sendto_addr)
                ack_packet, self.sendto_addr = self.s.recvfrom(ACK_PACKET_SIZE)
                unpacked_ack_packet = ack_packet_struct.unpack(ack_packet)
                self.sendto_addr = (self.sendto_addr[0],unpacked_ack_packet[2])
                self.s.sendto(ack_packet_struct.pack(*(self.seq,unpacked_ack_packet[0],0)),self.sendto_addr)
                self.seq += 1

            print(self.s.getsockname())
            
            data_packet, self.sendto_addr = self.s.recvfrom(DATA_PACKET_SIZE)
            unpacked_data_packet = data_packet_struct.unpack(data_packet)
        except:
            print("connection failed, please try again")
            return
        
        self.s.sendto(ack_packet_struct.pack(*(self.seq,int(unpacked_data_packet[0])+1,self.receive_buf_size)), self.sendto_addr)
        self.seq += 1

        # init some tcp control param
        self.receive_queue = [None]*self.receive_buf_size
        self.end_seq = -1
        self.target_file_md5 = unpacked_data_packet[3].rstrip(b'\x00').decode('utf-8')
        self.recv_base = 0
        self.write_num = 0
        self.rwnd = self.receive_buf_size

        # start receive data
        self.receive_thread = threading.Thread(target=self.receive_data)
        self.receive_thread.start()
        self.receive_thread.join()

    def receive_data(self):
        self.s.settimeout(5)
        while True:
            try:
                data_packet, self.sendto_addr = self.s.recvfrom(DATA_PACKET_SIZE)
            except socket.timeout:
                break
            
            r_seq, r_len, r_transflag, data = data_packet_struct.unpack(data_packet)

            if r_transflag == 3:
                self.s.sendto(ack_packet_struct.pack(*(self.seq,r_seq,self.rwnd)), self.sendto_addr)
                continue

            self.s.sendto(ack_packet_struct.pack(*(self.seq,r_seq,self.rwnd)), self.sendto_addr)
            self.seq += 1
        
            if r_seq < self.recv_base + self.receive_buf_size and r_seq >= self.recv_base:
                self.receive_queue[r_seq - self.recv_base] = data
                self.rwnd -= 1

            if r_transflag == 2:
                self.end_seq = r_seq
            
            while self.receive_queue[0] != None:
                self.file.write(self.receive_queue[0][0:r_len])
                self.receive_queue.pop(0)
                self.receive_queue.append(None)
                self.recv_base += 1
                self.rwnd += 1

        file_md5 = get_file_md5(self.file)
        if file_md5 != self.target_file_md5:
            print("target md5: ",self.target_file_md5)
            print("get md5: ",file_md5)
            print("file got may be wrong")
        else:
            print("md5 check ok")

        self.s.close()
        self.file.close()
        print("connection end")