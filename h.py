import ctypes
import threading
import time
from ctypes import wintypes
import keyboard
import pyperclip

DELAY = 0.03
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
INPUT_KEYBOARD = 1
HOTKEY_RELEASE_TIMEOUT = 1.0

# 指针长度适配 32/64 位
ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong

# 必须定义 MOUSEINPUT，保证联合大小和系统一致（MOUSEINPUT 是三个结构里最大的）
class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]

class INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
    ]

class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [
        ("type", wintypes.DWORD),
        ("u", INPUT_UNION),
    ]

# 声明 SendInput 函数
SendInput = ctypes.windll.user32.SendInput
SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
SendInput.restype = wintypes.UINT

typing = False
state_lock = threading.Lock()
stop_event = threading.Event()

def send_key(scan, flags):
    inp = INPUT(
        INPUT_KEYBOARD,
        INPUT_UNION(ki=KEYBDINPUT(0, scan, flags, 0, 0)),
    )
    result = SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
    if result != 1:
        raise ctypes.WinError()

def type_unicode_char(char):
    """发送单个 Unicode 字符，支持 UTF-16 代理对"""
    data = char.encode("utf-16-le", "surrogatepass")
    for i in range(0, len(data), 2):
        code = int.from_bytes(data[i:i + 2], "little")
        send_key(code, KEYEVENTF_UNICODE)
        send_key(code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)

def wait_for_hotkey_release():
    """等待热键修饰键释放，避免干扰输入内容"""
    deadline = time.monotonic() + HOTKEY_RELEASE_TIMEOUT
    while time.monotonic() < deadline:
        if stop_event.is_set():
            return False
        if not keyboard.is_pressed("ctrl") and not keyboard.is_pressed("alt"):
            return True
        time.sleep(0.01)
    print("Ctrl/Alt 未在规定时间内释放，已取消本次输入", flush=True)
    return False

def type_text():
    global typing
    try:
        if not wait_for_hotkey_release():
            return
        text = pyperclip.paste() or ""
        print(f"已读取 {len(text)} 个字符", flush=True)
        for char in text:
            if stop_event.is_set():
                break
            if char == "\r":
                continue
            if char == "\n":
                keyboard.press_and_release("enter")
            elif char == "\t":
                keyboard.press_and_release("tab")
            else:
                type_unicode_char(char)
            time.sleep(DELAY)
    except Exception as e:
        print(f"输入错误: {e!r}", flush=True)
    finally:
        with state_lock:
            typing = False
            stop_event.clear()

def start_typing():
    global typing
    with state_lock:
        if typing:
            return
        stop_event.clear()
        typing = True
        try:
            threading.Thread(target=type_text, daemon=True).start()
        except Exception:
            typing = False
            raise

def stop_typing():
    stop_event.set()

# 注册热键，suppress=True 屏蔽系统原生按键
keyboard.add_hotkey("ctrl+alt+v", start_typing, suppress=True)
keyboard.add_hotkey("f12", stop_typing, suppress=True)

print("脚本运行中：Ctrl+Alt+V 开始输入，F12 停止，Ctrl+C 退出", flush=True)
try:
    keyboard.wait()
except KeyboardInterrupt:
    pass
finally:
    keyboard.unhook_all()
