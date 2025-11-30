# 🟨 Coin Collector – Real-Time Multiplayer Game (Python + TCP)

A real-time **multiplayer Coin Collector** game built entirely using:

- **Python**
- **Raw TCP sockets** (no networking middleware)
- **Pygame** for rendering
- **Custom interpolation & prediction**
- **200ms simulated latency**
- **Authoritative server architecture**

This project demonstrates core real-time networking concepts without game engines or auto-sync frameworks like Photon, Mirror, Netcode, etc.

---

# 🚀 Features

### 🎮 Gameplay
- Multiple players move around a 2D map.
- Randomly spawning coins.
- Player collects a coin by touching it.
- Server validates collisions & updates scores.

### 🛰 Networking
- **Raw TCP socket communication**
- Clients send **only input** (WASD/Arrow keys)
- Server:
  - Moves all players
  - Spawns coins
  - Detects collisions
  - Updates scores
  - Broadcasts authoritative state

### ⏱ Latency Simulation
Fully custom latency injection:
- `INCOMING_LATENCY = 0.1`
- `OUTGOING_LATENCY = 0.1`

Total ≈ **200ms round-trip**.

### 🧠 Smoothness (Interpolation + Prediction)
- Remote players: **interpolation** (glide smoothly between updates)
- Local player: **client-side prediction + smooth correction**
- No stuttering, no snapping

---

# 📁 Project Structure


---

# 🧠 Architecture Overview

## 1. Server Authority (Security)
The server is the **only source of truth**.

Clients **cannot**:
- Modify their position
- Claim coin pickups
- Change their score
- Spawn items or players

Clients only send:
``` JSON
{
  "type": "input",
  "keys": { "up": true, "left": false, ... }
}
```
## The server:

Processes movement

Validates coin collision:

dist = math.hypot(px - cx, py - cy)
if dist < PLAYER_RADIUS + COIN_RADIUS:
    score += 1


Sends back authoritative state snapshots.

### 2. Tick Loop (Server Side)

The server runs at 20 ticks/sec:

Update player positions

Spawn coins

Detect coin collisions

Build state message

Send to all clients (after artificial delay)

### 3. Interpolation (Client Side)

For every remote player:

Store:

Previous position

Latest server position

Interpolation timer

Render position = blend of last & current:

alpha = min(t / INTERP_DURATION, 1.0)
x_draw = x_prev + (x - x_prev) * alpha


This produces smooth motion even with delayed updates.

### 4. Client-Side Prediction (Local Player Only)

Your own player moves instantly in response to input.
When server state arrives later:

Apply smooth correction, not a snap:

x_draw += (server_x - x_draw) * 0.15


This keeps the game responsive even with added latency.

# 🛠 Installation
### 1. Create & activate virtual environment (optional but recommended):
python -m venv venv

Windows:
venv\Scripts\activate

macOS / Linux:
source venv/bin/activate

### 2. Install dependencies
pip install pygame


Or if requirements.txt is added:

pip install -r requirements.txt

# ▶️ Running the Game
### Step 1: Start the server
python server.py


Expected output:

[SERVER] Starting on 127.0.0.1:9000
[SERVER] Waiting for connections ...

### Step 2: Run a client (Player 1)

In a new terminal:

python client.py


A Pygame window will open.

### Step 3: Run more clients (Player 2, Player 3…)

Open another terminal:

python client.py


Each client represents a different player.

# 🎮 Controls

Inside each Pygame window:

Click to focus

Move:

W / A / S / D

or Arrow keys

You = green square
Other players = blue squares
Coins = yellow circles

Score shown in the top-left.
# 📊 Evaluation Criteria Mapping
## ✔ Server Authority

Server handles all movement, collisions, scoring.

Client only sends inputs.

Server state is canonical.

## ✔ 200ms Latency Simulation

Custom sleep() injected into incoming & outgoing server messages.

## ✔ Smooth Rendering (Interpolation)

Remote entities are interpolated between server snapshots.

✔ Responsiveness (Prediction + Correction)

Local player moves instantly

Smoothly reconciles with server-authoritative state
