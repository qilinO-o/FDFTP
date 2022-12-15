import socket
import threading
#import os
import sys
#import random
import time
import importlib
importlib.reload(sys)
import FDFTPsocket
from const import *
from md5 import get_file_md5

STATE_SS = 1
STATE_CA = 2
STATE_FR = 3

class file_sender:
    def __init__(self, s, to_addr, is_server, seq_to_ack) -> None:
        self.s = s
        self.sender_host = self.s.getsockname()[0]
        self.sender_port = self.s.getsockname()[1]
        self.is_server = is_server
        self.seq_to_ack = seq_to_ack
        #self.seq_base = 0
        
        self.s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, SOCKET_BUF_SIZE)
        self.s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, SOCKET_BUF_SIZE)
        self.lock = threading.Lock()
        self.is_file_open = False
        self.sendto_addr = to_addr
    
    def start(self, filename):
        self.filename = filename
        # open file
        print("# open file")
        try:
            self.file = open(filename,'rb')
            self.is_file_open = True
        except:
            pass
        
        if self.is_file_open == False:
            print('file error: ',filename,'to receiver: ',self.sendto_addr)
            self.s.close()
            return
        else:
            print('start send file: ',filename,'to receiver: ',self.sendto_addr)
        self.Task = FDFTPsocket.Task(filename)

        # shake hand
        print("# shake hand")
        self.s.settimeout(5)
        try:
            if self.is_server == True:
                ack_packet, self.sendto_addr = self.s.recvfrom(ACK_PACKET_SIZE)
            if self.is_server == False:
                self.Task.sendto(self.s, data_packet_struct.pack(*(0,0,0,("upload:"+filename).encode('utf-8'))),self.sendto_addr)
                ack_packet, self.sendto_addr = self.s.recvfrom(ACK_PACKET_SIZE)
                unpacked_ack_packet = ack_packet_struct.unpack(ack_packet)
                self.sendto_addr = (self.sendto_addr[0],unpacked_ack_packet[2])

            self.Task.sendto(self.s, data_packet_struct.pack(*(0,self.seq_to_ack,1,get_file_md5(self.file).encode('utf-8'))), self.sendto_addr)
            
            ack_packet, self.sendto_addr = self.s.recvfrom(ACK_PACKET_SIZE)
            unpacked_ack_packet = ack_packet_struct.unpack(ack_packet)
        except:
            print("connection failed, please try again")
            return
    
        # init some tcp control param
        self.seq_to_ack = int(unpacked_ack_packet[0])
        self.rwnd = int(unpacked_ack_packet[2])
        self.send_queue = []
        self.timer_queue = []
        self.queue_size = 20
        self.send_base = 0
        self.next_seq_num = 0
        self.is_end = False
        self.pipeline_can_send = True
        self.have_timer = False #GBN
        self.cwnd = 1.0
        self.ssthresh = 1024.0
        self.dup_ack_cnt = 0
        self.rtt = 0.2
        self.timer_delay = 1.5 * self.rtt
        self.state = STATE_SS
        self.exit = False
        self.cnt = 0
        self.len = 0

        # start send data and receive ack by thread
        self.send_thread = threading.Thread(target=self.send_data)
        #self.recv_thread = threading.Thread(target=self.recv_ack)
        self.send_thread.start()
        #self.recv_thread.start()
        self.send_thread.join()
        #self.recv_thread.join()
    
    def send_data(self):
        # load file to buffer for MSS split & send
        #self.s.settimeout(0.1)
        print("# load file to buffer for MSS split & send")
        file_buf = []
        file_size = 0
        self.file.seek(0,0)
        while True:
            temp = self.file.read(MSS)
            file_size += len(temp)
            if str(temp) == "b''":
                self.file.close()
                break
            file_buf.append(temp)

        # begin send file from file_buf
        print("# begin send file from file_bufs")
        while True:
            self.lock.acquire()
            if self.is_end == False:
                swnd = min(self.rwnd,int(self.cwnd))
                if self.rwnd == 0:
                    data_pack = data_packet_struct.pack(*(0,0,3,b''))
                    self.Task.sendto(self.s, data_pack, self.sendto_addr)
                else:
                    for i in range(swnd-self.len):
                        if self.is_end == True:
                            break
                        data = file_buf[self.next_seq_num]
                        trans_flag = 1
                        if self.next_seq_num == len(file_buf)-1:
                            self.is_end = True
                            trans_flag = 2
                        data_pack = data_packet_struct.pack(*(self.next_seq_num,self.seq_to_ack,trans_flag,data))
                        self.Task.sendto(self.s, data_pack, self.sendto_addr)
                        t = time.time()
                        self.send_queue.append(data_pack)
                        self.len += 1
                        timer = threading.Timer(interval=self.timer_delay, function=self.retransmit, args=(self.next_seq_num,))
                        self.timer_queue.append((timer,t))
                        timer.start()
                        self.next_seq_num += 1
            self.lock.release()
          
            ack_packet, self.sendto_addr = self.s.recvfrom(ACK_PACKET_SIZE)
            r_seq, r_ack, r_rwnd = ack_packet_struct.unpack(ack_packet)
            #print("     ack:",r_ack)
            if r_seq == 0:
                self.rwnd = r_rwnd
                break

            self.seq_to_ack = r_seq
            self.rwnd = r_rwnd

            # FSM of congestion control
            self.lock.acquire()
            if r_ack >= self.send_base:
                self.handle_new_ack(r_ack)
                # if r_ack == self.next_seq_num-1:
                #     break
            self.lock.release()

                # client send end msg
            if self.exit == True:
                self.Task.finish()
                print("client: ",self.sendto_addr," has received the whole file: ",self.filename, " connection end")
                self.s.close()
                return
            

    def retransmit(self, seq):
        #print("retransmit")
        self.lock.acquire()
        if seq - self.send_base < 0:
            self.lock.release()
            return
        #self.cnt+=1
        #print(self.cnt)
        self.Task.sendto(self.s, self.send_queue[seq - self.send_base], self.sendto_addr)
        timer = threading.Timer(interval=self.timer_delay, function=self.retransmit, args=(seq,))
        self.timer_queue[seq - self.send_base] = (timer,-1)
        timer.start()
        self.ssthresh = max(self.cwnd / 2, 16)
        self.cwnd = 1.0
        self.state = STATE_SS
        self.lock.release() 

    def recv_ack(self):
        while True:
            ack_packet, self.sendto_addr = self.s.recvfrom(ACK_PACKET_SIZE)
            r_seq, r_ack, r_rwnd = ack_packet_struct.unpack(ack_packet)
            #print("     ack:",r_ack)
            self.seq_to_ack = r_seq

            self.lock.acquire()

            self.rwnd = r_rwnd

            # FSM of congestion control
            if self.state == STATE_SS:
                #print("in ss")
                if r_ack >= self.send_base:
                    self.handle_new_ack(r_ack)
                    if self.cwnd < self.ssthresh:
                        self.cwnd += 1  
                    else:
                        self.state = STATE_CA
                else:
                    pass

            elif self.state == STATE_CA:
                #print("in ca")
                if r_ack >= self.send_base:
                    self.handle_new_ack(r_ack)
                    self.cwnd += 1.0 / int(self.cwnd)
                else:
                    pass

            self.lock.release()

            # client send end msg
            if self.exit == True:
                self.Task.finish()
                print("client: ",self.sendto_addr," has received the whole file: ",self.filename, " connection end")
                self.s.close()
                return
                
    def handle_new_ack(self, r_ack): # irralated to congestion strategy
        #print(r_ack)
        if self.state == STATE_SS:
            if self.cwnd < self.ssthresh:
                self.cwnd += 1  
            else:
                self.state = STATE_CA

        elif self.state == STATE_CA:
            self.cwnd += 1.0 / int(self.cwnd)

        if self.timer_queue[r_ack - self.send_base][0] != None:
            self.timer_queue[r_ack - self.send_base][0].cancel()
            if self.timer_queue[r_ack - self.send_base][1] != -1:
                new_rtt = time.time() - self.timer_queue[r_ack - self.send_base][1]
                self.rtt = 0.875 * self.rtt + 0.125 * new_rtt
                self.timer_delay = 1.5 * self.rtt
            self.timer_queue[r_ack - self.send_base] = (None,-1)    
            self.len -= 1

        if r_ack == self.send_base:
            while len(self.timer_queue) != 0 and self.timer_queue[0][0] == None:
                self.send_base += 1
                self.send_queue.pop(0)
                self.timer_queue.pop(0)
            if len(self.timer_queue) == 0 and self.is_end:
                self.exit = True