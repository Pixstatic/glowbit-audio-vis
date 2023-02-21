import asyncio
from async_timeout import timeout
import time
from datetime import datetime as dt




import json

#initialize config values
COM = "COM5"
USEWINRT = True
TIMEFORMAT = "%I:%M %p"
DATEFORMAT = "%a, %x"

try: #attempt to read config file and populate values
    with open('config.json') as f:
        cfg = f.read() 


        config = json.loads(cfg)
    COM = config["COM Port"] #Serial Port for Pico
    USEWINRT = config["Windows Song Data"] #whether to use windows runtime APIs to get song data
    TIMEFORMAT = config["Time Format"] #format for time (top row of OLED)
    DATEFORMAT = config["Date Format"] #format for date (bottom of OLED)
except:
    print("Error loading config.json\nAttempting to use default values") #Print error, use default values



if USEWINRT: #import windows runtime if enabled
    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as MediaManager,
    )

import serial
import numpy as np
import pyaudiowpatch as pa
import struct
import math

notPlaying = {"artist": "None", "title": "Nothing Playing"} #default message for when a song is not playing




#useful maths functions
def lerp(a, b, t): 
    return a + t * (b - a)


def invlerp(a, b, v):
    return (v - a) / (b - a)


async def get_info(): #gets information for OLED display
    if not USEWINRT: #if not using windows runtime, return formatted date and time
        n = dt.now()
        return {"artist":n.strftime(TIMEFORMAT),"title":n.strftime(DATEFORMAT)}


    try: 
        async with timeout(1 / 50): #attempt to fetch song data, times out after 1/50 of a second to maintain low latency
            sessions = await MediaManager.request_async() #find media sessions
            current_session = sessions.get_current_session() 

            info_dict = notPlaying #initialize dict to default message

            if current_session:
                info = await current_session.try_get_media_properties_async() #try to get media info

                info_dict = { 
                    song_attr: info.__getattribute__(song_attr)
                    for song_attr in dir(info)
                }

                info_dict["genres"] = list(info_dict["genres"]) #convert info to list

            return info_dict
    except asyncio.TimeoutError: #if data request takes longer than 1/50 of a second, return None
        return None


def get_speakers(p,wasapi_info): #get information about current speakers
    default_speakers = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"]) #get default output device

    if not default_speakers["isLoopbackDevice"]: #checks if current output device supports loopback
        for loopback in p.get_loopback_device_info_generator():
            # Tries to find a loopback device with the same name as the speakers
            if default_speakers["name"] in loopback["name"]:
                default_speakers = loopback
                break
        else: #for-else is kinda funny, this just means it returns false if the loop ends "naturally"
            return False
    return default_speakers

def main():

    p = pa.PyAudio() #initialize pyaudio


    try:
        # Get default WASAPI info
        wasapi_info = p.get_host_api_info_by_type(pa.paWASAPI)
    except OSError:
        print("Seems like WASAPI isn't available on this system\nExiting in 5s")
        time.sleep(5)
        return False


    default_speakers = get_speakers(p,wasapi_info) #get current speakers

    if not default_speakers:
        print("Loopback Audio Device Not Found!\nExiting in 5s") 
        time.sleep(5)
        return False #exit if default speakers are not found (or do not support loopback)

    INDEX = default_speakers["index"] #gets device index of speakers

    FORMAT = pa.paInt16
    CHANNELS = 1 
    RATE = int(default_speakers["defaultSampleRate"])

    CHUNK = int(1024 / CHANNELS)




    try: #attempt to start audio stream in single-channel mode
        stream = p.open(
            format=FORMAT,
            channels=1,
            rate=RATE,
            input=True,
            frames_per_buffer=CHUNK,
            input_device_index=INDEX,
        )
    except OSError:
        try: #attempt to start audio stream with default number of channels supported by the speaker ("compatibility mode")
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
            


    d = [0, 0, 0, 0, 0, 0, 0, 0] #data buffer
    maxVol = 25 #maximum volume, controls the upper bound of the spectrum data
    points = [10, 17, 20, 25, 30, 40, 55, 75] #sampling points for array of spectrum data. each number corresponds to one column
    scales = [0.3,0.6,0.6,0.7,0.7,0.7,0.85,1] #how much to scale the data for each of these points; low frequencies would otherwise overpower high ones on the display

    bufferedInfo = notPlaying #initialize song info buffer to default message
    bufferTime = 0 #record time of last buffer write

    try: #attempt to open a serial connection to the Pico
        ser = serial.Serial(COM, 115200)
    except OSError:
        print("Pico is not connected\nExiting in 5s")
        time.sleep(5)
        return #if Pico is not connected on the configured serial port, exit

    ser.write(f'0,0,0,0,0,0,0,0`Connected!`Play Audio to Start`0\n'.encode()) #Write confirmation message to Pico

    ser.close()



    while True:
        try: #attempt to open serial connection
            ser = serial.Serial(COM, 115200)
        except OSError:
            print("Device disconnected\nExiting in 5s")
            time.sleep(5)
            return False #if Pico is not connected, exit

        info_dict = asyncio.run(get_info()) #get info for OLED display

        if info_dict: #set buffer if info is returned
            bufferedInfo = info_dict
            bufferTime = time.time()
        
        
        
        try: #attempt to read audio data
            data = stream.read(CHUNK, exception_on_overflow=False)
        except OSError:
            print("Audio device changed\nRestarting")
            return True #restart main loop in case audio device has changed. At this time, this does not usually work
    
        
        dataInt = struct.unpack(str(CHUNK*CHANNELS) + "h", data) #unpack raw audio data to array

        dataInt = dataInt[0:1024] #truncate data to length of 1024 

        fftData = np.abs(np.fft.fft(dataInt)) #run a fast fourier transform, to extract frequency data from raw audio

        s = "" #initialize string, which spectrum data will be written to

        mv = 0.001 if CHANNELS == 1 else 100 #initialize maximum volume for this loop. These are minimum values to hide noise

        intensity = 0 #unused, intended to measure "turbulence" of the current audio

        for i in range(0, 8):
            index = points[i]
            scale = scales[i]
            data = ((fftData[index] + fftData[index + 1] + fftData[index - 1]) / 3)*scale #sample FFT data at specified points. Average with neighbours to minimise spikes

            mv = lerp(mv,max(mv, data),0.7) #set mv to the greater value out of itself and the data at this point. interpolated to minimise spikes



            data = lerp(d[i], data, 0.5) #interpolate data with buffer to give a smoother appearance
            d[i] = data #write data to buffer


        maxVol = lerp(maxVol, mv, 0.15 if (mv > maxVol) else 0.03) #interpolate maximum volume towards mv. interpolates much faster if mv is greater than maxVol

        for i in range(0, 8):
            v = min((math.floor(invlerp(0, maxVol, d[i]) * 8)), 9) #maps each data point to the bounds described by maxVol

            intensity += v 
            
            s += f"{v}," #writes current data point to string

        ser.write(f'{s}`{bufferedInfo["artist"]}`{bufferedInfo["title"]}`1\n'.encode()) #writes data to Pico in the format "<spectrum data>`<top row text>`<main display text>`<enable type out effect>"

        ser.close() #close serial port to prevent the program hanging if the Pico is disconnected


if __name__ == "__main__":
    attempts = 0
    while(main() and attempts < 10): #Runs the main loop a maximum of 10 times, restarting it if it returns "True" at any point
        attempts += 1
