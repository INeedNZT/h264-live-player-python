from flask import Flask, render_template
from flask_sock import Sock
from simple_websocket import ConnectionClosed
from time import sleep
import json

import subprocess

app = Flask(__name__)
sock = Sock(app)
static_socks = []
static_buffer = bytearray()
NALseparator = b'\x00\x00\x00\x01'
options = {
    "width": 960,
    "height": 540
}


@app.route('/')
def home_template():
    return render_template('index.html')


@app.route('/static')
def index_template():
    return render_template('static.html')


@app.route('/staticww')
def worker_template():
    return render_template('static_ww.html')


@sock.route('/static')
def static_sock(sock):
    # file_path = "static/samples/admiral.264"
    file_path = "static/samples/out.h264"


    def start_feed(buffer):
        print("Start feed")
        with open(file_path, "rb") as h264_file:
            while True:
                sleep(0.074)
                chunk = h264_file.read(4096)
                if not chunk:
                    if buffer:
                        yield bytes(buffer)
                    break

                buffer += chunk
                while NALseparator in buffer:
                    position = buffer.index(NALseparator)
                    next_separator_position = buffer.find(NALseparator, position + len(NALseparator))
                    
                    if next_separator_position == -1:
                        break

                    segment = buffer[position:next_separator_position]
                    yield bytes(segment)
                    buffer = buffer[next_separator_position:]
        return

    new_client(sock, static_socks, static_buffer, start_feed)

# TODO: implement ffmpeg
@sock.route('/ffmpeg')
def ffmpeg_sock(sock):

    ffmpeg_command = [
        'ffmpeg',
        '-f', 'avfoundation',
        '-framerate', '30',
        '-video_size', '640x480',
        '-i', '0',
        '-g', '10',
        '-vcodec', 'libx264',
        '-profile:v', 'baseline',
        '-pix_fmt', 'nv12',
        '-tune', 'zerolatency',
        '-f', 'rawvideo',
        'pipe:1'
    ]

    # leftover = b''  # 用于存储上次读取的剩余数据
            # process = subprocess.Popen(ffmpeg_command, stdout=subprocess.PIPE)
            # while True:
            #     # 从 FFmpeg 输出中读取数据
            #     buffer = process.stdout.read(2048)
            #     if not buffer and not leftover:
            #         break
            #
            #     buffer = leftover + buffer  # 将剩余数据与新数据拼接
            #
            #     start = 0
            #     while True:
            #         start_code_index = find_start_code(buffer, start)
            #         if start_code_index < 0:
            #             leftover = buffer[start:] # 保存剩余数据以用于下次拼接
            #             break
            #         next_start_code_index = find_start_code(buffer, start_code_index + 4)
            #         if next_start_code_index < 0:
            #             nal_unit = buffer[start_code_index:]
            #             leftover = nal_unit  # 保存不完整的 NAL 单元以用于下次拼接
            #             break
            #
            #         nal_unit = buffer[start_code_index:next_start_code_index]
            #         nal_type = get_nal_type(nal_unit)
            #         process_nal_unit(nal_type, nal_unit)
            #         sock.send(nal_unit)
            #
            #         start = next_start_code_index
    pass

def broadcast(socks, data):
    for sock in socks:
        sock.send(data)

def new_client(sock, socks, buffer, start_feed):
    try:
        socks.append(sock)
        print("New client connected!")

        sock.send(json.dumps({
            "action": "init",
            "width": options["width"],
            "height": options["height"]
        }))

        while True:
            # waiting for message from ws client
            message = sock.receive()
            print(message)
            action = message.split(' ')[0]
            
            if action == "REQUESTSTREAM":
                if len(buffer) == 0:
                    for segment in start_feed(buffer):
                        broadcast(socks, segment)
                    buffer.clear()  # clear buffer after stream finished
                
                
            elif action == "STOPSTREAM":
                # not implemented yet
                pass
    except ConnectionClosed as e:
        socks.remove(sock)
        print("Client disconnected!")
            


if __name__ == "__main__":
    app.run(debug=True)
