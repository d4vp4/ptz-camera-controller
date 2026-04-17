import socket
import time
import threading
from pynput import keyboard

# Налаштування мережі
CAMERA_IP = "192.168.2.119"
CAMERA_PORT = 2000

# ==========================================
# 1. КОМАНДИ РУХУ (Yaw / Pitch)
# ==========================================
MOVE_UP_HEX = "eb901455aadc11300d000005dc0000049c00000000006d17"
MOVE_DOWN_HEX = "eb901455aadc11300d000005dc000006e000000000001303"
MOVE_LEFT_HEX = "eb901455aadc11300d00000550000005dc0000000000a0ff"
MOVE_RIGHT_HEX = "eb901455aadc11300d00000668000005dc00000000009b13"
STOP_HEX = "eb901455aadc11300100000000000000000000000000203d"

# ==========================================
# 2. КОМАНДИ ЗУМУ
# ==========================================
ZOOM_IN_HEX = "eb901455aadc11300f0000000000000000025800000074f9"
ZOOM_OUT_HEX = "eb901455aadc11300f000000000000000002180000003479"
ZOOM_STOP_HEX = "eb901455aadc11300f000000000000000000400000006ed9"

# ==========================================
# 3. СПЕЦІАЛЬНІ КОМАНДИ (Home / Nadir)
# ==========================================
HOME_HEX = "eb901455aadc11300400003ffc000000000000000000e641"
PITCH_DOWN_90_HEX = "eb901455aadc113012000000000000000000000000003361"

# ==========================================
# 4. ТЕПЛОВІЗОР ТА ПАЛІТРИ
# ==========================================
CAM_VISIBLE_HEX = "eb901455aadc11300f0000e0020000000004830000004bdf"  # ir -> visible1
CAM_THERMAL_HEX = "eb901455aadc11300f0000e0020000000004840000004ce1"  # visible1 -> ir

IR_WHITE_HOT_HEX = "eb901455aadc11300f0000e0020000000003840000004bdf"
IR_BLACK_HOT_HEX = "eb901455aadc11300f0000e0020000000003c40000000bdf"
IR_IRON_RED_HEX = "eb901455aadc11300f0000e0020000000004840000004ce1"

PALETTES = [
    ("White Hot", IR_WHITE_HOT_HEX),
    ("Black Hot", IR_BLACK_HOT_HEX),
    ("Iron Red", IR_IRON_RED_HEX)
]

# ==========================================
# 5. КАРТИНКА В КАРТИНЦІ (PIP)
# ==========================================
VIS_PIP_ON_HEX = "eb901455aadc11300f0000e0020000000003830000004cdf"
VIS_PIP_OFF_HEX = "eb901455aadc11300f0000e0020000000003810000004edf"
IR_PIP_ON_HEX = "eb901455aadc11300f0000e0020000000003840000004bdf"
IR_PIP_OFF_HEX = "eb901455aadc11300f0000e0020000000003820000004ddf"

STARTUP_PACKETS = [
    "eb901055aadc0d01e4000000000000000000e8b5",
    "eb90063e2a002a000092"
]
STATUS_REQUEST_HEX = "eb900755aadc0414110105"

camera_socket = None
current_key = None

# Глобальні стани камери
is_thermal = False
is_pip_on = False
palette_idx = 0


def parse_telemetry(data_bytes):
    """Декодер телеметрії (читання координат і зуму)"""
    hex_str = data_bytes.hex()
    is_moving = "f7ff" in hex_str
    marker_idx = hex_str.find("f7ff") if is_moving else hex_str.find("b7ff")

    if marker_idx != -1 and len(hex_str) >= marker_idx + 12:
        try:
            yaw_int = int(hex_str[marker_idx + 4: marker_idx + 8], 16)
            if yaw_int > 32767: yaw_int -= 65536
            yaw_deg = yaw_int / 182.0444

            pitch_int = int(hex_str[marker_idx + 8: marker_idx + 12], 16)
            if pitch_int > 32767: pitch_int -= 65536
            pitch_deg = pitch_int / 182.0444

            zoom_val = data_bytes[-2] / 10.0

            status_text = "🔄 Рух " if is_moving else "⏸️ Стоп"
            print(f"\r[{status_text}] Yaw: {yaw_deg:>6.2f}° | Pitch: {pitch_deg:>6.2f}° | Зум: {zoom_val:>4.1f}x",
                  end="")

        except:
            pass


# ==========================================
# СИСТЕМА КЕРУВАННЯ КЛАВІАТУРОЮ
# ==========================================
def on_press(key):
    global current_key, camera_socket, is_thermal, is_pip_on, palette_idx
    if camera_socket is None or key == current_key: return

    try:
        # Стрілочки (Рух)
        if key == keyboard.Key.up:
            camera_socket.sendall(bytes.fromhex(MOVE_UP_HEX))
            current_key = key
        elif key == keyboard.Key.down:
            camera_socket.sendall(bytes.fromhex(MOVE_DOWN_HEX))
            current_key = key
        elif key == keyboard.Key.left:
            camera_socket.sendall(bytes.fromhex(MOVE_LEFT_HEX))
            current_key = key
        elif key == keyboard.Key.right:
            camera_socket.sendall(bytes.fromhex(MOVE_RIGHT_HEX))
            current_key = key

        # Букви
        elif hasattr(key, 'char') and key.char:
            char = key.char.lower()
            if char == 'w':
                camera_socket.sendall(bytes.fromhex(ZOOM_IN_HEX))
                current_key = key
            elif char == 's':
                camera_socket.sendall(bytes.fromhex(ZOOM_OUT_HEX))
                current_key = key
            elif char == 'h':
                print("\n[*] Команда: Повернення в Home...")
                camera_socket.sendall(bytes.fromhex(HOME_HEX))
                current_key = key
            elif char == 'n':
                print("\n[*] Команда: Pitch -90° (Надир)...")
                camera_socket.sendall(bytes.fromhex(PITCH_DOWN_90_HEX))
                current_key = key

            # --- ЛОГІКА ТЕПЛОВІЗОРА ---
            elif char == 't':
                is_thermal = not is_thermal
                is_pip_on = False  # Скидаємо PIP при зміні сенсора
                if is_thermal:
                    print("\n[🔥] Увімкнено ТЕПЛОВІЗОР")
                    camera_socket.sendall(bytes.fromhex(CAM_THERMAL_HEX))
                else:
                    print("\n[📷] Увімкнено ОПТИЧНУ КАМЕРУ")
                    camera_socket.sendall(bytes.fromhex(CAM_VISIBLE_HEX))
                current_key = key

            elif char == 'p':
                if is_thermal:
                    palette_idx = (palette_idx + 1) % len(PALETTES)
                    p_name, p_hex = PALETTES[palette_idx]
                    print(f"\n[🎨] Палітра тепловізора: {p_name}")
                    camera_socket.sendall(bytes.fromhex(p_hex))
                else:
                    print("\n[!] Палітри працюють лише в режимі тепловізора (натисни T)")
                current_key = key

            # --- ЛОГІКА PIP (Картинка в картинці) ---
            elif char == 'i':
                is_pip_on = not is_pip_on
                if not is_thermal:  # Якщо зараз оптика
                    cmd = VIS_PIP_ON_HEX if is_pip_on else VIS_PIP_OFF_HEX
                else:  # Якщо зараз тепловізор
                    cmd = IR_PIP_ON_HEX if is_pip_on else IR_PIP_OFF_HEX

                status_str = "УВІМКНЕНО" if is_pip_on else "ВИМКНЕНО"
                print(f"\n[🔲] Режим PIP (Картинка в картинці): {status_str}")
                camera_socket.sendall(bytes.fromhex(cmd))
                current_key = key

    except:
        pass


def on_release(key):
    global current_key, camera_socket
    if camera_socket is None: return

    # Відпускання стрілок
    if key in [keyboard.Key.up, keyboard.Key.down, keyboard.Key.left, keyboard.Key.right]:
        try:
            camera_socket.sendall(bytes.fromhex(STOP_HEX))
        except:
            pass
        current_key = None

    # Відпускання зуму
    elif hasattr(key, 'char') and key.char:
        char = key.char.lower()
        if char in ['w', 's']:
            try:
                camera_socket.sendall(bytes.fromhex(ZOOM_STOP_HEX))
            except:
                pass
            current_key = None

    if key == keyboard.Key.esc:
        print("\n\n[!] Вихід з програми...")
        return False


# ==========================================
# ОСНОВНИЙ ЦИКЛ ЗВ'ЯЗКУ
# ==========================================
def main():
    global camera_socket

    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        camera_socket = s

        print(f"[*] Підключаємось до {CAMERA_IP}:{CAMERA_PORT}...")
        try:
            s.connect((CAMERA_IP, CAMERA_PORT))
            print("[+] З'єднання встановлено!")

            for hex_packet in STARTUP_PACKETS:
                s.sendall(bytes.fromhex(hex_packet))
                time.sleep(0.1)

            print("[+] Ініціалізація успішна!")
            print("[*] РУХ: Стрілки | ЗУМ: W / S | HOME: H | НАДИР: N")
            print("[*] ТЕПЛОВІЗОР: T (Увімк/Вимк) | ПАЛІТРИ: P")
            print("[*] PIP (Віконце): I")
            print("[*] ВИХІД: ESC\n")
            print("-" * 65)

            last_poll_time = time.time()

            while True:
                current_time = time.time()
                if current_time - last_poll_time >= 2.0:
                    s.sendall(bytes.fromhex(STATUS_REQUEST_HEX))
                    last_poll_time = current_time

                try:
                    data = s.recv(1024)
                    if not data: break
                    parse_telemetry(data)
                except socket.timeout:
                    continue

        except Exception as e:
            print(f"\n[-] Помилка: {e}")


if __name__ == "__main__":
    main()