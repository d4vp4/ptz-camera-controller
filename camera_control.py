import socket
import time
import threading
from pynput import keyboard
import cv2
import os


os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;udp|fflags;nobuffer|flags;low_delay"


# ==========================================
# НАЛАШТУВАННЯ МЕРЕЖІ
# ==========================================
CAMERA_IP = "192.168.2.119"
CAMERA_PORT = 2000
RTSP_URL = "rtsp://192.168.2.119:554"


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
FAST_ZOOM_OUT_HEX = "eb901455aadc11300f000000000000000002380000001479"


HOME_HEX = "eb901455aadc11300400003ffc000000000000000000e641"
PITCH_DOWN_90_HEX = "eb901455aadc113012000000000000000000000000003361"


# ==========================================
# 2. МАТРИЦЯ СТАНІВ ЕКРАНА (Сенсори та Палітри)
# ==========================================
VIS_PIP_OFF = "eb901455aadc11300f0000e0020000000003810000004edf"
VIS_PIP_ON_PALETTES = [
   "eb901455aadc11300f0000e0020000000003830000004cdf",  # White Hot
   "eb901455aadc11300f0000e0020000000003c30000000cdf",  # Black Hot
   "eb901455aadc11300f0000e0020000000004830000004bdf"  # Iron Red
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


# ==========================================
# ГЛОБАЛЬНІ ЗМІННІ
# ==========================================
camera_socket = None
current_key = None
is_thermal = False
is_pip_on = False
palette_idx = 0
is_running = True




# ==========================================
# КЛАС ДЛЯ "ЖИВОГО" ВІДЕО (Без фрізів)
# ==========================================
class LiveStream:
   def __init__(self, src):
       self.stream = cv2.VideoCapture(src)
       self.stream.set(cv2.CAP_PROP_BUFFERSIZE, 1)
       self.ret, self.frame = self.stream.read()
       self.stopped = False


   def start(self):
       threading.Thread(target=self.update, daemon=True).start()
       return self


   def update(self):
       while not self.stopped:
           if not self.stream.isOpened():
               break
           self.ret, self.frame = self.stream.read()


   def read(self):
       return self.ret, self.frame


   def stop(self):
       self.stopped = True
       self.stream.release()




# ==========================================
# ФУНКЦІЇ КЕРУВАННЯ ТА ТЕЛЕМЕТРІЇ
# ==========================================
def reset_home_and_zoom():
   """Фоновий макрос: повертає камеру в центр і повністю скидає зум"""
   global camera_socket
   if not camera_socket: return
   try:
       camera_socket.sendall(bytes.fromhex(HOME_HEX))
       time.sleep(0.1)
       camera_socket.sendall(bytes.fromhex(FAST_ZOOM_OUT_HEX))
       time.sleep(4.5)  # Час на повне складання лінзи
       camera_socket.sendall(bytes.fromhex(ZOOM_STOP_HEX))
   except:
       pass




def apply_display_state():
   """Менеджер режимів відео: підбирає пакет для тепловізора/оптики/PIP"""
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
   """Декодує пакети і виводить кути та зум"""
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




# ==========================================
# ОБРОБКА КЛАВІАТУРИ
# ==========================================
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
           if char in ['w', 'ц']:
               camera_socket.sendall(bytes.fromhex(ZOOM_IN_HEX))
               current_key = key
           elif char in ['s', 'і', 'ы']:
               camera_socket.sendall(bytes.fromhex(ZOOM_OUT_HEX))
               current_key = key
           elif char in ['h', 'р']:
               print("\n[*] Команда: Повернення в Home та скидання зуму...")
               threading.Thread(target=reset_home_and_zoom, daemon=True).start()
               current_key = key
           elif char in ['n', 'т']:
               print("\n[*] Команда: Pitch -90° (Надир)...")
               camera_socket.sendall(bytes.fromhex(PITCH_DOWN_90_HEX))
               current_key = key


           elif char in ['t', 'е']:
               is_thermal = not is_thermal
               print(f"\n[👁️] Перемикання на {'ТЕПЛОВІЗОР' if is_thermal else 'ОПТИКУ'}")
               apply_display_state()
               current_key = key
           elif char in ['i', 'ш']:
               is_pip_on = not is_pip_on
               print(f"\n[🔲] PIP: {'УВІМКНЕНО' if is_pip_on else 'ВИМКНЕНО'}")
               apply_display_state()
               current_key = key
           elif char in ['p', 'з']:
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
       if char in ['w', 'ц', 's', 'і', 'ы']:
           try:
               camera_socket.sendall(bytes.fromhex(ZOOM_STOP_HEX))
           except:
               pass
           current_key = None


   if key == keyboard.Key.esc:
       print("\n\n[!] Завершення роботи. Закриваємо потоки...")
       is_running = False
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
# ГОЛОВНИЙ ПОТІК (Відео)
# ==========================================
def main():
   global is_running


   print("[*] Запускаємо підключення до камери (TCP)...")
   net_thread = threading.Thread(target=network_loop, daemon=True)
   net_thread.start()


   print("[*] Ініціалізуємо драйвер клавіатури...")
   listener = keyboard.Listener(on_press=on_press, on_release=on_release)
   listener.start()


   print(f"[*] Підключаємось до відеопотоку {RTSP_URL}...")
   live_video = LiveStream(RTSP_URL).start()
   time.sleep(1)
   print("[+] Готово! Відео відкрито. Керуйте камерою (Натисни ESC для виходу)")


   while is_running:
       ret, frame = live_video.read()
       if ret and frame is not None:
           frame_resized = cv2.resize(frame, (1280, 720))
           cv2.imshow("PTZ Camera GCS (Viewpro)", frame_resized)


       key = cv2.waitKey(1) & 0xFF
       if key == 27 or cv2.getWindowProperty("PTZ Camera GCS (Viewpro)", cv2.WND_PROP_VISIBLE) < 1:
           is_running = False
           break


   live_video.stop()
   cv2.destroyAllWindows()
   print("\n[!] Програму успішно завершено.")




if __name__ == "__main__":
   main()


