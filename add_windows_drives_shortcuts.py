import ctypes
import string
import os

def add_windows_drives_shortcuts():
    """ add all windows hard disks with disk names to the file preferences 
        only works if added on menu.py
        it needs a unique character sequences to recognize the dynamically created drives ("UNIQUE")
        tested on win11


    """
    EXCLUSIONLIST = ["CACHE","ANYDISKNAMEYOUWANT"]
    
    UNIQUE = "://" 

    # removes all disks previously created
    home = os.path.expanduser("~")  
    hideNuke  = os.path.join(home, '.nuke') 
    
    for fil in os.listdir(hideNuke): 
        if not fil.endswith('.pref'): 
            continue
        preffile = os.path.join(hideNuke, fil)
        with open(preffile, "r") as f:
            lines = f.readlines()
        with open(preffile, "w") as f:
            for line in lines:
                if UNIQUE not in line:
                    f.write(line)

    # add shortcuts
    for drive in string.ascii_uppercase[1:]:
        kernel32 = ctypes.windll.kernel32
        volumeNameBuffer = ctypes.create_unicode_buffer(1024)
        drivestr = drive + ":\\"
        kernel32.GetVolumeInformationW(ctypes.c_wchar_p(drivestr), volumeNameBuffer)
        shortcut = str(volumeNameBuffer.value)

        if len(shortcut) > 0 and shortcut not in EXCLUSIONLIST:
            nuke.addFavoriteDir(drive+UNIQUE+shortcut, drive+":/")
 
add_windows_drives_shortcuts()
        