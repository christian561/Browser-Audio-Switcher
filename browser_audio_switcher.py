#!/usr/bin/env python3
"""
Browser Audio Switcher
Hot-keys:  Alt + Z / X / C   (Browser 1 / Browser 2 / Browser 3)
Buttons :  Browser 1 / 2 / 3
"""

import os, signal, subprocess, sys, threading, time, re, shutil
from pathlib import Path
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Check for wmctrl
try:
    subprocess.check_call(["which", "wmctrl"], stdout=subprocess.DEVNULL)
except subprocess.CalledProcessError:
    logger.error("wmctrl not found! Please install it: sudo apt install wmctrl")
    sys.exit(1)

# GTK
import gi; gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Gdk

# ─── browsers: one per profile ────────────────────────────────────
BROWSERS = [
    "/usr/bin/vivaldi-stable",   # Browser 1
    "/usr/bin/google-chrome",    # Browser 2
    "/usr/bin/brave-browser"     # Browser 3
]

# ─── URLs for each browser ────────────────────────────────────────
BROWSER_URLS = [
    "https://www.youtube.com/watch?v=I2JRIHQ2Z68",  # McDonald's beeping sounds
    "https://www.youtube.com/watch?v=MTJ-_gvNmbA",  # Tom & Jerry cartoon
    "https://www.youtube.com/watch?v=Nsi3zUriYgc"   # Spring nature sounds
]

# Mapping of browser process names to their identifiers
BROWSER_PATTERNS = [
    ["vivaldi", "vivaldi-stable"],             # For Vivaldi
    ["chrome", "google-chrome", "chromium"],   # For Chrome/Chromium
    ["brave", "brave-browser"]                 # For Brave
]

# Debug mode - set to True for more verbose logging
DEBUG = True
if DEBUG:
    logging.getLogger().setLevel(logging.DEBUG)

# Browser window IDs - keeps track of browser windows for quick access
browser_windows = [None, None, None]  # Indexed from 0, but browser numbers are 1-based

# Check browsers exist
for browser in BROWSERS:
    if not os.path.exists(browser):
        logger.warning(f"Browser not found: {browser}")

# Helpers
def run(cmd): 
    try:
        return subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed: {cmd}, error: {e}")
        return ""

def set_vol(idx, p): 
    try:
        logger.info(f"Setting volume for sink {idx} to {p}%")
        subprocess.call(["pactl", "set-sink-input-volume", idx, f"{p}%"])
        return True
    except Exception as e:
        logger.error(f"Failed to set volume: {e}")
        return False

def set_mute(idx, m): 
    try:
        logger.info(f"Setting mute for source {idx} to {m}")
        subprocess.call(["pactl", "set-source-output-mute", idx, "1" if m else "0"])
        return True
    except Exception as e:
        logger.error(f"Failed to set mute: {e}")
        return False

def list_all_windows():
    """List all windows to help with debugging"""
    try:
        logger.debug("Current windows:")
        output = run(["wmctrl", "-lp"])
        for line in output.splitlines():
            logger.debug(f"  {line}")
        return output
    except Exception as e:
        logger.error(f"Error listing windows: {e}")
        return ""

def focus_window_by_id(window_id):
    """Focus a window by its ID, return success status"""
    if not window_id:
        return False
        
    try:
        logger.debug(f"Attempting to focus window ID: {window_id}")
        result = subprocess.call(["wmctrl", "-i", "-a", window_id], stderr=subprocess.DEVNULL)
        return result == 0
    except Exception as e:
        logger.error(f"Error focusing window {window_id}: {e}")
        return False

def get_browser_executable_name(browser_path):
    """Extract executable name from path, compatible with snap packages"""
    base = os.path.basename(browser_path)
    if '.' in base:
        return base.split('.')[0]
    return base

def find_window_by_pid(pid):
    """Find a window by its PID"""
    output = run(["wmctrl", "-lp"])
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[2] == str(pid):
            return parts[0]
    return None

def find_window_by_title_part(title_part, exclude=None):
    """Find a window containing a part of a title"""
    output = run(["wmctrl", "-l"])
    for line in output.splitlines():
        if title_part.lower() in line.lower():
            if exclude and exclude in line:
                continue
            return line.split()[0]
    return None

def find_window_by_class(class_hint):
    """Find a window by its class hint (more reliable)"""
    try:
        output = run(["xprop", "-root", "_NET_CLIENT_LIST"])
        if not output:
            return None
            
        # Extract window IDs
        match = re.search(r'_NET_CLIENT_LIST\(WINDOW\): window id #\s*(.*)', output)
        if not match:
            return None
            
        window_ids = match.group(1).split(", ")
        for wid in window_ids:
            # For each window, check the class
            class_output = run(["xprop", "-id", wid, "WM_CLASS"])
            if class_hint.lower() in class_output.lower():
                return wid
        return None
    except Exception as e:
        logger.error(f"Error finding window by class: {e}")
        return None

# Expanded pattern to match application name and process ID
PAT_APP_PROCESS = re.compile(r'application\.process\.binary\s+=\s+".*?/([^/]+)"')
PAT_APP_NAME = re.compile(r'application\.name\s+=\s+"([^"]+)"')
PAT_MEDIA_NAME = re.compile(r'media\.name\s+=\s+"([^"]+)"')
PAT_APP_PID = re.compile(r'application\.process\.id\s+=\s+"(\d+)"')

def list_audio_streams():
    """Get more detailed information about audio streams"""
    try:
        # List sink inputs (playback)
        txt = run(["pactl", "list", "sink-inputs"])
        if not txt:
            logger.warning("No playback streams found")
            
        streams = []
        current_stream = {}
        
        for line in txt.splitlines():
            line = line.strip()
            
            if line.startswith("Sink Input #"):
                if current_stream and 'id' in current_stream:
                    streams.append(current_stream)
                current_stream = {'id': line.split("#")[1].strip()}
            elif "application.name" in line and '=' in line:
                m = PAT_APP_NAME.search(line)
                if m:
                    current_stream['app_name'] = m.group(1)
            elif "application.process.binary" in line:
                m = PAT_APP_PROCESS.search(line)
                if m:
                    current_stream['binary'] = m.group(1)
            elif "media.name" in line:
                m = PAT_MEDIA_NAME.search(line)
                if m:
                    current_stream['media_name'] = m.group(1)
            elif "application.process.id" in line:
                m = PAT_APP_PID.search(line)
                if m:
                    current_stream['pid'] = m.group(1)
        
        # Add the last stream if it exists
        if current_stream and 'id' in current_stream:
            streams.append(current_stream)
            
        logger.info(f"Found {len(streams)} audio streams: {streams}")
        return streams
    except Exception as e:
        logger.error(f"Error listing audio streams: {e}")
        return []

def get_window_pid(window_id):
    """Get PID for a window ID"""
    try:
        output = run(["xprop", "-id", window_id, "_NET_WM_PID"])
        match = re.search(r"_NET_WM_PID\(CARDINAL\) = (\d+)", output)
        if match:
            return match.group(1)
        return None
    except Exception as e:
        logger.error(f"Error getting PID for window {window_id}: {e}")
        return None

def adjust_stream_volumes(active_idx, streams):
    """Adjust volumes for all detected streams"""
    logger.info(f"Adjusting volumes, active: {active_idx}")
    
    ACTIVE_VOL, INACTIVE_VOL = 100, 30
    success = False
    browser_stream_ids = []
    
    # First, map browser names for better matching
    browser_names = {
        1: ["vivaldi", "vivaldimail"],
        2: ["chrome", "google chrome", "chromium"],
        3: ["brave", "brave-browser"]
    }
    
    active_browser_names = browser_names.get(active_idx, [])
    if active_browser_names:
        logger.info(f"Active browser names to match: {active_browser_names}")
    
    # Log all streams for debugging
    for stream in streams:
        if 'id' in stream:
            app_name = stream.get('app_name', '').lower()
            binary = stream.get('binary', '').lower()
            pid = stream.get('pid', '')
            logger.debug(f"Stream {stream['id']}: app_name='{app_name}', binary='{binary}', pid={pid}")
    
    # First attempt - manage by window IDs and process matching
    if active_idx <= len(browser_windows) and browser_windows[active_idx-1]:
        active_pid = get_window_pid(browser_windows[active_idx-1])
        logger.info(f"Active window ID: {browser_windows[active_idx-1]}, PID: {active_pid}")
        
        # Track which streams belong to which browser
        vivaldi_streams = []
        chrome_streams = []
        brave_streams = []
        
        # First pass: find browser streams and their browser index
        for stream in streams:
            if 'id' not in stream:
                continue
            
            # Get app name and binary info
            binary = stream.get('binary', '').lower()
            app_name = stream.get('app_name', '').lower()
            stream_pid = stream.get('pid', '')
            
            # Try to determine which browser this stream belongs to
            stream_browser_idx = None
            
            # Check Vivaldi streams
            if any(viv_name in app_name or viv_name in binary for viv_name in browser_names[1]):
                stream_browser_idx = 1
                vivaldi_streams.append(stream['id'])
                logger.info(f"Stream {stream['id']} matched as Vivaldi (Browser 1)")
            
            # Check Chrome streams - enhanced to ensure proper detection
            elif any(chrome_name in app_name or chrome_name in binary for chrome_name in browser_names[2]):
                stream_browser_idx = 2
                chrome_streams.append(stream['id'])
                logger.info(f"Stream {stream['id']} matched as Chrome (Browser 2)")
            
            # Check Brave streams
            elif any(brave_name in app_name or brave_name in binary for brave_name in browser_names[3]):
                stream_browser_idx = 3
                brave_streams.append(stream['id'])
                logger.info(f"Stream {stream['id']} matched as Brave (Browser 3)")
            
            # For Browser 2, all Chromium streams should be treated as Chrome streams if not identified otherwise
            elif active_idx == 2 and ("chromium" in app_name or "chromium" in binary):
                stream_browser_idx = 2
                chrome_streams.append(stream['id'])
                logger.info(f"Stream {stream['id']} identified as Chrome (Browser 2) based on active browser")
            
            # Chromium is typically used by all three browsers, so do additional checks
            elif "chromium" in app_name or "chromium" in binary:
                # Check if PID matches the active window PID
                if stream_pid == active_pid:
                    logger.info(f"Stream {stream['id']} matches active PID, setting to browser {active_idx}")
                    stream_browser_idx = active_idx
                    
                    if active_idx == 1:
                        vivaldi_streams.append(stream['id'])
                    elif active_idx == 2:
                        chrome_streams.append(stream['id'])
                    elif active_idx == 3:
                        brave_streams.append(stream['id'])
                
                # For Chromium streams, check the active browser
                else:
                    # Default based on active browser
                    if active_idx == 1 and not vivaldi_streams:
                        # If we're on Vivaldi and haven't found any Vivaldi streams yet
                        stream_browser_idx = 1
                        vivaldi_streams.append(stream['id'])
                        logger.info(f"Assigned Chromium stream {stream['id']} to Vivaldi (Browser 1) based on active browser")
            
            # Set the volume based on whether it's the active browser
            if stream_browser_idx is not None:
                volume = ACTIVE_VOL if stream_browser_idx == active_idx else INACTIVE_VOL
                logger.info(f"Setting stream {stream['id']} (browser {stream_browser_idx}) to {volume}%")
                set_vol(stream['id'], volume)
                browser_stream_ids.append(stream['id'])
                success = True
        
        # Log the streams found for each browser
        logger.info(f"Found {len(vivaldi_streams)} Vivaldi streams: {vivaldi_streams}")
        logger.info(f"Found {len(chrome_streams)} Chrome streams: {chrome_streams}")
        logger.info(f"Found {len(brave_streams)} Brave streams: {brave_streams}")
        
        # If we're on Vivaldi and didn't find any Vivaldi streams, try a more aggressive approach
        if active_idx == 1 and not vivaldi_streams and streams:
            logger.info("No Vivaldi streams found, trying to assign active Chromium/unknown streams to Vivaldi")
            
            # Look for Chromium or unknown streams to assign to Vivaldi
            for stream in streams:
                if 'id' in stream and stream['id'] not in browser_stream_ids:
                    logger.info(f"Setting unassigned stream {stream['id']} to active volume (Vivaldi)")
                    set_vol(stream['id'], ACTIVE_VOL)
                    success = True
    
    # If first attempt failed, try a more aggressive approach
    if not success and streams:
        logger.info("Using more aggressive volume control approach")
        
        # Set volume based on active browser
        for stream in streams:
            if 'id' not in stream:
                continue
                
            app_name = stream.get('app_name', '').lower()
            binary = stream.get('binary', '').lower()
            
            # Browser 1 (Vivaldi) is active
            if active_idx == 1:
                # If this is likely a Vivaldi stream
                if "vivaldi" in app_name or "vivaldi" in binary:
                    logger.info(f"Setting Vivaldi stream {stream['id']} to {ACTIVE_VOL}%")
                    set_vol(stream['id'], ACTIVE_VOL)
                else:
                    logger.info(f"Setting non-Vivaldi stream {stream['id']} to {INACTIVE_VOL}%")
                    set_vol(stream['id'], INACTIVE_VOL)
                success = True
                
            # Browser 2 (Chrome) is active
            elif active_idx == 2:
                # If this is likely a Chrome stream
                if "chrome" in app_name or "chrome" in binary:
                    logger.info(f"Setting Chrome stream {stream['id']} to {ACTIVE_VOL}%")
                    set_vol(stream['id'], ACTIVE_VOL)
                else:
                    logger.info(f"Setting non-Chrome stream {stream['id']} to {INACTIVE_VOL}%")
                    set_vol(stream['id'], INACTIVE_VOL)
                success = True
                
            # Browser 3 (Brave) is active
            elif active_idx == 3:
                # If this is likely a Brave stream
                if "brave" in app_name or "brave" in binary:
                    logger.info(f"Setting Brave stream {stream['id']} to {ACTIVE_VOL}%")
                    set_vol(stream['id'], ACTIVE_VOL)
                else:
                    logger.info(f"Setting non-Brave stream {stream['id']} to {INACTIVE_VOL}%")
                    set_vol(stream['id'], INACTIVE_VOL)
                success = True
    
    # Last resort - handle chromium streams based on active browser
    if active_idx == 1 and streams:
        logger.info("Last resort for Vivaldi - setting chromium streams accordingly")
        vivaldi_found = False
        
        # First pass - identify Vivaldi if possible
        for stream in streams:
            if 'id' in stream:
                app_name = stream.get('app_name', '').lower()
                binary = stream.get('binary', '').lower()
                
                if "vivaldi" in app_name or "vivaldi" in binary:
                    logger.info(f"Found definite Vivaldi stream: {stream['id']}")
                    set_vol(stream['id'], ACTIVE_VOL)
                    vivaldi_found = True
        
        # If no definite Vivaldi stream, use PID matching
        if not vivaldi_found and active_pid:
            for stream in streams:
                if 'id' in stream and stream.get('pid') == active_pid:
                    logger.info(f"Found likely Vivaldi stream by PID: {stream['id']}")
                    set_vol(stream['id'], ACTIVE_VOL)
                    vivaldi_found = True
        
        # If still no Vivaldi, assume first chromium stream is Vivaldi
        if not vivaldi_found:
            chromium_found = False
            for stream in streams:
                if 'id' in stream:
                    app_name = stream.get('app_name', '').lower()
                    if "chromium" in app_name and not chromium_found:
                        logger.info(f"Assuming first Chromium stream is Vivaldi: {stream['id']}")
                        set_vol(stream['id'], ACTIVE_VOL)
                        chromium_found = True
                    elif "chrome" in app_name and not "google" in app_name and not chromium_found:
                        logger.info(f"Assuming Chrome stream is Vivaldi: {stream['id']}")
                        set_vol(stream['id'], ACTIVE_VOL)
                        chromium_found = True
    
    # Additional special case for Browser 2 to handle Chromium streams
    if active_idx == 2 and streams:
        logger.info("Special handling for Browser 2 - ensuring Chromium streams are handled correctly")
        
        # First ensure all Chromium streams that aren't explicitly Google Chrome are set to 30%
        for stream in streams:
            if 'id' in stream:
                app_name = stream.get('app_name', '').lower()
                binary = stream.get('binary', '').lower()
                
                # If it's a Chromium stream but not explicitly Google Chrome
                if "chromium" in app_name and not "google chrome" in app_name:
                    # Only if it's not associated with active PID
                    if not (active_pid and stream.get('pid') == active_pid):
                        logger.info(f"Setting Chromium stream {stream['id']} to {INACTIVE_VOL}% (not Google Chrome)")
                        set_vol(stream['id'], INACTIVE_VOL)
        
        # Then ensure actual Google Chrome streams are at 100%
        for stream in streams:
            if 'id' in stream:
                app_name = stream.get('app_name', '').lower()
                if "google chrome" in app_name:
                    logger.info(f"Ensuring Google Chrome stream {stream['id']} is set to {ACTIVE_VOL}%")
                    set_vol(stream['id'], ACTIVE_VOL)
    
    return success

# ──────────────────────────────────────────────────────────────────────────────
# Microphone (source-output) helpers
# ──────────────────────────────────────────────────────────────────────────────

def list_microphone_streams():
    """Return a list of microphone (source-output) streams with metadata.

    Each element is a dict containing at least:
        id        – the source-output index (string)
        app_name  – application.name property (lower-cased)
        binary    – application.process.binary (lower-cased) if present
        pid       – application.process.id if present (string)
    """
    try:
        txt = run(["pactl", "list", "source-outputs"])
        if not txt:
            logger.info("No microphone source-outputs found")
            return []

        streams = []
        current = {}

        for line in txt.splitlines():
            line = line.strip()

            if line.startswith("Source Output #"):
                if current and 'id' in current:
                    streams.append(current)
                current = {'id': line.split("#")[1].strip()}

            elif "application.name" in line and '=' in line:
                m = PAT_APP_NAME.search(line)
                if m:
                    current['app_name'] = m.group(1)

            elif "application.process.binary" in line:
                m = PAT_APP_PROCESS.search(line)
                if m:
                    current['binary'] = m.group(1)

            elif "application.process.id" in line:
                m = PAT_APP_PID.search(line)
                if m:
                    current['pid'] = m.group(1)

        if current and 'id' in current:
            streams.append(current)

        logger.info(f"Found {len(streams)} microphone streams: {streams}")
        return streams

    except Exception as e:
        logger.error(f"Error listing microphone streams: {e}")
        return []


def adjust_microphone_streams(active_idx: int, streams):
    """Mute/unmute microphone streams so only the active browser is un-muted."""

    if not streams:
        logger.info("No microphone streams to adjust")
        return False

    logger.info(f"Adjusting microphone streams, active browser: {active_idx}")

    # Map browser indices to recognizable names (same as in adjust_stream_volumes)
    browser_names = {
        1: ["vivaldi", "vivaldimail"],
        2: ["chrome", "google chrome", "chromium"],
        3: ["brave", "brave-browser"]
    }
    
    # Special handling for Vivaldi: if Vivaldi is active, don't let "chromium" match to Browser 2
    if active_idx == 1:
        # Remove "chromium" from Browser 2's matching list when Vivaldi is active
        browser_names[2] = [name for name in browser_names[2] if name != "chromium"]
        # Add it to Vivaldi's matches instead
        browser_names[1].append("chromium")
        
        logger.info("Modified browser name matching to prioritize Vivaldi for Chromium streams")
    
    # Obtain active window PID if we have it for more reliable matching
    active_pid = None
    if active_idx <= len(browser_windows) and browser_windows[active_idx-1]:
        active_pid = get_window_pid(browser_windows[active_idx-1])
    
    # Special handling for Browser 2 (Chrome) - need to identify Vivaldi's Chromium stream
    # We'll use PIDs to help differentiate between Chrome's Chromium and Vivaldi's Chromium
    vivaldi_pid = None
    chrome_pid = None
    
    if active_idx == 2:
        # Get PIDs for Browser 1 (Vivaldi) and Browser 2 (Chrome) for more accurate matching
        if len(browser_windows) >= 1 and browser_windows[0]:  # Vivaldi's window
            vivaldi_pid = get_window_pid(browser_windows[0])
        if len(browser_windows) >= 2 and browser_windows[1]:  # Chrome's window
            chrome_pid = get_window_pid(browser_windows[1])
        
        if vivaldi_pid:
            logger.info(f"Found Vivaldi PID: {vivaldi_pid} for enhanced stream matching")
        if chrome_pid:
            logger.info(f"Found Chrome PID: {chrome_pid} for enhanced stream matching")

    success = False

    # Keep track of browser mic streams for special Vivaldi handling
    browser_mic_streams = {1: [], 2: [], 3: []}
    chromium_streams = []
    vivaldi_chromium_streams = []  # Specifically for Vivaldi's Chromium streams

    for stream in streams:
        sid = stream.get('id')
        if not sid:
            continue

        app_name = stream.get('app_name', '').lower()
        binary   = stream.get('binary', '').lower()
        pid      = stream.get('pid', '')

        # Special case for Browser 2 active - identify Vivaldi's Chromium streams by PID
        if active_idx == 2 and "chromium" in app_name and vivaldi_pid and pid:
            # If this Chromium stream's PID is closer to Vivaldi's PID than Chrome's PID
            # or if we're not sure about Chrome's PID, mark it as a potential Vivaldi stream
            if not chrome_pid or abs(int(pid) - int(vivaldi_pid)) < abs(int(pid) - int(chrome_pid)):
                logger.info(f"Identified Chromium stream {sid} (PID {pid}) as likely belonging to Vivaldi")
                vivaldi_chromium_streams.append(sid)

        # Determine which browser (if any) this microphone stream belongs to
        matched_idx = None

        for idx, name_list in browser_names.items():
            if any(name in app_name or name in binary for name in name_list):
                matched_idx = idx
                # Store in browser-specific list for later special handling
                browser_mic_streams[idx].append(sid)
                break

        # Track chromium streams separately
        if "chromium" in app_name and matched_idx is None:
            chromium_streams.append(sid)

        # Chrome vs Vivaldi handling - Browser 2 active case
        if active_idx == 2 and "chromium input" in app_name.lower():
            # When Browser 2 is active, consider all "Chromium input" streams as belonging to Browser 1
            # This is a simplification, but seems to be the most reliable approach given the observed behavior
            logger.info(f"Browser 2 active: Assuming Chromium input stream {sid} belongs to Browser 1 (Vivaldi)")
            matched_idx = 1  # Force match to Browser 1 (Vivaldi)
            browser_mic_streams[1].append(sid)

        # Fallback – PID match with active window (restoring this critical fallback logic)
        if matched_idx is None and active_pid and pid == active_pid:
            matched_idx = active_idx
            browser_mic_streams[active_idx].append(sid)
            logger.info(f"PID match: Stream {sid} (PID {pid}) matches active browser {active_idx}")

        # Decide mute state
        if matched_idx == active_idx:
            logger.info(f"Un-muting mic stream {sid} for active browser {active_idx}")
            set_mute(sid, False)
            success = True
        elif matched_idx in (1, 2, 3):
            logger.info(f"Muting mic stream {sid} (browser {matched_idx}) – not active")
            set_mute(sid, True)
            success = True
        else:
            # Not one of our browsers – leave untouched
            logger.debug(f"Leaving mic stream {sid} untouched (not one of managed browsers)")

    # Special handling for Vivaldi (Browser 1)
    # If we're on Browser 1 and didn't find a Vivaldi mic stream, but found unassigned Chromium streams
    if active_idx == 1 and not browser_mic_streams[1] and chromium_streams:
        logger.info(f"No Vivaldi mic streams found, attempting to use Chromium stream as Vivaldi")
        for sid in chromium_streams:
            logger.info(f"Un-muting Chromium mic stream {sid} for Vivaldi (Browser 1)")
            set_mute(sid, False)
            success = True
            # Break after first one - we only need one mic stream
            break

    return success

# Global variable to store references to spawned browsers
browsers = []

# ─── per-browser instance wrapper ────────────────────────────────────────
class Browser:
    def __init__(self, idx:int, exe:str, url:str):
        self.idx = idx
        self.exe = exe
        self.url = url
        self.profile = Path.home()/f".pb_browser{idx}"
        self.title = f"Browser {idx}"
        self.proc = None
        self.window_id = None
        self.pid = None
        
        # Get the executable name for later searching
        self.exe_name = get_browser_executable_name(exe)
        logger.debug(f"Browser {idx} executable name: {self.exe_name}")

    def launch(self):
        # Check if browser exists
        if not os.path.exists(self.exe):
            logger.error(f"Browser not found: {self.exe}")
            return False
            
        # ensure profile dir exists and is writable
        if self.profile.exists() and not self.profile.is_dir():
            self.profile.unlink()                # was a file → remove
        self.profile.mkdir(exist_ok=True)

        try:
            logger.info(f"Launching Browser {self.idx} with {self.exe} to URL: {self.url}")
            
            # List windows before
            if DEBUG:
                logger.debug("Windows before browser launch:")
                list_all_windows()
                
            # Launch with custom title to make it easier to find
            custom_title = f"Browser{self.idx}_{int(time.time())}"
            self.proc = subprocess.Popen([
                self.exe, "--new-window",
                "--autoplay-policy=no-user-gesture-required", 
                f"--user-data-dir={self.profile}",
                f"--title={custom_title}",
                self.url
            ])
            
            self.pid = str(self.proc.pid)
            logger.info(f"Started process with PID: {self.pid}")
            
            # Wait for window to appear
            for attempt in range(20):  # Try for up to 10 seconds
                time.sleep(0.5)
                
                # List all windows occasionally to help debug
                if attempt % 4 == 0 and DEBUG:
                    logger.debug(f"Looking for browser window (attempt {attempt+1}):")
                    list_all_windows()
                
                # Strategy 1: Find by PID
                window_id = find_window_by_pid(self.pid)
                if window_id:
                    self.window_id = window_id
                    browser_windows[self.idx-1] = window_id  # Store globally
                    subprocess.call(["wmctrl", "-i", "-r", self.window_id, "-N", self.title])
                    logger.info(f"Window found by PID for Browser {self.idx}, ID: {self.window_id}")
                    return True
                    
                # Strategy 2: Find by custom title
                window_id = find_window_by_title_part(custom_title)
                if window_id:
                    self.window_id = window_id
                    browser_windows[self.idx-1] = window_id  # Store globally
                    subprocess.call(["wmctrl", "-i", "-r", self.window_id, "-N", self.title])
                    logger.info(f"Window found by custom title for Browser {self.idx}, ID: {self.window_id}")
                    return True
                    
                # Strategy 3: Find by executable name in window list
                window_id = find_window_by_title_part(self.exe_name.lower())
                if window_id:
                    self.window_id = window_id
                    browser_windows[self.idx-1] = window_id  # Store globally
                    subprocess.call(["wmctrl", "-i", "-r", self.window_id, "-N", self.title])
                    logger.info(f"Window found by exe name for Browser {self.idx}, ID: {self.window_id}")
                    return True
                    
                # For Brave specifically, sometimes it has trouble focusing
                if self.exe_name.lower() in ["brave", "brave-browser"]:
                    window_id = find_window_by_class("Brave")
                    if window_id:
                        self.window_id = window_id
                        browser_windows[self.idx-1] = window_id
                        subprocess.call(["wmctrl", "-i", "-r", self.window_id, "-N", self.title])
                        logger.info(f"Brave window found by class for Browser {self.idx}, ID: {self.window_id}")
                        return True
                    
            logger.warning(f"Could not find window for Browser {self.idx}")
            logger.debug("Final window list:")
            list_all_windows()
            return False
        except Exception as e:
            logger.error(f"Failed to launch Browser {self.idx}: {e}")
            return False

    def focus(self):
        """Focus this browser, using various strategies to ensure it succeeds"""
        # Update our record of windows first
        list_all_windows()
        
        # Strategy 1: Use known window ID
        if self.window_id and focus_window_by_id(self.window_id):
            logger.info(f"Successfully focused Browser {self.idx} by window ID")
            return True
            
        # Strategy 2: Focus by window title
        try:
            logger.debug(f"Focusing Browser {self.idx} with title: {self.title}")
            result = subprocess.call(["wmctrl", "-a", self.title], stderr=subprocess.DEVNULL)
            if result == 0:
                logger.info(f"Successfully focused Browser {self.idx} by title")
                return True
        except Exception as e:
            logger.error(f"Error focusing by title: {e}")
            
        # Strategy 3: Try to find window by PID
        if self.pid:
            window_id = find_window_by_pid(self.pid)
            if window_id:
                self.window_id = window_id
                browser_windows[self.idx-1] = window_id  # Update global record
                if focus_window_by_id(window_id):
                    logger.info(f"Successfully focused Browser {self.idx} by PID")
                    return True
                    
        # Strategy 4: For Brave specifically, use class name
        if self.exe_name.lower() in ["brave", "brave-browser"]:
            window_id = find_window_by_class("Brave")
            if window_id:
                self.window_id = window_id
                browser_windows[self.idx-1] = window_id
                if focus_window_by_id(window_id):
                    logger.info(f"Successfully focused Browser {self.idx} (Brave) by class")
                    return True
                    
        # Strategy 5: Last resort - try to force window focus using xdotool if available
        try:
            if self.window_id:
                subprocess.call(["xdotool", "windowactivate", self.window_id], stderr=subprocess.DEVNULL)
                logger.info(f"Tried focusing Browser {self.idx} using xdotool")
                return True
        except Exception:
            pass
            
        logger.warning(f"Could not focus window for Browser {self.idx}")
        return False

# ─── core switcher ──────────────────────────────────────────────────
class Switcher:
    def __init__(self):
        # Initialize browsers with specific URLs
        global browsers
        browsers = [Browser(i+1, exe, url) for i, (exe, url) in enumerate(zip(BROWSERS, BROWSER_URLS))]
        
        # Launch browsers
        for b in browsers:
            b.launch()
            time.sleep(1)  # Brief delay between browser launches
        
        # Wait a bit for browsers to start
        GLib.timeout_add_seconds(3, self.check_audio_streams)
            
    def check_audio_streams(self):
        """Check if audio streams are available after startup"""
        streams = list_audio_streams()
        if streams:
            logger.info(f"Found {len(streams)} audio streams after startup")
        else:
            logger.warning("No audio streams detected after startup")
        return False  # Don't repeat
    
    def activate(self, num:int):
        logger.info(f"Activating Browser {num}")
        if not 1 <= num <= 3: 
            logger.warning(f"Invalid browser number: {num}")
            return False
            
        # Focus the window
        success = browsers[num-1].focus()
        
        # Get current audio streams
        streams = list_audio_streams()
        if streams:
            # Adjust volumes
            adjust_stream_volumes(num, streams)

            # Handle microphone streams
            mic_streams = list_microphone_streams()
            if mic_streams:
                adjust_microphone_streams(num, mic_streams)
            else:
                logger.info("No microphone streams detected")

        if streams:
            return True
        else:
            logger.warning("No audio streams found!")
            return False

# ─── GTK UI ─────────────────────────────────────────────────────────
class UI(Gtk.Window):
    def __init__(self):
        Gtk.Window.__init__(self, title="Browser Audio Switcher")
        self.set_default_size(400, 200)
        self.set_resizable(False)
        self.connect("destroy", Gtk.main_quit)
        
        # Set a dark theme if available
        settings = Gtk.Settings.get_default()
        if hasattr(settings, 'set_property'):
            settings.set_property("gtk-application-prefer-dark-theme", True)
        
        vb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        vb.set_margin_top(10)
        vb.set_margin_bottom(10)
        vb.set_margin_start(10)
        vb.set_margin_end(10)
        self.add(vb)
        
        # Create switcher before buttons
        self.sw = Switcher()
        
        # Browser info
        info_frame = Gtk.Frame(label="Browser Profiles")
        vb.pack_start(info_frame, True, True, 0)
        
        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        info_box.set_margin_top(5)
        info_box.set_margin_bottom(5)
        info_box.set_margin_start(5)
        info_box.set_margin_end(5)
        info_frame.add(info_box)
        
        # Add browser info with video descriptions
        video_descriptions = [
            "McDonald's beeping sounds",
            "Tom & Jerry cartoon",
            "Spring nature sounds"
        ]
        
        browser_info = [
            f"Browser 1 ({BROWSERS[0].split('/')[-1]}): {video_descriptions[0]}",
            f"Browser 2 ({BROWSERS[1].split('/')[-1]}): {video_descriptions[1]}",
            f"Browser 3 ({BROWSERS[2].split('/')[-1]}): {video_descriptions[2]}"
        ]
        
        for info in browser_info:
            info_box.pack_start(Gtk.Label(label=info, xalign=0), False, False, 0)
        
        # Button box
        hb = Gtk.Box(spacing=8)
        vb.pack_start(hb, False, False, 5)
        
        # Create color variants for the buttons
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(b"""
        .browser1-button { background: #7289DA; color: white; font-weight: bold; }
        .browser2-button { background: #DE4C4A; color: white; font-weight: bold; }
        .browser3-button { background: #EF7E14; color: white; font-weight: bold; }
        """)
        
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), 
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        
        # Browser buttons
        browser_labels = [
            "Browser 1",
            "Browser 2", 
            "Browser 3"
        ]
        
        button_classes = [
            "browser1-button",
            "browser2-button",
            "browser3-button"
        ]
        
        for i in (1, 2, 3):
            btn = Gtk.Button(label=browser_labels[i-1])
            # Add custom class for coloring
            btn.get_style_context().add_class(button_classes[i-1])
            btn.connect("clicked", self.on_browser_button_clicked, i)
            hb.pack_start(btn, True, True, 0)

        # Status label
        self.status_label = Gtk.Label(label="Ready - Click a button to switch browsers")
        vb.pack_start(self.status_label, False, False, 5)

        # Audio control info
        self.audio_info = Gtk.Label(label="No audio streams detected")
        self.audio_info.set_line_wrap(True)
        vb.pack_start(self.audio_info, False, False, 0)
        
        # Control buttons box
        control_box = Gtk.Box(spacing=8)
        vb.pack_start(control_box, False, False, 5)
        
        # Refresh button for audio
        refresh_btn = Gtk.Button(label="Refresh Audio")
        refresh_btn.connect("clicked", self.on_refresh_clicked)
        control_box.pack_start(refresh_btn, True, True, 0)
        
        # Debug button to list windows
        debug_btn = Gtk.Button(label="List Windows")
        debug_btn.connect("clicked", self.on_debug_clicked)
        control_box.pack_start(debug_btn, True, True, 0)

        quitb = Gtk.Button(label="Quit")
        quitb.connect("clicked", Gtk.main_quit)
        vb.pack_start(quitb, False, False, 0)
        
        # Timer to periodically refresh audio info
        GLib.timeout_add_seconds(5, self.refresh_audio_info)
        
        self.show_all()
    
    def refresh_audio_info(self):
        """Refresh audio stream information"""
        streams = list_audio_streams()
        if streams:
            self.audio_info.set_text(f"Found {len(streams)} audio streams")
        else:
            self.audio_info.set_text("No audio streams detected")
        return True  # Keep the timer running
        
    def on_refresh_clicked(self, button):
        """Handle refresh button click"""
        self.status_label.set_text("Refreshing audio information...")
        self.refresh_audio_info()
        self.status_label.set_text("Audio information refreshed")
    
    def on_debug_clicked(self, button):
        """Handle debug button click to list windows"""
        self.status_label.set_text("Listing windows...")
        output = list_all_windows()
        self.status_label.set_text("Windows listed in log")
        
    def on_browser_button_clicked(self, button, browser_num):
        logger.info(f"Button clicked for Browser {browser_num}")
        self.status_label.set_text(f"Activating Browser {browser_num}...")
        
        # Schedule the activate call and update status after
        def activate_and_update():
            success = self.sw.activate(browser_num)
            self.refresh_audio_info()
            self.status_label.set_text(f"Browser {browser_num} active" if success else f"Failed to activate Browser {browser_num}")
            return False
            
        # Use idle_add to ensure GTK operations happen on the main thread
        GLib.idle_add(activate_and_update)

# ─── run ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    signal.signal(signal.SIGINT, lambda *_: Gtk.main_quit())
    try:
        logger.info("Starting Browser Audio Switcher")
        UI()
        Gtk.main()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
