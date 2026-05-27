"""
update.zip + version.json 생성 스크립트
NAS /update/ 폴더에 업로드할 파일을 만든다.
"""
import os
import shutil
import zipfile
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 업데이트에 포함할 app/ 파일 목록
APP_FILES = [
    "ent_bot_gui_dual.py",
    "ent_bot_gui_template.py",
    "ent_bot_engine_template.py",
    "ent_bot_config.py",
    "auto_login.py",
    "capture_window.py",
    "template_scanner.py",
    "input_lock.py",
    "ocr_process.py",
    "keyboard_mouse_check.py",
    "coord_picker.py",
    "run_dual.bat",
    # 설정 파일 (첫 실행용 기본값 — 이미 있으면 런처가 스킵)
    "ent_config.json",
    "ent_config2.json",
    "auto_login_config.json",
]

def main():
    ver = input("버전 입력 (예: 1.0.0): ").strip()
    if not ver:
        print("버전을 입력하세요.")
        return

    pkg_dir = os.path.join(BASE_DIR, "_update_pkg")
    app_dst = os.path.join(pkg_dir, "app")
    tmpl_dst = os.path.join(pkg_dir, "templates")
    inter_dst = os.path.join(pkg_dir, "Interception")

    # 임시 폴더 초기화
    if os.path.exists(pkg_dir):
        shutil.rmtree(pkg_dir)
    os.makedirs(app_dst)

    # app 파일 복사
    print("\n[1/3] 소스 파일 복사 중...")
    missing = []
    for fname in APP_FILES:
        src = os.path.join(BASE_DIR, fname)
        dst = os.path.join(app_dst, fname)
        if os.path.exists(src):
            shutil.copy2(src, dst)
            print(f"  + {fname}")
        else:
            missing.append(fname)
            print(f"  ! 없음: {fname}")

    # templates 복사
    print("\n[2/3] templates 복사 중...")
    tmpl_src = os.path.join(BASE_DIR, "templates")
    if os.path.exists(tmpl_src):
        shutil.copytree(tmpl_src, tmpl_dst)
        print(f"  + templates/ ({len(os.listdir(tmpl_src))}개 파일)")
    else:
        print("  ! templates 폴더 없음")

    # Interception 복사
    inter_src = os.path.join(BASE_DIR, "Interception")
    if os.path.exists(inter_src):
        shutil.copytree(inter_src, inter_dst)
        print(f"  + Interception/")

    # zip 생성
    print("\n[3/3] update.zip 생성 중...")
    zip_path = os.path.join(BASE_DIR, "update.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(pkg_dir):
            for file in files:
                abs_path = os.path.join(root, file)
                arc_name = os.path.relpath(abs_path, pkg_dir)
                zf.write(abs_path, arc_name)

    size_kb = os.path.getsize(zip_path) // 1024

    # version.json 생성
    ver_path = os.path.join(BASE_DIR, "version.json")
    with open(ver_path, "w", encoding="utf-8") as f:
        json.dump({"version": ver, "file": "update.zip"}, f, indent=4)

    # 임시 폴더 정리
    shutil.rmtree(pkg_dir)

    print(f"\n{'='*45}")
    print(f"  완료!")
    print(f"  update.zip   ({size_kb} KB)")
    print(f"  version.json (버전: {ver})")
    if missing:
        print(f"\n  [주의] 누락된 파일: {', '.join(missing)}")
    print(f"\n  NAS /update/ 폴더에 두 파일을 업로드하세요.")
    print(f"{'='*45}")

if __name__ == "__main__":
    main()
    input("\nEnter 키를 누르면 종료...")
