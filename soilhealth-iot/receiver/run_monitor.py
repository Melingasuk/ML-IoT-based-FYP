"""Run this computer's receiver and bridge together. Ctrl+C stops both children."""
import ctypes
import getpass
import os
from pathlib import Path
import subprocess
import sys
import time

def main():
    root=Path(__file__).resolve().parent
    config=Path(os.environ.get('SOILHEALTH_BRIDGE_CONFIG', str(root/'bridge.json')))
    if not config.resolve().is_file():
        raise SystemExit('Private bridge configuration is missing.')
    mutex=None
    if os.name=='nt':
        api=ctypes.WinDLL('kernel32',use_last_error=True)
        api.CreateMutexW.restype=ctypes.c_void_p
        api.CreateMutexW.argtypes=[ctypes.c_void_p,ctypes.c_bool,ctypes.c_wchar_p]
        api.CloseHandle.argtypes=[ctypes.c_void_p]
        mutex=api.CreateMutexW(None,False,'Local\\SoilHealthCombinedReceiver')
        if not mutex: raise SystemExit('Could not create receiver lock.')
        if ctypes.get_last_error()==183:
            api.CloseHandle(mutex)
            raise SystemExit('The combined monitor is already running.')
    children=[]
    print('Keep this computer awake and connected. Full history: '+str(root/'soilhealth.sqlite3'),flush=True)
    print('Enter the HiveMQ RECEIVER password when prompted; it is not saved.',flush=True)
    try:
        password=os.environ.get('SOILHEALTH_RECEIVER_PASSWORD') or getpass.getpass('HiveMQ receiver password: ')
        if not password: raise SystemExit('Receiver password is required.')
        receiver_env=os.environ.copy()
        receiver_env['SOILHEALTH_RECEIVER_PASSWORD']=password
        children.append(subprocess.Popen([sys.executable,'-u',str(root/'receiver.py')],env=receiver_env))
        del password, receiver_env
        children.append(subprocess.Popen([sys.executable,'-u',str(root/'cloud_bridge.py'),'--config',str(config.resolve())]))
        while all(p.poll() is None for p in children): time.sleep(1)
        if any(p.returncode not in (None,0) for p in children): raise SystemExit('A monitor process stopped; check its error above.')
    except KeyboardInterrupt:
        print('Stopping monitor.')
    finally:
        for p in children:
            if p.poll() is None: p.terminate()
        for p in children:
            try:p.wait(timeout=5)
            except subprocess.TimeoutExpired:p.kill();p.wait()
        if mutex:api.CloseHandle(mutex)

if __name__=='__main__':main()
