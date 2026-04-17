"""2페이지 버튼 클릭 테스트 — 서버 리스트 화면에서 실행"""
import time
import cv2
import win32gui
import numpy as np

WINDOW_NAME = "Lineage Classic"
TMPL_DIR = "templates/login"

def find_window(name):
    found = None
    def cb(hwnd, _):
        nonlocal found
        if win32gui.IsWindowVisible(hwnd) and name in win32gui.GetWindowText(hwnd):
            found = hwnd
            return False
        return True
    try:
        win32gui.EnumWindows(cb, None)
    except:
        pass
    return found

def grab_frame(hwnd):
    import win32ui, win32con
    client = win32gui.GetClientRect(hwnd)
    w = client[2] - client[0]
    h = client[3] - client[1]
    if w <= 0 or h <= 0:
        return None, w, h
    pt = win32gui.ClientToScreen(hwnd, (0, 0))
    wr = win32gui.GetWindowRect(hwnd)
    cx = pt[0] - wr[0]
    cy = pt[1] - wr[1]
    wDC = win32gui.GetWindowDC(hwnd)
    dcObj = win32ui.CreateDCFromHandle(wDC)
    cDC = dcObj.CreateCompatibleDC()
    bmp = win32ui.CreateBitmap()
    bmp.CreateCompatibleBitmap(dcObj, w, h)
    cDC.SelectObject(bmp)
    cDC.BitBlt((0, 0), (w, h), dcObj, (cx, cy), win32con.SRCCOPY)
    arr = bmp.GetBitmapBits(True)
    img = np.frombuffer(arr, dtype="uint8").reshape(h, w, 4)
    cDC.DeleteDC()
    dcObj.DeleteDC()
    win32gui.ReleaseDC(hwnd, wDC)
    win32gui.DeleteObject(bmp.GetHandle())
    return np.ascontiguousarray(img[..., :3]), w, h

hwnd = find_window(WINDOW_NAME)
if not hwnd:
    print("게임 창 없음")
    exit()

# 클라이언트 영역 크기
cr = win32gui.GetClientRect(hwnd)
cw, ch = cr[2]-cr[0], cr[3]-cr[1]
pt = win32gui.ClientToScreen(hwnd, (0, 0))
print(f"GetClientRect: {cw}x{ch}")
print(f"ClientToScreen(0,0): ({pt[0]},{pt[1]})")

# grab_frame 크기
frame, gw, gh = grab_frame(hwnd)
print(f"grab_frame 크기: {gw}x{gh}")

# dxcam 캡처 크기
from capture_window import WindowCapture
wc = WindowCapture(WINDOW_NAME)
time.sleep(0.5)
dxf = wc.get_screenshot()
print(f"dxcam 캡처 크기: {dxf.shape[1]}x{dxf.shape[0]}")

# 템플릿 매칭
tmpl = cv2.imread(f"{TMPL_DIR}/page2_btn.png")
if tmpl is not None and frame is not None:
    result = cv2.matchTemplate(frame, tmpl, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    th, tw = tmpl.shape[:2]
    cx = max_loc[0] + tw // 2
    cy = max_loc[1] + th // 2
    print(f"\ngrab_frame 템플릿 매칭: score={max_val:.3f} pos=({cx},{cy})")

    # dxcam에서도 매칭
    result2 = cv2.matchTemplate(dxf, tmpl, cv2.TM_CCOEFF_NORMED)
    _, max_val2, _, max_loc2 = cv2.minMaxLoc(result2)
    cx2 = max_loc2[0] + tw // 2
    cy2 = max_loc2[1] + th // 2
    print(f"dxcam 템플릿 매칭:      score={max_val2:.3f} pos=({cx2},{cy2})")

    if abs(cx-cx2) > 3 or abs(cy-cy2) > 3:
        print(f"\n⚠ 좌표 차이 발견! grab_frame({cx},{cy}) vs dxcam({cx2},{cy2})")
        print(f"  차이: dx={cx2-cx}, dy={cy2-cy}")
    else:
        print(f"\n✓ 좌표 일치")
