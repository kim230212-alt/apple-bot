import cv2
import numpy as np
import win32gui
import win32ui
import win32con
import ctypes
import time
import os
import dxcam

# DPI 인식 설정 (물리 픽셀 기준으로 좌표 일치)
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

class WindowCapture:
    w = 0
    h = 0
    hwnd = None
    cropped_x = 0
    cropped_y = 0
    offset_x = 0
    offset_y = 0

    def __init__(self, window_name=None):
        self.dpi_scale = ctypes.windll.shcore.GetScaleFactorForDevice(0) / 100

        if window_name is None:
            self.hwnd = win32gui.GetDesktopWindow()
        else:
            self.hwnd = self.find_window_by_substring(window_name)
            if not self.hwnd:
                raise Exception(f"'{window_name}' 글자가 포함된 창을 찾을 수 없습니다. 게임이 켜져 있는지 확인해주세요.")

        # 클라이언트 영역의 실제 크기와 화면 절대좌표를 정확하게 계산
        client_rect = win32gui.GetClientRect(self.hwnd)
        self.w = client_rect[2] - client_rect[0]
        self.h = client_rect[3] - client_rect[1]

        # 클라이언트 영역 좌상단의 절대 스크린 좌표
        pt = win32gui.ClientToScreen(self.hwnd, (0, 0))
        self.offset_x = pt[0]
        self.offset_y = pt[1]

        # BitBlt 캡처 시작점 (창 내부에서 클라이언트 영역까지의 오프셋)
        window_rect = win32gui.GetWindowRect(self.hwnd)
        self.cropped_x = pt[0] - window_rect[0]
        self.cropped_y = pt[1] - window_rect[1]

        import win32api
        self._win32api   = win32api
        self._cameras    = {}   # output_idx → dxcam camera
        self._cur_output = None
        self._mon_scale  = 1.0
        self._last_hmon  = None
        self._update_capture_region()
        print(f"  dxcam monitor={self._cur_output}  crop={self._crop}")

    def find_window_by_substring(self, substring):
        """창 제목에 특정 문자열(substring)이 포함된 창의 핸들(hwnd)을 찾습니다."""
        found_hwnd = None
        def callback(hwnd, extra):
            nonlocal found_hwnd
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if substring in title:
                    found_hwnd = hwnd
                    return False  # 찾았으면 EnumWindows 중지 (False를 리턴하면 중지되지만 에러가 발생할 수 있음, 여기서는 멈춤)
            return True
        try:
            win32gui.EnumWindows(callback, None)
        except Exception:
            pass # EnumWindows 콜백에서 False를 반환하면 발생하는 예외 무시
        return found_hwnd

    def _update_capture_region(self):
        """창 위치/모니터를 재확인하고 캡처 좌표 갱신"""
        # 창 클라이언트 영역 재계산
        client_rect = win32gui.GetClientRect(self.hwnd)
        self.w = client_rect[2] - client_rect[0]
        self.h = client_rect[3] - client_rect[1]
        pt = win32gui.ClientToScreen(self.hwnd, (0, 0))
        self.offset_x = pt[0]
        self.offset_y = pt[1]

        # BitBlt용 cropped 좌표 갱신
        window_rect = win32gui.GetWindowRect(self.hwnd)
        self.cropped_x = pt[0] - window_rect[0]
        self.cropped_y = pt[1] - window_rect[1]

        # 현재 창이 있는 모니터 찾기
        import win32api as _wa
        hmon = self._win32api.MonitorFromWindow(self.hwnd, win32con.MONITOR_DEFAULTTONEAREST)

        # 모니터가 바뀌지 않았으면 crop 좌표만 갱신 (dxcam 재탐색 생략)
        mon_info = _wa.GetMonitorInfo(hmon)
        mon_rect = mon_info['Monitor']
        mon_ox   = mon_rect[0]
        mon_oy   = mon_rect[1]
        mon_lw   = mon_rect[2] - mon_rect[0]
        mon_lh   = mon_rect[3] - mon_rect[1]

        # 모니터 내 상대 좌표 (논리 px)
        l = self.offset_x - mon_ox
        t = self.offset_y - mon_oy
        r = l + self.w
        b = t + self.h
        if (r - l) % 2 != 0: r -= 1
        if (b - t) % 2 != 0: b -= 1

        # 모니터가 변경됐을 때만 dxcam output 재탐색
        if hmon != getattr(self, '_last_hmon', None):
            self._last_hmon = hmon

            # dxcam output 탐색: 논리 해상도와 일치하는 것 → scale=1.0 (FHD 100%)
            # 또는 논리*primary_scale과 일치하는 것 → scale=primary (4K 150%)
            dx_idx = 0
            mon_scale = 1.0
            for i in range(8):
                try:
                    if i not in self._cameras:
                        self._cameras[i] = dxcam.create(output_idx=i, output_color="BGR")
                    cam = self._cameras[i]
                    print(f"    dxcam[{i}]: {cam.width}x{cam.height}  logical={mon_lw}x{mon_lh}")
                    if cam.width == mon_lw and cam.height == mon_lh:
                        # 100% DPI 모니터 (물리 = 논리)
                        dx_idx    = i
                        mon_scale = 1.0
                        break
                    elif cam.width == int(mon_lw * self.dpi_scale) and \
                         cam.height == int(mon_lh * self.dpi_scale):
                        # primary DPI 스케일과 일치
                        dx_idx    = i
                        mon_scale = self.dpi_scale
                        break
                except Exception:
                    break

            self._cur_output  = dx_idx
            self._mon_scale   = mon_scale
            print(f"  monitor={dx_idx}  scale={mon_scale:.2f}  logical={mon_lw}x{mon_lh}")

        # 크롭 좌표: 해당 모니터 스케일 기준 물리 픽셀
        s  = self._mon_scale
        lp = int(l * s)
        tp = int(t * s)
        rp = int(r * s)
        bp = int(b * s)
        if (rp - lp) % 2 != 0: rp -= 1
        if (bp - tp) % 2 != 0: bp -= 1
        self._crop = (lp, tp, rp, bp)

    def get_screenshot(self):
        # 창 위치 변경 감지 (매 프레임 win32 API 최소화)
        pt = win32gui.ClientToScreen(self.hwnd, (0, 0))
        if pt != (self.offset_x, self.offset_y):
            self._update_capture_region()  # 창 이동 시에만 갱신
        camera = self._cameras[self._cur_output]

        # 전체 화면 캡처 후 게임 창 영역 직접 슬라이싱
        full = camera.grab()
        if full is not None:
            l, t, r, b = self._crop
            frame = full[t:b, l:r]
            if frame.shape[1] != self.w or frame.shape[0] != self.h:
                frame = cv2.resize(frame, (self.w, self.h))
            return frame
        # fallback: BitBlt

        # fallback: BitBlt
        wDC = win32gui.GetWindowDC(self.hwnd)
        dcObj = win32ui.CreateDCFromHandle(wDC)
        cDC = dcObj.CreateCompatibleDC()
        dataBitMap = win32ui.CreateBitmap()
        dataBitMap.CreateCompatibleBitmap(dcObj, self.w, self.h)
        cDC.SelectObject(dataBitMap)
        cDC.BitBlt((0, 0), (self.w, self.h), dcObj, (self.cropped_x, self.cropped_y), win32con.SRCCOPY)
        signedIntsArray = dataBitMap.GetBitmapBits(True)
        img = np.frombuffer(signedIntsArray, dtype='uint8')
        img.shape = (self.h, self.w, 4)
        cDC.DeleteDC()
        dcObj.DeleteDC()
        win32gui.ReleaseDC(self.hwnd, wDC)
        win32gui.DeleteObject(dataBitMap.GetHandle())
        return np.ascontiguousarray(img[...,:3])

    def get_screen_position(self, pos):
        """
        캡처된 이미지 안에서의 X, Y 좌표(pos)를 실제 모니터 상의 절대 X, Y 좌표로 변환해 줍니다.
        frame은 항상 self.w x self.h (논리 픽셀)로 resize되고,
        offset_x/y도 ClientToScreen 기준 논리 픽셀이므로 단순 덧셈으로 변환합니다.
        """
        return (int(pos[0] + self.offset_x), int(pos[1] + self.offset_y))

if __name__ == '__main__':
    # =========================================================================
    # [설정] 캡처할 창의 이름을 정확히 입력하세요.
    # 리니지 클래식 클라이언트의 창 이름이 "Lineage Classic" 이라면 아래와 같이 설정합니다.
    # =========================================================================
    WINDOW_NAME = "Lineage Classic" # 창 제목이 다르다면 이 부분을 수정하세요!
    
    # 캡처된 이미지가 저장될 폴더 (라벨링을 위해 모아두는 곳)
    SAVE_DIR = "images"
    if not os.path.exists(SAVE_DIR):
        os.makedirs(SAVE_DIR)
        
    try:
        wincap = WindowCapture(WINDOW_NAME)
        print(f"✅ '{WINDOW_NAME}' 창을 성공적으로 인식했습니다.")
    except Exception as e:
        print(f"❌ 오류: {e}")
        print("💡 게임 클라이언트 창의 정확한 이름을 WINDOW_NAME 변수에 입력해 주세요.")
        print("💡 창 이름을 모를 경우 WINDOW_NAME = None 으로 설정하면 전체 화면을 캡처합니다.")
        exit()

    print("\n--- 📷 캡처 도구 실행 중 ---")
    print("▶ 캡처 도구 창(Computer Vision)이 활성화된 상태에서 키를 누르세요.")
    print("▶ 수동 저장: 's' 키를 누르면 사진이 1장씩 저장됩니다.")
    print("▶ 자동 저장: 'a' 키를 누르면 1초에 1장씩 자동으로 저장됩니다. (다시 'a'를 누르면 중지)")
    print("▶ 프로그램 종료: 'q' 키를 누르세요.\n")
    
    auto_capture = False
    last_capture_time = time.time()
    capture_count = 0

    while True:
        # 1. 화면 캡처 실행
        screenshot = wincap.get_screenshot()
        
        # 2. 사용자에게 현재 캡처되고 있는 화면을 보여줍니다. (디버깅 창)
        cv2.imshow('Computer Vision', screenshot)
        
        key = cv2.waitKey(1)
        
        # 'q' 키: 종료
        if key == ord('q'):
            print("캡처 도구를 종료합니다.")
            cv2.destroyAllWindows()
            break
            
        # 's' 키: 수동 캡처
        elif key == ord('s'):
            filename = os.path.join(SAVE_DIR, f'capture_{capture_count}_{int(time.time())}.jpg')
            cv2.imwrite(filename, screenshot)
            print(f"📸 수동 캡처 완료 ({capture_count}번째): {filename}")
            capture_count += 1
            
        # 'a' 키: 자동 캡처 토글
        elif key == ord('a'):
            auto_capture = not auto_capture
            if auto_capture:
                print("🔄 [자동 캡처 모드] 시작 (1초마다 저장)")
            else:
                print("⏸️ [자동 캡처 모드] 중지됨")
                
        # 자동 캡처 로직 (1초마다 1장)
        if auto_capture and (time.time() - last_capture_time) > 1.0:
            filename = os.path.join(SAVE_DIR, f'capture_auto_{capture_count}_{int(time.time())}.jpg')
            cv2.imwrite(filename, screenshot)
            print(f"📸 자동 캡처 ({capture_count}번째): {filename}")
            capture_count += 1
            last_capture_time = time.time()
