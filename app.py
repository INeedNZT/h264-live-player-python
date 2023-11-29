from flask import Flask, render_template
from flask_sock import Sock
from simple_websocket import ConnectionClosed
from time import sleep
import json

import threading
import subprocess

app = Flask(__name__)
sock = Sock(app)

# shared variables for static video
static_socks = []
static_stream_thread = None

# shared variables for ffmpeg
ffmpeg_socks = []
ffmpeg_stream_thread = None

NALseparator = b'\x00\x00\x00\x01'


@app.route('/')
def home_template():
    return render_template('index.html')


@app.route('/static')
def static_template():
    return render_template('static.html')


@app.route('/staticww')
def static_worker_template():
    return render_template('static_ww.html')


@app.route('/ffmpeg')
def ffmpeg_template():
    return render_template('ffmpeg.html')


@app.route('/ffmpegww')
def ffmpeg_worker_template():
    return render_template('ffmpeg_ww.html')


# The implementation logic here is as follows: 
# Once a client starts the video, the server will read the video file and send it to the client.
# Requests from other clients will be ignored, 
# but they will still receive the broadcast. Note this is just for testing purposes.
# NOTE:
# 1. If you play out.h264, for new clients, it is normal to wait for a while before the video is played
# since the SPS frame is sparse, and admiral.264 cannot be played because it is not an h264 baseline profile. 
# 2. If you experience pixelation when pausing and then resuming the video, it is normal because 
# this implementation doesn't truly pause the broadcast (the server continues broadcasting). 
# The image might only return to normal when the next SPS frame is received, but it is rare in this video.
@sock.route('/static')
def static_sock(sock):
    # file_path = "static/samples/admiral.264"
    file_path = "static/samples/out.h264"
    global static_socks

    # the video resolution for out.h264 is 960x540
    options = {
        "width": 960,
        "height": 540
    }
    
    def get_feed():
        with open(file_path, "rb") as h264_file:
            buffer = bytearray()
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
    
    def broadcast_frame():
        for segment in get_feed():
            broadcast(static_socks, segment)

    def start_feed():
        print("Start Feeding...")
        global static_stream_thread
        if static_stream_thread is None or not static_stream_thread.is_alive():
            static_stream_thread = threading.Thread(target=broadcast_frame)
            static_stream_thread.start()
        
    new_client(sock, static_socks, options, start_feed)


# This setup uses FFmpeg to stream from your camera. You can modify the FFmpeg command 
# below to suit your device. It's also important to note that the 'pause' here is not 
# a true pause, as detailed in the NOTE section of the static_sock function.
@sock.route('/ffmpeg')
def ffmpeg_sock(sock):

    # the video resolution my camera is 960x540
    options = {
        "width": 640,
        "height": 480
    }

    # Use your own ffmpeg settings (mine is for mac)
    ffmpeg_command = [
        'ffmpeg',
        '-f', 'avfoundation',
        '-framerate', '30',
        '-video_size', f'{options["width"]}x{options["height"]}',
        '-i', '0',
        '-g', '10',
        '-vcodec', 'libx264',
        '-profile:v', 'baseline',
        '-pix_fmt', 'nv12',
        '-tune', 'zerolatency',
        '-f', 'rawvideo',
        'pipe:1'
    ]

    global ffmpeg_socks

    def start_process():
        process = subprocess.Popen(ffmpeg_command, stdout=subprocess.PIPE)
        return process
    
    def get_feed(ffmpeg_stdout):
        buffer = bytearray()
        while True:
            chunk = ffmpeg_stdout.read(4096)
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

    def broadcast_frame():
        process = start_process()
        for segment in get_feed(process.stdout):
            broadcast(ffmpeg_socks, segment)
            if len(ffmpeg_socks) == 0:
                print("No clients are watching. Stopping FFmpeg stream.")
                process.terminate()
                break
    
    def start_feed():
        print("Start Feeding...")
        global ffmpeg_stream_thread
        if ffmpeg_stream_thread is None or not ffmpeg_stream_thread.is_alive():
            ffmpeg_stream_thread = threading.Thread(target=broadcast_frame)
            ffmpeg_stream_thread.start()
    
    new_client(sock, ffmpeg_socks, options, start_feed)


def broadcast(socks, data):
    for sock in socks:
        try:
            if not sock.pause:
                sock.send(data)
        except Exception as e:
            print(e)
            # ignore the disconnected clients or other issues
            pass

def new_client(sock, socks, options, start_feed):
    try:
        # add an attribute to pause the socket
        # default is False
        sock.pause = False
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
                sock.pause = False
                start_feed()
            elif action == "STOPSTREAM":
                # pause just for this socket
                sock.pause = True

    except ConnectionClosed as e:
        socks.remove(sock)
        print("Client disconnected!")
            


if __name__ == "__main__":
    app.run()
