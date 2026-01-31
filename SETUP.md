# DSBG-Shuffle Setup Guide

This guide provides detailed, step-by-step instructions for setting up and running the DSBG-Shuffle Streamlit app. Whether you're new to coding or have never heard of Docker, this guide will walk you through everything you need to know.

## Table of Contents

- [What is DSBG-Shuffle?](#what-is-dsbg-shuffle)
- [Method 1: Local Setup (Running Directly on Your Computer)](#method-1-local-setup-running-directly-on-your-computer)
- [Method 2: Docker Setup (Running in a Container)](#method-2-docker-setup-running-in-a-container)
- [Accessing the App from Other Devices](#accessing-the-app-from-other-devices)
- [Troubleshooting](#troubleshooting)

---

## What is DSBG-Shuffle?

DSBG-Shuffle is a companion app for **Dark Souls: The Board Game** that helps you manage encounters, events, bosses, campaigns, and character builds. The app can run entirely offline on your computer, making it perfect for use during game sessions.

You have two ways to run this app:
1. **Local Setup**: Install Python and run it directly on your computer
2. **Docker Setup**: Use Docker to run the app in an isolated container (easier, but requires Docker installation)

---

## Method 1: Local Setup (Running Directly on Your Computer)

This method involves installing Python on your computer and running the app directly. This is great if you want to make modifications or prefer not to use Docker.

### Prerequisites

Before you begin, you'll need:
- **Python 3.11 or newer** installed on your computer
- **pip** (Python's package installer - this comes with Python)
- **A terminal/command prompt** to enter commands

### Step 1: Install Python

If you don't have Python installed:

#### Windows:
1. Go to [python.org/downloads](https://www.python.org/downloads/)
2. Click the "Download Python 3.11" (or newer) button
3. Run the installer
4. **IMPORTANT**: Check the box that says "Add Python to PATH" during installation
5. Click "Install Now"
6. Once complete, open Command Prompt and type: `python --version`
   - You should see something like "Python 3.11.x"

#### macOS:
1. Go to [python.org/downloads](https://www.python.org/downloads/)
2. Download the macOS installer for Python 3.11 or newer
3. Run the installer and follow the prompts
4. Open Terminal (found in Applications > Utilities)
5. Type: `python3 --version`
   - You should see something like "Python 3.11.x"

#### Linux:
Most Linux distributions come with Python. Open a terminal and check:
```bash
python3 --version
```
If you need to install Python 3.11 or newer, use your distribution's package manager:
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install python3.11 python3-pip

# Fedora
sudo dnf install python3.11

# Arch
sudo pacman -S python
```

### Step 2: Download the DSBG-Shuffle Code

You need to get the code onto your computer:

#### Option A: Using Git (Recommended)
If you have Git installed:
```bash
git clone https://github.com/DanDuhon/DSBG-Shuffle-streamlit.git
cd DSBG-Shuffle-streamlit
```

#### Option B: Download as ZIP
1. Go to [https://github.com/DanDuhon/DSBG-Shuffle-streamlit](https://github.com/DanDuhon/DSBG-Shuffle-streamlit)
2. Click the green "Code" button
3. Click "Download ZIP"
4. Extract the ZIP file to a folder on your computer
5. Open your terminal/command prompt and navigate to that folder:
   ```bash
   cd path/to/DSBG-Shuffle-streamlit
   ```

### Step 3: Install Required Python Packages

The app needs several Python packages to run. Install them all with one command:

#### Windows:
```bash
pip install -r requirements.txt
```

#### macOS/Linux:
```bash
pip3 install -r requirements.txt
```

This will download and install:
- **Streamlit**: The framework that powers the web interface
- **Pillow**: For image processing
- **Requests**: For making web requests
- **streamlit-javascript**: For JavaScript integration

This may take a minute or two. You'll see progress as packages are downloaded and installed.

### Step 4: Run the App

Now you're ready to start the app!

#### Windows:
```bash
streamlit run app.py
```

#### macOS/Linux:
```bash
streamlit run app.py
```

You should see output like:
```
You can now view your Streamlit app in your browser.

Local URL: http://localhost:8501
Network URL: http://192.168.1.100:8501
```

### Step 5: Access the App

1. Your web browser should automatically open to `http://localhost:8501`
2. If it doesn't, manually open your browser and go to: **http://localhost:8501**
3. You should see the DSBG-Shuffle app interface!

### Step 6: Using the App

- The app will continue running in your terminal/command prompt window
- **Don't close this window** while you're using the app
- To stop the app: Press `Ctrl+C` in the terminal window
- To restart it: Run `streamlit run app.py` again

### Data Persistence

When running locally:
- Your settings, saved encounters, and campaigns are stored in the `data/` folder
- These files are saved automatically and will persist between sessions
- The main settings file is: `data/user_settings.json`

---

## Method 2: Docker Setup (Running in a Container)

Docker is a tool that packages applications and all their dependencies into "containers" - isolated environments that run the same way on any computer. Think of it like a virtual machine, but much lighter and faster.

### Why Use Docker?

- **Easier setup**: No need to install Python or manage dependencies
- **Consistency**: Runs the same way on any computer
- **Isolation**: Doesn't interfere with other software on your computer
- **Easy updates**: Just rebuild the container to get the latest version

### Prerequisites

You'll need:
- **Docker Desktop** (for Windows/Mac) or **Docker Engine** (for Linux)
- **Docker Compose** (usually included with Docker Desktop)

### Step 1: Install Docker

#### Windows:
1. Go to [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/)
2. Download and run the installer
3. Follow the installation wizard
4. You may need to enable WSL 2 (Windows Subsystem for Linux) if prompted
5. Restart your computer if required
6. Start Docker Desktop from the Start menu
7. Wait for Docker to fully start (you'll see a green icon in the system tray)
8. Open Command Prompt or PowerShell and verify installation:
   ```bash
   docker --version
   docker compose version
   ```
   You should see version numbers for both commands.

#### macOS:
1. Go to [Docker Desktop for Mac](https://www.docker.com/products/docker-desktop/)
2. Download the installer for your Mac type:
   - **Intel chip**: Download for Intel
   - **Apple Silicon (M1/M2/M3)**: Download for Apple chip
3. Open the downloaded .dmg file
4. Drag Docker to your Applications folder
5. Open Docker from Applications
6. You may need to enter your password to approve system changes
7. Wait for Docker to start (whale icon in menu bar)
8. Open Terminal and verify:
   ```bash
   docker --version
   docker compose version
   ```

#### Linux:
Follow the official installation guide for your distribution: [Install Docker Engine](https://docs.docker.com/engine/install/)

**For Ubuntu/Debian:**
```bash
# Update package index
sudo apt update

# Install prerequisites
sudo apt install ca-certificates curl gnupg

# Add Docker's official GPG key
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# Set up the repository
echo \
  "deb [arch="$(dpkg --print-architecture)" signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  "$(. /etc/os-release && echo "$VERSION_CODENAME")" stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker Engine
sudo apt update
sudo apt install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Verify installation
docker --version
docker compose version
```

### Step 2: Download the DSBG-Shuffle Code

Same as Method 1, Step 2 - get the code using Git or by downloading the ZIP file.

### Step 3: Build and Run with Docker Compose

Docker Compose is a tool that makes it easy to run Docker applications. The DSBG-Shuffle repository includes a `docker-compose.yaml` file that has all the configuration already set up for you.

1. Open your terminal/command prompt
2. Navigate to the DSBG-Shuffle-streamlit folder:
   ```bash
   cd path/to/DSBG-Shuffle-streamlit
   ```

3. Build and start the Docker container:
   ```bash
   docker compose up --build
   ```

**What this command does:**
- `docker compose`: Uses Docker Compose to manage the application
- `up`: Starts the application
- `--build`: Builds the Docker image first (this creates the container with all dependencies)

**First-time run**: This will take a few minutes because Docker needs to:
1. Download the Python base image
2. Install all the app dependencies
3. Copy the app code into the container
4. Start the application

You'll see a lot of output. Eventually, you'll see something like:
```
dsbg  | You can now view your Streamlit app in your browser.
dsbg  | 
dsbg  | Network URL: http://0.0.0.0:8501
```

### Step 4: Access the App

Open your web browser and go to:
- **http://localhost:8501** (on the same computer)

That's it! The app is now running.

### Step 5: Managing the Docker Container

**To stop the app:**
- Press `Ctrl+C` in the terminal where it's running
- Or run this command in a new terminal:
  ```bash
  docker compose down
  ```

**To start it again:**
```bash
docker compose up
```
(You don't need `--build` unless you've updated the code)

**To run in the background (detached mode):**
```bash
docker compose up -d
```
This runs the container in the background so you can close the terminal.

**To view logs when running in background:**
```bash
docker compose logs -f
```
(Press `Ctrl+C` to stop viewing logs; the app keeps running)

**To stop a background container:**
```bash
docker compose down
```

### Data Persistence

Docker stores your data in a **volume** - a special storage area that persists even when you stop or rebuild the container.

- Your settings, encounters, and campaigns are saved automatically
- This data persists when you:
  - Stop the container
  - Restart the container
  - Update the app and rebuild the container

**To reset all data (start fresh):**

⚠️ **Warning**: This deletes all your saved settings, encounters, and campaigns!

```bash
# Stop the container
docker compose down

# Remove the data volume
docker volume rm dsbg-shuffle-streamlit_dsbg_data

# Start fresh
docker compose up
```

**To backup your data:**

The data is stored in a Docker volume named `dsbg-shuffle-streamlit_dsbg_data`. To back it up, you can copy it from a running container:

```bash
# Make sure the container is running
docker compose up -d

# Copy data from the container to your computer
docker cp dsbg:/app/data ./data-backup
```

---

## Accessing the App from Other Devices

One of the great features of DSBG-Shuffle is that you can access it from other devices on your network (like a tablet at your gaming table).

### Step 1: Find Your Computer's IP Address

#### Windows:
1. Open Command Prompt
2. Type: `ipconfig`
3. Look for "IPv4 Address" under your active network adapter
4. It will look something like: `192.168.1.100`

#### macOS:
1. Open Terminal
2. Type: `ifconfig | grep "inet " | grep -v 127.0.0.1`
3. Look for an address starting with `192.168.` or `10.` (not `127.0.0.1`)
   - Example: `192.168.1.100` or `10.0.1.50`

Or use the GUI:
1. System Preferences > Network
2. Select your active connection (Wi-Fi or Ethernet)
3. Your IP address is shown on the right

#### Linux:
```bash
hostname -I
```
Or:
```bash
ip addr show
```
Look for an address like `192.168.1.100`

### Step 2: Access from Another Device

On your other device (phone, tablet, another computer):

1. Make sure it's connected to the **same Wi-Fi network** as the computer running DSBG-Shuffle
2. Open a web browser
3. Go to: `http://YOUR-IP-ADDRESS:8501`
   - For example: `http://192.168.1.100:8501`

### Troubleshooting Network Access

**If other devices can't connect:**

#### Windows Firewall:
Windows Firewall might be blocking the connection.

1. Open Windows Defender Firewall
2. Click "Advanced settings"
3. Click "Inbound Rules" in the left panel
4. Click "New Rule..." in the right panel
5. Select "Port" and click Next
6. Select "TCP" and enter "8501" in Specific local ports
7. Select "Allow the connection"
8. Check all profiles (Domain, Private, Public)
9. Give it a name like "DSBG-Shuffle"
10. Click Finish

Or use this command in an **Administrator** PowerShell:
```powershell
New-NetFirewallRule -DisplayName "DSBG-Shuffle" -Direction Inbound -Protocol TCP -LocalPort 8501 -Action Allow
```

#### macOS Firewall:
If you have the firewall enabled:
1. System Preferences > Security & Privacy > Firewall
2. Click "Firewall Options"
3. Ensure Python or Docker is allowed
4. Or temporarily disable the firewall for testing

#### Linux Firewall (ufw):
```bash
sudo ufw allow 8501/tcp
```

#### Router/Network Issues:
- Some routers have "client isolation" enabled on Wi-Fi, which prevents devices from talking to each other
- This is common on guest networks
- Try connecting both devices to the main network instead of a guest network

---

## Troubleshooting

### Common Issues and Solutions

#### "Command not found: python" or "Command not found: streamlit"

**Problem**: Python or Streamlit isn't installed or not in your PATH.

**Solution**:
- On Windows: Make sure you checked "Add Python to PATH" during installation
- On macOS/Linux: Try using `python3` instead of `python`, and `pip3` instead of `pip`
- Verify Python is installed: `python --version` or `python3 --version`
- Reinstall Streamlit: `pip install -r requirements.txt`

#### "Address already in use" or "Port 8501 is already in use"

**Problem**: Something else is using port 8501, or you already have DSBG-Shuffle running.

**Solution**:
- Check if you have another instance running and close it
- Change the port by running: `streamlit run app.py --server.port 8502`
- Then access the app at `http://localhost:8502`

#### Docker: "Cannot connect to the Docker daemon"

**Problem**: Docker Desktop isn't running.

**Solution**:
- Start Docker Desktop
- Wait for it to fully start (green icon in system tray/menu bar)
- Try your command again

#### Docker: "Error response from daemon: pull access denied"

**Problem**: Docker can't download required images.

**Solution**:
- Check your internet connection
- Try: `docker compose up --build` again
- If on Linux, make sure your user is in the docker group: `sudo usermod -aG docker $USER`
  - Then log out and back in

#### App starts but shows errors or missing images

**Problem**: The app isn't running from the correct directory.

**Solution**:
- Make sure you're in the repository root directory
- The app expects to find the `data/` and `assets/` folders
- Run: `ls` (macOS/Linux) or `dir` (Windows) to verify you see `app.py`, `data/`, and `assets/`

#### Changes not showing up in Docker

**Problem**: You modified code but don't see the changes.

**Solution**:
- Rebuild the Docker image: `docker compose up --build`
- The `--build` flag tells Docker to rebuild the image with your changes

#### Slow performance or app crashes

**Problem**: Memory issues or large cached data.

**Solution**:
- **Local**: Delete cached Streamlit data: Close the app, delete the `.streamlit` cache folder, restart
- **Docker**: Restart the container: `docker compose restart`
- Clear browser cache
- Close other applications to free up memory

#### "ModuleNotFoundError" when running locally

**Problem**: Required Python packages aren't installed.

**Solution**:
```bash
pip install -r requirements.txt
# or on macOS/Linux:
pip3 install -r requirements.txt
```

#### Can't access from other devices

**Problem**: Firewall or network configuration blocking access.

**Solution**:
- See [Accessing the App from Other Devices](#accessing-the-app-from-other-devices) section
- Check firewall settings
- Ensure both devices are on the same network
- Verify your IP address hasn't changed
- Check for "client isolation" on your router

---

## Additional Resources

### Learn More About the App

- See the [README.md](README.md) for information about:
  - App features and modes
  - Data persistence
  - Streamlit Cloud deployment
  - Supabase configuration

### Learn More About the Tools

- **Python**: [python.org](https://www.python.org/)
- **Streamlit**: [streamlit.io](https://streamlit.io/)
- **Docker**: [docker.com](https://www.docker.com/)
- **Docker Compose**: [docs.docker.com/compose](https://docs.docker.com/compose/)

### Getting Help

If you encounter issues not covered in this guide:

1. Check if there's an existing issue on the [GitHub repository](https://github.com/DanDuhon/DSBG-Shuffle-streamlit/issues)
2. Create a new issue with:
   - Your operating system
   - Whether you're using local or Docker setup
   - The exact error message you're seeing
   - What you were trying to do when the error occurred

---

## Quick Reference

### Local Setup Commands
```bash
# Install dependencies
pip install -r requirements.txt

# Run the app
streamlit run app.py

# Access the app
# http://localhost:8501
```

### Docker Commands
```bash
# Build and start (first time or after code changes)
docker compose up --build

# Start (after first build)
docker compose up

# Start in background
docker compose up -d

# View logs
docker compose logs -f

# Stop
docker compose down

# Reset all data
docker compose down
docker volume rm dsbg-shuffle-streamlit_dsbg_data
```

### Network Access
```bash
# Find your IP address

# Windows
ipconfig

# macOS (look for 192.168.x.x or 10.x.x.x, not 127.0.0.1)
ifconfig | grep "inet "

# Linux
hostname -I

# Then access from other devices:
# http://YOUR-IP:8501
```

---

Happy gaming with Dark Souls: The Board Game! 🎲⚔️
