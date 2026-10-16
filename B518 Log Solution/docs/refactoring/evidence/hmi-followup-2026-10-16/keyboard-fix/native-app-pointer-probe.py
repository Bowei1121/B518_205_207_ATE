import json,sys,time,tempfile,tkinter as tk
from pathlib import Path
from unittest.mock import patch
import Quartz
from AppKit import NSRunningApplication,NSApplicationActivateIgnoringOtherApps,NSApplication
sys.path.insert(0,str(Path(sys.argv[1])/'src'))
import b518_log_solution as ui
class Hotkey:
 available=True
 def __init__(self,callback):pass
 def close(self):pass
records=[]
with tempfile.TemporaryDirectory() as d,patch.object(ui,'PREFS_PATH',Path(d)/'preferences.json'):
 root=tk.Tk();app=ui.B518LogSolutionApp(root,hotkey_factory=Hotkey,session_root=Path(d)/'s',app_event_path=Path(d)/'e')
 def pump(t):
  end=time.monotonic()+t
  while time.monotonic()<end:root.update();time.sleep(.01)
 def click(control):
  point=(control.winfo_rootx()+control.winfo_width()/2,control.winfo_rooty()+control.winfo_height()/2)
  for kind in (Quartz.kCGEventMouseMoved,Quartz.kCGEventLeftMouseDown,Quartz.kCGEventLeftMouseUp):
   Quartz.CGEventPost(Quartz.kCGSessionEventTap,Quartz.CGEventCreateMouseEvent(None,kind,point,Quartz.kCGMouseButtonLeft));pump(.2)
 for name in ('settings_button','round_alarm_button','project_choice','machine_choice'):
  control=getattr(app,name);control.bindtags(('RawPointer',)+control.bindtags())
 for sequence in ('<ButtonPress-1>','<ButtonRelease-1>'):
  root.bind_class('RawPointer',sequence,lambda event,sequence=sequence:records.append({'event':sequence,'widget':str(event.widget)}))
 pump(.4);NSRunningApplication.currentApplication().activateWithOptions_(NSApplicationActivateIgnoringOtherApps);pump(.3);root.lift();root.focus_force();pump(.3)
 results={}
 for name in ('settings_button','round_alarm_button'):
  native=NSApplication.sharedApplication();key=native.keyWindow()
  records.append({'before':name,'active':bool(native.isActive()),'key':str(key.title()) if key else None,'focus':str(root.focus_get())})
  click(getattr(app,name));window=app.settings_window if name=='settings_button' else app.recovery_window
  results[name]=bool(window and window.winfo_viewable())
  if window:
   if name=='settings_button':app._close_settings()
   else:window.destroy()
  pump(.3)
 for name in ('project_choice','machine_choice'):
  control=getattr(app,name);click(control)
  popdown=root.tk.call('ttk::combobox::PopdownWindow',control)
  results[name]=bool(int(root.tk.call('winfo','ismapped',popdown)))
  root.tk.call('ttk::combobox::Unpost',control);pump(.2)
 print(json.dumps({'executable':sys.executable,'tk':root.tk.call('info','patchlevel'),'results':results,'raw_events':records},indent=2),flush=True)
 app.rounds.request_close()
 while app.rounds.close_status().status!='complete':pump(.03)
 app.hotkey.close();root.destroy()
 sys.exit(0 if all(results.values()) else 1)
