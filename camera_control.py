import socket
import time
import threading
from pynput import keyboard
import cv2  # ДОДАНО ДЛЯ ВІДЕО

# Налаштування мережі
CAMERA_IP = "192.168.2.119"
CAMERA_PORT = 2000
RTSP_URL = "rtsp://192.168.2.119:554"  # Знайдене посилання на відео

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
# 2. МАТРИЦЯ СТАНІВ ЕКРАНА
# ==========================================
VIS_PIP_OFF = "eb901455aadc11300f0000e0020000000003810000004edf"

VIS_PIP_ON_PALETTES = [
    "eb901455aadc11300f0000e0020000000003830000004cdf",
    "eb901455aadc11300f0000e0020000000003c30000000cdf",
    "eb901455aadc11300f0000e0020000000004830000004bdf"
]

IR_PIP_OFF_PALETTES = [
    "eb901455aadc11300f0000e0020000000003820000004ddf",
    "eb901455aadc11300f000000000000000003c1000000ecdb",
    "eb901455aadc11300f00000000000000000481000000ab5b"
]

IR_PIP_ON_PALETTES = [
    "eb901455aadc11300f0000e0020000000003840000004bdf",
    "eb901455aadc11300f0000e0020000000003c40000000bdf",
    "eb901455aadc11300f0000e0020000000004840000004ce1"
]

PALETTE_NAMES = ["White Hot", "Black Hot", "Iron Red"]

STARTUP_PACKETS = ["eb901055aadc0d01e4000000000000000000e8b5", "eb90063e2a002a000092"]
STATUS_REQUEST_HEX = "eb900755aadc0414110105"

camera_socket = None
current_key = None

# Глобальні стани
is_thermal = False
is_pip_on = False
palette_idx = 0
is_running = True  # Прапорець для зупинки всіх потоків


def apply_display_state():
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
            print(f"\r[{status_text}] Yaw: {yaw_deg:>6.2f}° | Pitch: {pitch_deg:>6.2f}° | Зум: {zoom_val:>4.1f}x   ",
                  end="")
        except:
            pass


def on_press(key):
    global current_key, camera_socket, is_thermal, is_pip_on, palette_idx
    if camera_socket is None or key == current_key: return

    try:
        if key == keyboard.Key.up:
            camera_socket.sendall(bytes.fromhex(MOVE_UP_HEX)); current_key = key
        elif key == keyboard.Key.down:
            camera_socket.sendall(bytes.fromhex(MOVE_DOWN_HEX)); current_key = key
        elif key == keyboard.Key.left:
            camera_socket.sendall(bytes.fromhex(MOVE_LEFT_HEX)); current_key = key
        elif key == keyboard.Key.right:
            camera_socket.sendall(bytes.fromhex(MOVE_RIGHT_HEX)); current_key = key

        elif hasattr(key, 'char') and key.char:
            char = key.char.lower()
            if char == 'w':
                camera_socket.sendall(bytes.fromhex(ZOOM_IN_HEX)); current_key = key
            elif char == 's':
                camera_socket.sendall(bytes.fromhex(ZOOM_OUT_HEX)); current_key = key
            elif char == 'h':
                print("\n[*] Home..."); camera_socket.sendall(bytes.fromhex(HOME_HEX)); current_key = key
            elif char == 'n':
                print("\n[*] Pitch -90°..."); camera_socket.sendall(bytes.fromhex(PITCH_DOWN_90_HEX)); current_key = key

            elif char == 't':
                is_thermal = not is_thermal
                print(f"\n[👁️] Перемикання на {'ТЕПЛОВІЗОР' if is_thermal else 'ОПТИКУ'}")
                apply_display_state()
                current_key = key
            elif char == 'i':
                is_pip_on = not is_pip_on
                print(f"\n[🔲] PIP: {'УВІМКНЕНО' if is_pip_on else 'ВИМКНЕНО'}")
                apply_display_state()
                current_key = key
            elif char == 'p':
                palette_idx = (palette_idx + 1) % 3
                print(f"\n[🎨] Палітра: {PALETTE_NAMES[palette_idx]}")
                apply_display_state()
                current_key = key
    except:
        pass


def on_release(key):
    global current_key, camera_socket, is_running
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
        is_running = False  # Зупиняємо всі потоки
        return False


# ==========================================
# ФОНОВИЙ ПОТІК (TCP Мережа)
# ==========================================
def network_loop():
    global camera_socket, is_running
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        camera_socket = s
        try:
            s.connect((CAMERA_IP, CAMERA_PORT))
            for pkt in STARTUP_PACKETS:
                s.sendall(bytes.fromhex(pkt))
                time.sleep(0.1)

            apply_display_state()
            last_poll = time.time()

            while is_running:
                curr = time.time()
                if curr - last_poll >= 2.0:
                    s.sendall(bytes.fromhex(STATUS_REQUEST_HEX))
                    last_poll = curr

                try:
                    data = s.recv(1024)
                    if data: parse_telemetry(data)
                except socket.timeout:
                    continue
        except Exception as e:
            print(f"\n[-] Мережева помилка: {e}")


# ==========================================
# ГОЛОВНИЙ ПОТІК (Відео + Запуск)
# ==========================================
def main():
    global is_running

    print("[*] Запускаємо фонові процеси...")
    # 1. Запуск мережі у фоні
    net_thread = threading.Thread(target=network_loop, daemon=True)
    net_thread.start()

    # 2. Запуск клавіатури у фоні
    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()

    print(f"[*] Підключаємось до відеопотоку {RTSP_URL}...")

    # 3. Запуск Відео у головному потоці
    cap = cv2.VideoCapture(RTSP_URL)
    # Зменшуємо буфер, щоб відео менше "відставало" від реального часу
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    if not cap.isOpened():
        print("[-] Не вдалося відкрити RTSP відеопотік! Перевір адресу або чи не зайнята камера.")
    else:
        print("[+] Відеопотік успішно відкрито! (Натисни ESC для виходу)")

    # Головний цикл відображення картинок
    while is_running:
        if cap.isOpened():
            ret, frame = cap.read()
            if ret:
                # Зменшуємо розмір вікна, якщо відео 4K/1080p і не влазить в екран
                frame = cv2.resize(frame, (1280, 720))
                cv2.imshow("PTZ Camera Stream (Viewpro)", frame)
            else:
                pass  # Якщо кадр загубився через Wi-Fi, просто чекаємо наступний

        # Обов'язкова функція OpenCV для оновлення вікна (1 мілісекунда)
        # Також закриває скрипт, якщо натиснути ESC (27) знаходячись у вікні відео
        key = cv2.waitKey(1) & 0xFF
        if key == 27:
            is_running = False
            break

    # Коректно закриваємо відео
    cap.release()
    cv2.destroyAllWindows()
    print("\n[!] Програму завершено.")


if __name__ == "__main__":
    main()