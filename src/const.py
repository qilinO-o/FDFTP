import struct

data_packet_struct = struct.Struct('iii1024s') # seq, ack, syn0/trans1/end2, data
ack_packet_struct = struct.Struct('iii') # seq, ack, rwnd
DATA_PACKET_SIZE = 1024+12
ACK_PACKET_SIZE = 12
MSS = 1024 # all window size are per MSS
SOCKET_BUF_SIZE = 1024*1024