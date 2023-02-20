import asyncio
from async_timeout import timeout
import time
from datetime import datetime as dt




import json


COM = "COM5"
USEWINRT = True
TIMEFORMAT = "%I:%M %p"
DATEFORMAT = "%a, %x"

try:     
    with open('config.json') as f:
        cfg = f.read() 


        config = json.loads(cfg)
    COM = config["COM Port"]
    USEWINRT = config["Windows Song Data"]
    TIMEFORMAT = config["Time Format"]
    DATEFORMAT = config["Date Format"]
except:
    print("Error loading config.json\nAttempting to use default values")



if USEWINRT:
    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as MediaManager,
    )

import serial
import numpy as np
import pyaudiowpatch as pa
import struct
import math

notPlaying = {"artist": "None", "title": "Nothing Playing"}





def lerp(a, b, t):
    return a + t * (b - a)


def invlerp(a, b, v):
    return (v - a) / (b - a)


async def get_info():
    if not USEWINRT:
        n = dt.now()
        return {"artist":n.strftime(TIMEFORMAT),"title":n.strftime(DATEFORMAT)}


    try:
        async with timeout(1 / 50):
            sessions = await MediaManager.request_async()
            current_session = sessions.get_current_session()

            info_dict = notPlaying

            if current_session:
                info = await current_session.try_get_media_properties_async()

                # song_attr[0] != '_' ignores system attributes
                info_dict = {
                    song_attr: info.__getattribute__(song_attr)
                    for song_attr in dir(info)
                    #if song_attr[0] != "_"
                }

                # converts winrt vector to list
                info_dict["genres"] = list(info_dict["genres"])

            return info_dict
    except asyncio.TimeoutError:
        return None


def get_speakers(p,wasapi_info):
    default_speakers = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])

    if not default_speakers["isLoopbackDevice"]:
        for loopback in p.get_loopback_device_info_generator():
            # Tries to find a loopback device with the same name as the speakers
            if default_speakers["name"] in loopback["name"]:
                default_speakers = loopback
                break
        else:
            return False
    return default_speakers

def main():

    p = pa.PyAudio()


    try:
        # Get default WASAPI info
        wasapi_info = p.get_host_api_info_by_type(pa.paWASAPI)
    except OSError:
        print("Seems like WASAPI isn't available on this system\nExiting in 5s")
        time.sleep(5)
        return False

    

    #print(default_speakers.keys())

    default_speakers = get_speakers(p,wasapi_info)

    if not default_speakers:
        print("Loopback Audio Device Not Found!\nExiting in 5s")
        time.sleep(5)
        return False

    INDEX = default_speakers["index"]

    FORMAT = pa.paInt16
    CHANNELS = 1 #default_speakers["maxInputChannels"]
    RATE = int(default_speakers["defaultSampleRate"])

    CHUNK = int(1024 / CHANNELS)




    try:

        stream = p.open(
            format=FORMAT,
            channels=1,
            rate=RATE,
            input=True,
            frames_per_buffer=CHUNK,
            input_device_index=INDEX,
        )
    except OSError:
        try:
            CHANNELS = default_speakers["maxInputChannels"]
            
            stream = p.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=RATE,
                input=True,
                frames_per_buffer=CHUNK,
                input_device_index=INDEX,
            )
            print("Your current audio device does not work with Mono mode, switching to compatibility mode (higher latency)")
        except OSError:
            raise Exception("Your audio configuration does not work with audio capture!")
            


    d = [0, 0, 0, 0, 0, 0, 0, 0]
    maxVol = 25
    points = [10, 17, 20, 25, 30, 40, 55, 75]
    scales = [0.3,0.6,0.6,0.7,0.7,0.7,0.85,1]

    bufferedInfo = notPlaying
    bufferTime = 0

    try:
        ser = serial.Serial(COM, 115200)
    except OSError:
        print("Pico is not connected\nExiting in 5s")
        time.sleep(5)
        return

    ser.write(f'0,0,0,0,0,0,0,0`Connected!`Play Audio to Start`0\n'.encode())

    ser.close()



    while True:
        try:
            ser = serial.Serial(COM, 115200)
        except OSError:
            print("Device disconnected\nExiting in 5s")
            time.sleep(5)
            return False

        info_dict = asyncio.run(get_info())

        if info_dict:
            bufferedInfo = info_dict
            bufferTime = time.time()
        
        
        
        try:
            data = stream.read(CHUNK, exception_on_overflow=False)
        except OSError:
            print("Audio device changed\nRestarting")
            return True
    
        
        dataInt = struct.unpack(str(CHUNK*CHANNELS) + "h", data)

        dataInt = dataInt[0:1024]

        fftData = np.abs(np.fft.fft(dataInt))

        s = ""

        mv = 0.001 if CHANNELS == 1 else 100

        intensity = 0

        for i in range(0, 8):
            index = points[i]
            scale = scales[i]
            data = ((fftData[index] + fftData[index + 1] + fftData[index - 1]) / 3)*scale

            mv = lerp(mv,max(mv, data),0.7)



            data = lerp(d[i], data, 0.5)
            d[i] = data


        maxVol = lerp(maxVol, mv, 0.15 if (mv > maxVol) else 0.03)

        for i in range(0, 8):
            v = min((math.floor(invlerp(0, maxVol, d[i]) * 8)), 9)

            intensity += v
            
            s += f"{v},"

        ser.write(f'{s}`{bufferedInfo["artist"]}`{bufferedInfo["title"]}`1\n'.encode())

        ser.close()


if __name__ == "__main__":
    attempts = 0
    while(main() and attempts < 10):
        attempts += 1
