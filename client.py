import socket
import json
import pygame

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8765  # or 8765 if you didn't change it

MAP_WIDTH = 800
MAP_HEIGHT = 600

# --- Global state ---

world_state = {
    "coins": [],
}

my_id = None

# Interpolation state: per-player
# player_id -> {"x_prev":..., "y_prev":..., "x":..., "y":..., "t":..., "score":...}
entity_state = {}
INTERP_DURATION = 0.1  # seconds over which we blend positions


def recv_messages(sock, buffer):
    """
    Non-blocking receive from server.
    Returns (new_buffer, list_of_complete_json_messages)
    """
    messages = []

    try:
        data = sock.recv(4096)
        if not data:
            # Connection closed from server side.
            return buffer, messages
        buffer += data.decode("utf-8")
    except BlockingIOError:
        # No data available now (normal for non-blocking socket)
        return buffer, messages
    except ConnectionResetError:
        # Server forcibly closed.
        return buffer, messages
    except OSError:
        # Some other socket error, ignore for now
        return buffer, messages

    # Split by newline (each line is a JSON message)
    while True:
        if "\n" not in buffer:
            break
        line, buffer = buffer.split("\n", 1)
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
            messages.append(msg)
        except json.JSONDecodeError:
            # ignore malformed
            continue

    return buffer, messages


def send_input(sock, keys):
    msg = {
        "type": "input",
        "keys": keys,
    }
    data = json.dumps(msg) + "\n"
    try:
        sock.sendall(data.encode("utf-8"))
    except (BlockingIOError, BrokenPipeError, ConnectionResetError, OSError):
        # If we can't send this frame, just skip. Next frame will try again.
        pass


def update_entities_from_server(players_list):
    """
    Called whenever we get a new 'state' from server.
    Updates interpolation targets for each player.
    """
    global entity_state

    seen_ids = set()

    for p in players_list:
        pid = p["id"]
        x = float(p["x"])
        y = float(p["y"])
        score = p["score"]
        seen_ids.add(pid)

        if pid not in entity_state:
            # First time we see this player: no interpolation yet, just set both prev and current.
            entity_state[pid] = {
                "x_prev": x,
                "y_prev": y,
                "x": x,
                "y": y,
                "t": 0.0,
                "score": score,
            }
        else:
            ent = entity_state[pid]
            # Shift current to prev, and set new target
            ent["x_prev"] = ent["x"]
            ent["y_prev"] = ent["y"]
            ent["x"] = x
            ent["y"] = y
            ent["t"] = 0.0  # restart interpolation timer
            ent["score"] = score

    # Remove players that disappeared (disconnected)
    to_delete = [pid for pid in entity_state.keys() if pid not in seen_ids]
    for pid in to_delete:
        del entity_state[pid]


def main():
    global my_id, world_state, entity_state

    # ----- Connect to server -----
    print(f"[CLIENT] Connecting to {SERVER_HOST}:{SERVER_PORT} ...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((SERVER_HOST, SERVER_PORT))
    # Non-blocking socket: all recv calls must handle BlockingIOError
    sock.setblocking(False)
    print("[CLIENT] Connected to server.")

    # Send join message
    join_msg = {"type": "join", "name": "Player"}
    sock.sendall((json.dumps(join_msg) + "\n").encode("utf-8"))
    print("[CLIENT] Sent join message")

    # ----- Init pygame -----
    pygame.init()
    screen = pygame.display.set_mode((MAP_WIDTH, MAP_HEIGHT))
    pygame.display.set_caption("Coin Collector (Client)")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(None, 24)

    running = True
    recv_buffer = ""

    # For smarter input sending (not every frame)
    last_input_keys = None
    send_timer = 0.0

    while running:
        # Cap FPS to 60
        dt = clock.tick(60) / 1000.0

        # --- Handle window events (keeps window responsive) ---
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        # --- Handle keyboard input ---
        pressed = pygame.key.get_pressed()
        input_keys = {
            "up": pressed[pygame.K_w] or pressed[pygame.K_UP],
            "down": pressed[pygame.K_s] or pressed[pygame.K_DOWN],
            "left": pressed[pygame.K_a] or pressed[pygame.K_LEFT],
            "right": pressed[pygame.K_d] or pressed[pygame.K_RIGHT],
        }

        send_timer += dt
        changed = (input_keys != last_input_keys)
        if changed or send_timer >= 0.1:  # send at most 10x/sec, or on change
            send_input(sock, input_keys)
            last_input_keys = dict(input_keys)
            send_timer = 0.0

        # --- Receive & process server messages (non-blocking) ---
        recv_buffer, msgs = recv_messages(sock, recv_buffer)
        for msg in msgs:
            mtype = msg.get("type")
            if mtype == "welcome":
                my_id = msg.get("id")
                print(f"[CLIENT] Assigned player ID: {my_id}")
            elif mtype == "state":
                # Update coins
                world_state["coins"] = msg.get("coins", [])
                # Update interpolation state for players
                players_list = msg.get("players", [])
                update_entities_from_server(players_list)

        # --- Advance interpolation timers ---
        for ent in entity_state.values():
            ent["t"] += dt

        # --- Draw ---
        screen.fill((30, 30, 30))

        coins = world_state["coins"]

        # Draw coins
        for c in coins:
            x, y = int(c["x"]), int(c["y"])
            pygame.draw.circle(screen, (255, 215, 0), (x, y), 10)

        # Draw players
        my_score = 0
        for pid, ent in entity_state.items():
            # For remote players: interpolate between prev and current
            if pid != my_id:
            # Interpolation for remote players
                alpha = min(ent["t"] / INTERP_DURATION, 1.0)
                x_draw = ent["x_prev"] + (ent["x"] - ent["x_prev"]) * alpha
                y_draw = ent["y_prev"] + (ent["y"] - ent["y_prev"]) * alpha
            else:
                # Smooth correction for local player
                # Instead of snapping, blend toward authoritative position
                correct_speed = 0.15  # lower = smoother, higher = snappier
                x_draw = ent.get("x_draw", ent["x"])
                y_draw = ent.get("y_draw", ent["y"])

                # blend current visual pos toward authoritative pos
                x_draw += (ent["x"] - x_draw) * correct_speed
                y_draw += (ent["y"] - y_draw) * correct_speed

                # save back into entity state for next frame
                ent["x_draw"] = x_draw
                ent["y_draw"] = y_draw

                my_score = ent["score"]

            if pid == my_id:
                color = (0, 255, 0)  # self
            else:
                color = (0, 128, 255)  # others

            pygame.draw.rect(
                screen,
                color,
                pygame.Rect(int(x_draw) - 15, int(y_draw) - 15, 30, 30),
            )

        # Score text
        score_text = font.render(f"Your ID: {my_id}  Score: {my_score}", True, (255, 255, 255))
        screen.blit(score_text, (10, 10))

        pygame.display.flip()

    # Cleanup
    sock.close()
    pygame.quit()


if __name__ == "__main__":
    main()
