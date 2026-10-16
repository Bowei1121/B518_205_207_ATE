import sys,time,json,os,tkinter as tk
from tkinter import ttk
import Quartz
from AppKit import NSRunningApplication,NSApplicationActivateIgnoringOtherApps
root=tk.Tk();root.geometry('300x150+100+150');events=[];opened=[]
b=ttk.Button(root,text='Settings',command=lambda:opened.append(True),takefocus=True);b.pack(pady=20)
b.bindtags(('ProbePointer',)+b.bindtags())
for sequence in ('<ButtonPress-1>','<ButtonRelease-1>'):
 root.bind_class('ProbePointer',sequence,lambda e,sequence=sequence:events.append(sequence))
def pump(t):
 end=time.monotonic()+t
 while time.monotonic()<end:root.update();time.sleep(.01)
pump(.3);NSRunningApplication.currentApplication().activateWithOptions_(NSApplicationActivateIgnoringOtherApps);pump(.3);root.lift();root.focus_force();pump(.3)
point=(b.winfo_rootx()+b.winfo_width()/2,b.winfo_rooty()+b.winfo_height()/2)
for kind in (Quartz.kCGEventMouseMoved,Quartz.kCGEventLeftMouseDown,Quartz.kCGEventLeftMouseUp):
 Quartz.CGEventPost(Quartz.kCGSessionEventTap,Quartz.CGEventCreateMouseEvent(None,kind,point,Quartz.kCGMouseButtonLeft));pump(.2)
print(json.dumps({'executable':sys.executable,'tk':root.tk.call('info','patchlevel'),'events':events,'callbacks':len(opened),'pointer':root.winfo_pointerxy(),'target':point}),flush=True)
root.destroy()
