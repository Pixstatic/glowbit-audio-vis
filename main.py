import sys
import machine
from machine import Pin, I2C
from ssd1306 import SSD1306_I2C
import glowbit
import math


#buttonPin = 16

#button = Pin(buttonPin,Pin.IN,Pin.PULL_UP)



matrix = glowbit.matrix8x8(rateLimitFPS = 60)

charWidth = 8

maxChars = math.floor(128/charWidth)


i2c=I2C(0,sda=Pin(0), scl=Pin(1), freq=400000)
oled = SSD1306_I2C(128, 64, i2c)

try:
    oled.text("Connect To PC",0,0)
    oled.show()
    oledexists = True
except:
    oledexists = False


def addTextMultiline(text,y,charLimit):
    
    t = list(text)
    for i in range(0,math.ceil(len(t)/maxChars)):
        oled.text(''.join(t[j] for j in range(i*maxChars,min(i*maxChars+maxChars,len(t))) if j < charLimit),0,i*9+y)


frame = 0

frameUpdated = 0

songTitle = ""

while True:
    # read a command from the host
    v = sys.stdin.readline().strip()

    # perform the requested action
    if v.lower():
        vsplit = v.split('`')
        oled.fill(0)
        mc = frame - frameUpdated if (int(vsplit[3]) == 1) else 999
        #oled.text(vsplit[2],0,16)
        
        if (vsplit[2] != songTitle):
            songTitle = vsplit[2]
            frameUpdated = frame
        
        
        if oledexists:
            addTextMultiline(vsplit[2],16,mc)
            
            
            addTextMultiline(vsplit[1],4,min(maxChars,mc))
            
            
            oled.show()
        
        #cs = vsplit[3].split(',')
        
        #c = matrix.rgbColour(int(cs[0]),int(cs[1]),int(cs[2]))
        
        ss = vsplit[0].split(',')
        
        for x in range(0,8):
            for y in range(0,8):
                c = matrix.wheel(int((x+y+frame)*(255/16)))
                
                matrix.pixelSetXY(x,y,c if (8-y) < int(ss[x]) else matrix.black())
        
        #if (button.value()):
        #    matrix.pixelsFill(matrix.white())
        
        matrix.pixelsShow()
        frame += 1
             
                
                
                
                
        
        