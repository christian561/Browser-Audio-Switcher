
# Browser Audio Switcher

A Linux utility to seamlessly switch between multiple browser-based voice chat applications with a single click. Perfect for managing multiple meetings, voice chats, or online games simultaneously.

![Browser Audio Switcher](https://github.com/user-attachments/assets/295f0d5c-436e-4e2e-b8e8-8b9d80b4f97f)

## Features

- Switch between up to 3 browser sessions with a single click
- **Smart Audio Management**: Only the active browser plays at full volume (inactive browsers at 30%)
- **Intelligent Microphone Control**: Mic is only active in the foreground browser
- Separate browser profiles ensure independent sessions
- Colorful, intuitive GUI interface
- Works with most Chromium-based browsers

## Requirements

- Linux (Debian/Ubuntu/Mint recommended)
- Python 3.6+
- GTK3
- Multiple Chromium-based browsers:
  - Recommended: Vivaldi, Google Chrome, and Brave
  - Other combinations possible with configuration
- PulseAudio sound system
- wmctrl (window management)

## Dependencies

Install required system packages:
```bash
sudo apt update
sudo apt install python3-pip python3-gi wmctrl
```

Install Python dependencies:
```bash
pip3 install pathlib
```

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/browser-audio-switcher.git
```

2. Make the script executable:
```bash
chmod +x phoneburner_switcher.py
```

3. Install the supported browsers if not already installed:
   - [Vivaldi](https://vivaldi.com/download/)
   - [Google Chrome](https://www.google.com/chrome/)
   - [Brave](https://brave.com/download/)

## Usage

Run the application:
```bash
./browser_audio_switcher.py
```

### First Launch

On first launch, the application will:
1. Create separate browser profiles in your home directory
2. Open each browser with a test audio stream
3. Display a control panel with three colored buttons

### Switching Between Browsers

- Click on "Browser 1" (blue) to activate Vivaldi
- Click on "Browser 2" (red) to activate Google Chrome
- Click on "Browser 3" (orange) to activate Brave

When switching, the application will:
- Focus the selected browser window
- Turn up the volume for that browser to 100%
- Reduce other browsers' volume to 30%
- Enable microphone for the active browser only
- Mute microphone for all inactive browsers

### Using for Voice Chat

1. Navigate each browser to a different voice chat service (Zoom, Discord, Google Meet, etc.)
2. Sign into separate accounts if needed
3. Join your different meetings/voice chats
4. Use the switcher to control which one is active

## Configuration

### Changing Browsers

Edit the following variables at the top of the script:

```python
BROWSERS = [
    "/usr/bin/vivaldi-stable",   # Browser 1
    "/usr/bin/google-chrome",    # Browser 2
    "/usr/bin/brave-browser"     # Browser 3
]
```

### Changing Default URLs

```python
BROWSER_URLS = [
    "https://www.youtube.com/watch?v=I2JRIHQ2Z68",  # Test stream for Browser 1
    "https://www.youtube.com/watch?v=MTJ-_gvNmbA",  # Test stream for Browser 2
    "https://www.youtube.com/watch?v=Nsi3zUriYgc"   # Test stream for Browser 3
]
```

## How It Works

1. **Browser Management**: The app launches separate browser instances with isolated profiles
2. **Window Control**: Uses wmctrl to focus and manage browser windows
3. **Audio Control**: 
   - Identifies audio streams from each browser via PulseAudio
   - Adjusts volume for active/inactive browsers
   - Manages microphone input routing

## Troubleshooting

### Browsers not launching
- Verify paths in the BROWSERS array
- Check if you have permissions to execute the browsers

### Audio not switching correctly
- Ensure PulseAudio is running (`pulseaudio --check`)
- Try launching browsers manually first

### Windows not focusing
- Make sure wmctrl is installed (`which wmctrl`)
- Check if your window manager supports wmctrl commands

## License

MIT License - See LICENSE file for details

## Acknowledgments

- Created for managing multiple voice chat sessions simultaneously
- Inspired by the need to participate in multiple online meetings

---

## Technical Details

The application uses:
- GTK3 for the user interface
- PulseAudio CLI commands for audio management
- wmctrl for window management
- subprocess for browser launching and control

The separate browser profiles ensure that cookies, history, and settings are isolated between instances, allowing you to be logged into different accounts simultaneously.
