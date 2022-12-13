#-*-coding: utf-8-*-
from flask import *
from flask import request, render_template
from flask_socketio import SocketIO
import json, os, pygame, random
from mutagen.mp3 import MP3
from shutil import copyfile
from copy import deepcopy
from multiprocessing import Process, Value, Manager
from datetime import datetime

app=Flask(__name__, static_url_path='', static_folder='static')
app.config['SECRET_KEY'] = 'gsa'
socketio = SocketIO(app)

category = ['발라드', '랩', '팝송', 'K-POP', 'jazz', '비오는 날', '카페', '신나는 노래', '감성 노래', 'all']

# status
# 0 아무 상태 아님
# 1 재생중
# 2 중지중
# 3 재생 요청
# 4 중지 -> 재생 요청
# 5 중지 요청
# 6 모든 상태를 종료하고 0으로 바꿔라

def get_length(cur):
    global playlist
    song_name = playlist[cur]
    audio = MP3(f'audio_data/all/{song_name}')
    return audio.info.length

@app.route('/api', methods = ['POST'])
def upload_file():
    global song_data, cur, playlist, status
    type = request.form.get('type')
    if type == 'upload':
        get_category = request.form.get('category')
        if get_category != None:
            files = request.files
            try:
                dict_category = json.loads(get_category)
                for i in files:
                    file = files[i]
                    if file.filename in dict_category:
                        file.save(f'audio_data/all/{file.filename}')
                        if file.filename not in song_data['all']:
                            song_data['all'].append(file.filename)
                        for file_category in dict_category[file.filename]:
                            copyfile(f'audio_data/all/{file.filename}', f'audio_data/{file_category}/{file.filename}')
                            if file.filename not in song_data[file_category]:
                                song_data[file_category].append(file.filename)
                    else:
                        return {'type': 'error', 'message': 'data is wrong'}
            except json.decoder.JSONDecodeError:
                return {'type': 'error', 'message': 'data is not json'}
            return {'type': 'success', 'message': 'files upload success!'}
        else:
            return {'type': 'error', 'message': 'cannot received file!'}
    elif type == 'select_playlist':
        value = request.form.get('value')
        if value == None or value == '':
            return {'type': 'error', 'message': 'no have value parameter'}
        else:
            if value in category:
                return {'type': 'success', 'message': 'playlist select success!', 'list': list(song_data[value])}
            else:
                return {'type': 'error', 'message': f'no have {value} category'}
    elif type == 'remove_song':
        value = request.form.get('value')
        song_name = request.form.get('song_name')
        if value == None or value == '':
            return {'type': 'error', 'message': 'no have value parameter'}
        elif song_name == None or song_name == '':
            return {'type': 'error', 'message': 'no have song_name parameter'}
        else:
            if value in category:
                if song_name in song_data[value]:
                    if value == 'all':
                        for i in category:
                            if song_name in song_data[i]:
                                try:
                                    os.remove(f'audio_data/{i}/{song_name}')
                                    song_data[i].remove(song_name)
                                except PermissionError:
                                    return {'type': 'error', 'message': f'{song_name} is playing. Then cannot remove this song.'}
                    else:
                        song_data[value].remove(song_name)
                        os.remove(f'audio_data/{value}/{song_name}')
                        if len([i for i in category[:-1] if song_name in song_data[i]]) == 0:
                            os.remove(f'audio_data/all/{song_name}')
                    if song_name in playlist:
                        ck_index = playlist.index(song_name)
                        if status == 2:
                            if cur >= ck_index:
                                cur -= 1
                        playlist.remove(song_name)
                    return {'type': 'success', 'message': 'playlist select success!'}
                else:
                    return {'type': 'error', 'message': f'no have {song_name} in {value} category'}
            else:
                return {'type': 'error', 'message': f'no have {value} category'}
    else:
        return {'type': 'error', 'message': 'no have essential parameter'}

@app.route('/uploads')
def uploads():
    return render_template('uploads.html', category=category)

@app.route('/play')
def play():
    global song_data, playlist, cur, status, now
    if len(playlist) == 0:
        for _ in playlist:
            playlist.pop()
        for i in song_data['all']:
            playlist.append(i)
        cur.value = 0
        if len(playlist) != 0:
            now_singer, now_title = playlist[0][:-4].split(' - ')
            full_time = get_length(0)
        else:
            now_singer, now_title, full_time = '', '', 0
    else:
        now_singer, now_title = playlist[cur.value][:-4].split(' - ')
        full_time = get_length(cur.value)
    
    now_min, now_sec, now_full, percent = 0, 0, '0:00', 0
    if status.value:
        now_min = now.value // 60
        now_sec = now.value % 60
        now_full = f'{int(full_time//60)}:{int(full_time)%60:02d}'
        if full_time != 0:
            percent = 100 * now.value / full_time
        else:
            percent = 0
    send_data = []
    for i in playlist:
        singer, title = i[:-4].split(' - ')
        send_data.append([title, singer])
    return render_template('play.html', page_type='category', category=category, data=send_data, status=status.value, now_min=now_min, now_sec=now_sec, now_full=now_full, full_time=full_time, now_singer=now_singer, now_title=now_title, percent=percent, volume=volume.value)

@app.route('/remove')
def remove():
    global song_data
    return render_template('remove.html', category=category, playlist=song_data['all'])

@app.route('/')
def index():
    return render_template('index.html')

def play_song(title, singer):
    global playlist, cur, status, now
    song_name = f'{singer} - {title}.mp3'
    if song_name in playlist:
        cur.value = playlist.index(song_name)
        if status.value == 2:
            status.value = 4
            full_time = get_length(cur.value)
            socketio.emit('play', data=(1, full_time))
        else:
            status.value = 3
            full_time = get_length(cur.value)
            socketio.emit('change_song', data=(title, singer, f'{int(full_time//60)}:{int(full_time)%60:02d}'))
            socketio.emit('play', data=(1, full_time))

@socketio.on('finish_song')
def finish_song(methods=['GET', 'POST']):
    global playlist, cur, status, now
    song_name = playlist[cur.value]
    singer, title = song_name[:-4].split(' - ')
    full_time = get_length(cur.value)
    socketio.emit('change_song', data=(title, singer, f'{int(full_time//60)}:{int(full_time)%60:02d}'))
    socketio.emit('play', data=(1, full_time))

@socketio.on('play')
def play_event(title, singer, methods=['GET', 'POST']):
    play_song(title, singer)

@socketio.on('stop')
def stop_event(title, singer, methods=['GET', 'POST']):
    global status
    if status.value == 1:
        status.value = 5
        socketio.emit('play', data=(0))

@socketio.on('next')
def next_event(methods=['GET', 'POST']):
    global cur, playlist
    if cur.value+1 >= len(playlist):
        cur.value = 0
    else:
        cur.value += 1
    singer, title = playlist[cur.value][:-4].split(' - ')
    play_song(title, singer)

@socketio.on('back')
def back_event(methods=['GET', 'POST']):
    global cur, playlist
    if cur.value == 0:
        cur.value = len(playlist) - 1
    else:
        cur.value -= 1
    singer, title = playlist[cur.value][:-4].split(' - ')
    play_song(title, singer)

@socketio.on('replay')
def replay_song(methods=['GET', 'POST']):
    global cur, playlist
    singer, title = playlist[cur.value][:-4].split(' - ')
    play_song(title, singer)

@socketio.on('change_playlist')
def change_playlist(random_val, category_val, methods=['GET', 'POST']):
    global song_data
    playlist_temp = deepcopy(song_data[category[int(category_val)]])
    if random_val:
        random.shuffle(playlist_temp)
    p_list = []
    for i in playlist_temp:
        singer, title = i[:-4].split(' - ')
        p_list.append({'title': title, 'singer': singer})
    socketio.emit('change_playlist', data=(p_list), to=request.sid)

@socketio.on('playlist_save')
def playlist_save(playlist_temp_, methods=['GET', 'POST']):
    global playlist, cur, status
    song_name = playlist[cur.value]
    while len(playlist):
        del playlist[0]
    for i in playlist_temp_:
        playlist.append(i)
    if song_name in playlist:
        cur.value = playlist.index(song_name)
    else:
        cur.value = 0
        if len(playlist) != 0:
            now_singer, now_title = playlist[0][:-4].split(' - ')
            full_time = get_length(cur.value)
        else:
            now_singer, now_title, full_time = '', '', 0
        socketio.emit('change_song', data=(now_title, now_singer, f'{int(full_time//60)}:{int(full_time)%60:02d}'))
        if status.value:
            status.value = 6
    p_list = []
    for i in playlist:
        singer, title = i[:-4].split(' - ')
        p_list.append({'title': title, 'singer': singer})
    socketio.emit('saved_playlist', data=(p_list, status.value))

@socketio.on('volume')
def vol(vol, methods=['GET', 'POST']):
    global volume, vol_status
    vol = int(vol)
    volume.value = vol
    vol_status.value = 1
    socketio.emit('volume', data=(vol))

def main(song_data_temp, playlist_temp, cur_temp, status_temp, volume_temp, now_temp, vol_status_temp):
    global song_data, playlist, cur, status, volume, now, vol_status
    song_data, playlist, cur, status, volume, now, vol_status = song_data_temp, playlist_temp, cur_temp, status_temp, volume_temp, now_temp, vol_status_temp
    socketio.run(app, host='0.0.0.0', )

def loop(song_data_temp, playlist_temp, cur_temp, status_temp, volume_temp, now_temp, vol_status_temp):
    global song_data, playlist, cur, status, volume, now, vol_status
    song_data, playlist, cur, status, volume, now, vol_status = song_data_temp, playlist_temp, cur_temp, status_temp, volume_temp, now_temp, vol_status_temp
    pygame.init()
    pygame.mixer.init()
    volume_temp = int(pygame.mixer.music.get_volume() * 100)
    volume.value = volume_temp
    pygame.mixer.music.set_endevent ( pygame.USEREVENT )
    temp_status = -2
    while status.value != -2:
        # 8~18
        now_datetime = datetime.now().hour
        if status.value == -1 and 7 < now_datetime < 18:
            cur.value = 0
            song_name = playlist[cur.value]
            pygame.mixer.music.load(f'audio_data/all/{song_name}')
            pygame.mixer.music.play()
            status.value = 1
        elif status.value != -1 and (now_datetime < 8 or 17 < now_datetime):
            status.value = -1
            pygame.mixer.music.stop()
        if status.value != temp_status:
            temp_status = status.value
            print('status', temp_status)
        if status.value == 0:
            pass
        elif status.value == 1:
            now.value = pygame.mixer.music.get_pos() // 1000
            for event in pygame.event.get():
                if event.type == pygame.USEREVENT and now.value != 0:
                    print("Music End")
                    if cur.value+1 >= len(playlist):
                        cur.value = 0
                    else:
                        cur.value += 1
                    singer, title = playlist[cur.value][:-4].split(' - ')
                    play_song(title, singer)
        elif status.value == 2:
            pass
        elif status.value == 3:
            song_name = playlist[cur.value]
            pygame.mixer.music.load(f'audio_data/all/{song_name}')
            pygame.mixer.music.play()
            status.value = 1
        elif status.value == 4:
            pygame.mixer.music.unpause()
            status.value = 1
        elif status.value == 5:
            pygame.mixer.music.pause()
            status.value = 2
        elif status.value == 6:
            pygame.mixer.music.stop()
            status.value = 0
        if vol_status.value == 1:
            pygame.mixer.music.set_volume(volume.value/100)
            vol_status.value = 0

if __name__ == "__main__":
    print(("* Flask starting server..."))
    # app.run(host="0.0.0.0", debug=True)
    # socketio.run(app, host='0.0.0.0', debug=True)
    manager = Manager()
    
    song_data = manager.dict()
    if not os.path.exists('audio_data'):
        os.makedirs('audio_data')
    for i in category:
        if not os.path.exists(f'audio_data/{i}'):
            os.makedirs(f'audio_data/{i}')
        song_data[i] = manager.list([f for f in os.listdir(f'audio_data/{i}') if os.path.isfile(f'audio_data/{i}/{f}')])
    playlist = manager.list(song_data['all'])
    cur = Value('i', 0)
    status = Value('i', 0)
    volume = Value('i', 20)
    now = Value('i', 0)
    vol_status = Value('i', 0)
    
    jobs = []
    process1 = Process(target=main, args=(song_data, playlist, cur, status, volume, now, vol_status))
    jobs.append(process1)
    process1.start()
    process2 = Process(target=loop, args=(song_data, playlist, cur, status, volume, now, vol_status))
    jobs.append(process2)
    process2.start()
    for i in jobs:
        i.join()