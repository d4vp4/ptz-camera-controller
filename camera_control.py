import socket
import time
import threading
from pynput import keyboard

# Налаштування мережі
CAMERA_IP = "192.168.2.119"
CAMERA_PORT = 2000

# ==========================================
# 1. СЮДИ ВСТАВ ЗНАЙДЕНІ ПАКЕТИ РУХУ
# ==========================================
MOVE_UP_HEX = "eb901455aadc11300d000005dc0000049c00000000006d17"  # Встав сюди Hex для руху ВГОРУ
MOVE_DOWN_HEX = "eb901455aadc11300d000005dc000006e000000000001303"  # Встав сюди Hex для руху ВНИЗ
MOVE_LEFT_HEX = "eb901455aadc11300d00000550000005dc0000000000a0ff"  # Встав сюди Hex для руху ВЛІВО
MOVE_RIGHT_HEX = "eb901455aadc11300d00000668000005dc00000000009b13"  # Встав сюди Hex для руху ВПРАВО
STOP_HEX = "eb901455aadc11300100000000000000000000000000203d"  # Встав сюди Hex для ЗУПИНКИ

STARTUP_PACKETS = [
    "eb901055aadc0d01e4000000000000000000e8b5",
    "eb90063e2a002a000092"
]
STATUS_REQUEST_HEX = "eb900755aadc0414110105"

# Глобальна змінна для сокета, щоб клавіатура могла в нього писати
camera_socket = None
# Запобіжник, щоб не спамити команду, якщо клавіша затиснута
current_key = None


def parse_telemetry(data_bytes):
    """Декодер телеметрії (твій вчорашній код)"""
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
            # Використовуємо \r щоб рядок оновлювався на одному місці, а не спамив униз
            print(f"\r[{status_text}] Yaw: {yaw_deg:>6.2f}° | Pitch: {pitch_deg:>6.2f}° | Зум: {zoom_val:>4}x", end="")

        except:
            pass


# ==========================================
# 2. СИСТЕМА КЕРУВАННЯ КЛАВІАТУРОЮ
# ==========================================
def on_press(key):
    global current_key, camera_socket
    if camera_socket is None: return

    # Якщо ми вже тримаємо цю кнопку - ігноруємо (щоб не спамити мережу)
    if key == current_key: return

    try:
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
    except Exception as e:
        pass


def on_release(key):
    global current_key, camera_socket
    if camera_socket is None: return

    # Коли ВІДПУСКАЄМО стрілку - відправляємо команду СТОП
    if key in [keyboard.Key.up, keyboard.Key.down, keyboard.Key.left, keyboard.Key.right]:
        try:
            camera_socket.sendall(bytes.fromhex(STOP_HEX))
        except:
            pass
        current_key = None

    # Вихід зі скрипта по кнопці Esc
    if key == keyboard.Key.esc:
        print("\n\n[!] Вихід з програми...")
        return False


# ==========================================
# 3. ОСНОВНИЙ ЦИКЛ ЗВ'ЯЗКУ
# ==========================================
def main():
    global camera_socket

    # Запускаємо слухача клавіатури у фоновому потоці
    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        camera_socket = s  # Передаємо сокет глобально, щоб клавіатура могла ним користуватись

        print(f"[*] Підключаємось до {CAMERA_IP}:{CAMERA_PORT}...")
        try:
            s.connect((CAMERA_IP, CAMERA_PORT))
            print("[+] З'єднання встановлено!")

            for hex_packet in STARTUP_PACKETS:
                s.sendall(bytes.fromhex(hex_packet))
                time.sleep(0.1)

            print("[+] Ініціалізація успішна!")
            print("[*] УПРАВЛІННЯ: Стрілки на клавіатурі (Up, Down, Left, Right).")
            print("[*] Вихід: Натисни ESC.\n")
            print("-" * 60)

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