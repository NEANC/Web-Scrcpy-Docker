from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, send
from scrcpy import Scrcpy
import argparse
import queue
# Force inclusion of simple_websocket for threading async_mode in bundled binary
import simple_websocket  # noqa: F401

scpy_ctx = None
client_sid = None
message_queue = queue.Queue()
video_bit_rate = "1024000"

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
# In a bundled binary we likely don't have eventlet/gevent installed; force threading.
socketio = SocketIO(app, async_mode="threading")

@app.route('/')
def index():
    return render_template('index.html')

def video_send_task():
    global client_sid
    while client_sid != None:
        try:
            message = message_queue.get(timeout=0.01)
            socketio.emit('video_data', message, to=client_sid)
        except queue.Empty:
            pass
        except Exception as e:
            print(f"Error sending data: {e}")
        finally:
            socketio.sleep(0.001)
    print(f"video_send_task stopped")

def send_video_data(data):
    message_queue.put(data)

@socketio.on('connect')
def handle_connect():
    global scpy_ctx, client_sid
    print('Client connected')

    if scpy_ctx is not None:
        print(f'reject connection, client {scpy_ctx} is already connected')
        return False
    else:
        client_sid = request.sid
        scpy_ctx = Scrcpy()
        scpy_ctx.scrcpy_start(send_video_data, video_bit_rate)
        socketio.start_background_task(video_send_task)
        print(f'connectioned, client  {scpy_ctx}')

@socketio.on('disconnect')
def handle_disconnect(reason=None):
    """Cleanup scrcpy session when client disconnects."""
    global scpy_ctx, client_sid
    print(f'Client disconnected: {reason}, ctx={scpy_ctx}')
    client_sid = None
    if scpy_ctx is not None:
        try:
            scpy_ctx.scrcpy_stop()
        except Exception as e:
            print(f'scrcpy_stop failed: {e}')
        scpy_ctx = None
    print('scrcpy cleanup done')

@socketio.on('control_data')
def handle_control_data(data):
    global scpy_ctx
    scpy_ctx.scrcpy_send_control(data)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Web server for scrcpy')
    parser.add_argument('--video_bit_rate', default="1024000", help='scrcpy video bit rate')
    parser.add_argument('--port', type=int, default=5000, help='port to bind the web server to')
    args = parser.parse_args()
    video_bit_rate = args.video_bit_rate
    socketio.run(app, host='0.0.0.0', port=args.port)