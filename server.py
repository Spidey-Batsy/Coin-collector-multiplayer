import socket
import threading
import json
import time
import random
import math

HOST = "127.0.0.1"
PORT = 8765

TICK_RATE = 20           # 20 updates per second
DT = 1.0 / TICK_RATE
INCOMING_LATENCY = 0.1   # 100ms on messages from client
OUTGOING_LATENCY = 0.1   # 100ms on messages to client

MAP_WIDTH = 800
MAP_HEIGHT = 600
PLAYER_SPEED = 200.0     # pixels per second
PLAYER_RADIUS = 20
COIN_RADIUS = 15

MAX_COINS = 5

players = {}             # conn -> player dict
players_lock = threading.Lock()

coins = []               # list of {id, x, y}
coins_lock = threading.Lock()

next_player_id = 1
next_coin_id = 1


def send_message(conn, obj):
    """Send a JSON message with artificial latency."""
    data = json.dumps(obj) + "\n"
    try:
        # Outgoing latency (server -> client)
        time.sleep(OUTGOING_LATENCY)
        conn.sendall(data.encode("utf-8"))
    except Exception:
        # Connection might be closed; ignore
        pass


def spawn_coin():
    """Spawn a single coin at a random position."""
    global next_coin_id
    x = random.randint(50, MAP_WIDTH - 50)
    y = random.randint(50, MAP_HEIGHT - 50)
    coin = {"id": next_coin_id, "x": x, "y": y}
    next_coin_id += 1
    coins.append(coin)


def handle_client(conn, addr):
    """Handle input from a single client."""
    global next_player_id
    print(f"[SERVER] New connection from {addr}")
    f = conn.makefile("r")
    player_id = None

    try:
        for line in f:
            line = line.strip()
            if not line:
                break

            # Incoming latency (client -> server)
            time.sleep(INCOMING_LATENCY)

            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue

            mtype = msg.get("type")

            if mtype == "join":
                # Register a new player
                with players_lock:
                    player_id = next_player_id
                    next_player_id += 1
                    start_x = random.randint(100, MAP_WIDTH - 100)
                    start_y = random.randint(100, MAP_HEIGHT - 100)
                    players[conn] = {
                        "id": player_id,
                        "x": float(start_x),
                        "y": float(start_y),
                        "score": 0,
                        "input": {"up": False, "down": False, "left": False, "right": False},
                    }
                print(f"[SERVER] Player {player_id} joined from {addr}")

                # Send welcome message with assigned ID
                send_message(conn, {"type": "welcome", "id": player_id})

            elif mtype == "input" and player_id is not None:
                keys = msg.get("keys", {})
                with players_lock:
                    p = players.get(conn)
                    if p:
                        p["input"] = {
                            "up": bool(keys.get("up", False)),
                            "down": bool(keys.get("down", False)),
                            "left": bool(keys.get("left", False)),
                            "right": bool(keys.get("right", False)),
                        }

    except Exception as e:
        print(f"[SERVER] Error with client {addr}: {e}")

    finally:
        print(f"[SERVER] Connection closed from {addr}")
        with players_lock:
            if conn in players:
                del players[conn]
        conn.close()


def game_loop():
    """Authoritative game loop: movement, coins, collisions, broadcasting."""
    last_spawn_time = time.time()

    while True:
        start_time = time.time()

        # Spawn coins periodically
        with coins_lock:
            now = time.time()
            if len(coins) < MAX_COINS and (now - last_spawn_time) > 2.0:
                spawn_coin()
                last_spawn_time = now

        # Snapshot players
        with players_lock:
            player_items = list(players.items())

        # Update player positions based on last input
        for conn, p in player_items:
            keys = p["input"]
            dx = 0.0
            dy = 0.0
            if keys.get("up"):
                dy -= 1
            if keys.get("down"):
                dy += 1
            if keys.get("left"):
                dx -= 1
            if keys.get("right"):
                dx += 1

            length = math.hypot(dx, dy)
            if length > 0:
                dx /= length
                dy /= length

            p["x"] += dx * PLAYER_SPEED * DT
            p["y"] += dy * PLAYER_SPEED * DT

            # Clamp to map boundaries
            p["x"] = max(PLAYER_RADIUS, min(MAP_WIDTH - PLAYER_RADIUS, p["x"]))
            p["y"] = max(PLAYER_RADIUS, min(MAP_HEIGHT - PLAYER_RADIUS, p["y"]))

        # Handle collisions with coins
        with coins_lock:
            to_remove = set()
            for coin in coins:
                cx, cy = coin["x"], coin["y"]
                for conn, p in player_items:
                    px, py = p["x"], p["y"]
                    dist = math.hypot(px - cx, py - cy)
                    if dist < (PLAYER_RADIUS + COIN_RADIUS):
                        # Player collects coin
                        p["score"] += 1
                        to_remove.add(coin["id"])
                        break  # coin already collected

            if to_remove:
                coins[:] = [c for c in coins if c["id"] not in to_remove]

        # Build state snapshot
        with coins_lock:
            coins_snapshot = [dict(c) for c in coins]

        players_snapshot = []
        for conn, p in player_items:
            players_snapshot.append(
                {
                    "id": p["id"],
                    "x": p["x"],
                    "y": p["y"],
                    "score": p["score"],
                }
            )

        state_msg = {
            "type": "state",
            "players": players_snapshot,
            "coins": coins_snapshot,
        }

        # Broadcast state to all players
        for conn, p in player_items:
            send_message(conn, state_msg)

        # Maintain tick rate
        elapsed = time.time() - start_time
        sleep_time = DT - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)


def start_server():
    print(f"[SERVER] Starting on {HOST}:{PORT}")
    game_thread = threading.Thread(target=game_loop, daemon=True)
    game_thread.start()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, PORT))
        s.listen()
        print("[SERVER] Waiting for connections ...")

        while True:
            conn, addr = s.accept()
            client_thread = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            client_thread.start()


if __name__ == "__main__":
    start_server()
