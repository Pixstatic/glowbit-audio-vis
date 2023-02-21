import sys
import machine
from machine import Pin, I2C
from ssd1306 import SSD1306_I2C
import glowbit
import math


matrix = glowbit.matrix8x8(rateLimitFPS = 60) #initialize Glowbit Matrix

charWidth = 8 #pixel width of a single character on the OLED Display

maxChars = math.floor(128/charWidth) #calculate maximum characters able to be displayed on a single row of the display



try: #Check if OLED is connected, and show text if it is
    i2c=I2C(0,sda=Pin(0), scl=Pin(1), freq=400000) #create i2c connection to OLED
    oled = SSD1306_I2C(128, 64, i2c) #initialize OLED Display

    oled.text("Connect To PC",0,0)
    oled.show()
    oledexists = True
except:
    oledexists = False


def addTextMultiline(text,y,charLimit): #function for showing text across multiple lines
    
    t = list(text)
    for i in range(0,math.ceil(len(t)/maxChars)):
        oled.text(''.join(t[j] for j in range(i*maxChars,min(i*maxChars+maxChars,len(t))) if j < charLimit),0,i*9+y)


frame = 0 

frameUpdated = 0 #the last frame that the text on the display was updated

songTitle = "" #buffered song title

while True:
    # read a command from the host
    v = sys.stdin.readline().strip()

    # perform the requested action
    if v.lower():
        vsplit = v.split('`')
        mc = frame - frameUpdated if (int(vsplit[3]) == 1) else 999
        #oled.text(vsplit[2],0,16)
        
        if (vsplit[2] != songTitle): #check if song name has been updated (for typeout effect)
            songTitle = vsplit[2]
            frameUpdated = frame 
        
        if oledexists: #update OLED Display if it is connected
            oled.fill(0)

            addTextMultiline(vsplit[2],16,mc)
            addTextMultiline(vsplit[1],4,min(maxChars,mc))
            oled.show()
        
        ss = vsplit[0].split(',')
        
        for x in range(0,8):
            for y in range(0,8):
                c = matrix.wheel(int((x+y+frame)*(255/16)))
                
                matrix.pixelSetXY(x,y,c if (8-y) < int(ss[x]) else matrix.black())
        
        matrix.pixelsShow()
        frame += 1
        
                
                
                
                
        
        