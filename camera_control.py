import socket
import time
import threading
from pynput import keyboard

# Налаштування мережі
CAMERA_IP = "192.168.2.119"
CAMERA_PORT = 2000

# ==========================================
# 1. КОМАНДИ РУХУ ТА ЗУМУ
# ==========================================
MOVE_UP_HEX = "eb901455aadc11300d000005dc0000049c00000000006d17"
MOVE_DOWN_HEX = "eb901455aadc11300d000005dc000006e000000000001303"
MOVE_LEFT_HEX = "eb901455aadc11300d00000550000005dc0000000000a0ff"
MOVE_RIGHT_HEX = "eb901455aadc11300d00000668000005dc00000000009b13"
STOP_HEX = "eb901455aadc11300100000000000000000000000000203d"

ZOOM_IN_HEX = "eb901455aadc11300f0000000000000000025800000074f9"
ZOOM_OUT_HEX = "eb901455aadc11300f000000000000000002180000003479"
ZOOM_STOP_HEX = "eb901455aadc11300f000000000000000000400000006ed9"

HOME_HEX = "eb901455aadc11300400003ffc000000000000000000e641"
PITCH_DOWN_90_HEX = "eb901455aadc113012000000000000000000000000003361"

# ==========================================
# 2. МАТРИЦЯ СТАНІВ ЕКРАНА (Сенсор + PIP + Палітра)
# ==========================================
# Коли ОПТИКА головна, а PIP вимкнений (колір не має значення)
VIS_PIP_OFF = "eb901455aadc11300f0000e0020000000003810000004edf"

# Коли ОПТИКА головна, а PIP увімкнений (колір міняє тепловізор у віконці)
VIS_PIP_ON_PALETTES = [
    "eb901455aadc11300f0000e0020000000003830000004cdf",  # White Hot
    "eb901455aadc11300f0000e0020000000003c30000000cdf",  # Black Hot
    "eb901455aadc11300f0000e0020000000004830000004bdf"  # Iron Red
]

# Коли ТЕПЛОВІЗОР головний, а PIP ВИМКНЕНИЙ (твої нові пакети)
IR_PIP_OFF_PALETTES = [
    "eb901455aadc11300f0000e0020000000003820000004ddf",  # White Hot
    "eb901455aadc11300f000000000000000003c1000000ecdb",  # Black Hot (Новий)
    "eb901455aadc11300f00000000000000000481000000ab5b"  # Iron Red (Новий)
]

# Коли ТЕПЛОВІЗОР головний, а PIP УВІМКНЕНИЙ (віконце оптики)
IR_PIP_ON_PALETTES = [
    "eb901455aadc11300f0000e0020000000003840000004bdf",  # White Hot
    "eb901455aadc11300f0000e0020000000003c40000000bdf",  # Black Hot
    "eb901455aadc11300f0000e0020000000004840000004ce1"  # Iron Red
]

PALETTE_NAMES = ["White Hot", "Black Hot", "Iron Red"]

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


def apply_display_state():
    """Розумний менеджер: підбирає 1 правильний Hex на основі 3 параметрів"""
    global camera_socket
    if not camera_socket: return

    cmd_hex = ""
    if not is_thermal:
        if not is_pip_on:
            cmd_hex = VIS_PIP_OFF
        else:
            cmd_hex = VIS_PIP_ON_PALETTES[palette_idx]
    else:
        if not is_pip_on:
            cmd_hex = IR_PIP_OFF_PALETTES[palette_idx]
        else:
            cmd_hex = IR_PIP_ON_PALETTES[palette_idx]

    try:
        camera_socket.sendall(bytes.fromhex(cmd_hex))
    except:
        pass


def parse_telemetry(data_bytes):
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


def on_press(key):
    global current_key, camera_socket, is_thermal, is_pip_on, palette_idx
    if camera_socket is None or key == current_key: return

    try:
        # Рух
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

        # Інші кнопки
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

            # --- ЛОГІКА ЕКРАНА (Тепер просто змінюємо статус і викликаємо менеджер) ---
            elif char == 't':
                is_thermal = not is_thermal
                sensor_name = "ТЕПЛОВІЗОР" if is_thermal else "ОПТИКУ"
                print(f"\n[👁️] Перемикання на {sensor_name}")
                apply_display_state()
                current_key = key

            elif char == 'i':
                is_pip_on = not is_pip_on
                pip_status = "УВІМКНЕНО" if is_pip_on else "ВИМКНЕНО"
                print(f"\n[🔲] Режим PIP: {pip_status}")
                apply_display_state()
                current_key = key

            elif char == 'p':
                palette_idx = (palette_idx + 1) % 3
                print(f"\n[🎨] Палітра тепловізора: {PALETTE_NAMES[palette_idx]}")
                apply_display_state()
                current_key = key

    except:
        pass


def on_release(key):
    global current_key, camera_socket
    if camera_socket is None: return

    if key in [keyboard.Key.up, keyboard.Key.down, keyboard.Key.left, keyboard.Key.right]:
        try:
            camera_socket.sendall(bytes.fromhex(STOP_HEX))
        except:
            pass
        current_key = None

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

            # Синхронізуємо початковий стан камери (Оптика, без PIP)
            apply_display_state()

            print("[+] Ініціалізація успішна!")
            print("[*] РУХ: Стрілки | ЗУМ: W / S | HOME: H | НАДИР: N")
            print("[*] ТЕПЛОВІЗОР: T | ПАЛІТРИ: P | PIP (Віконце): I")
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