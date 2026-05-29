"""
launcher.exe 빌드 스크립트 (PyArmor + PyInstaller)
"""
import os
import sys
import shutil
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def run(cmd, **kwargs):
    print(f"\n> {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    result = subprocess.run(cmd, **kwargs)
    if result.returncode != 0:
        print(f"[오류] 실패 (exit {result.returncode})")
        sys.exit(1)

def main():
    os.chdir(BASE_DIR)

    # 도구 설치
    print("[1/4] 도구 설치 중...")
    run([sys.executable, "-m", "pip", "install", "pyarmor>=8.0", "pyinstaller", "requests", "-q"])

    # 이전 빌드 정리
    for d in ["_armored", "build"]:
        p = os.path.join(BASE_DIR, d)
        if os.path.exists(p):
            shutil.rmtree(p)
    spec = os.path.join(BASE_DIR, "launcher.spec")
    if os.path.exists(spec):
        os.remove(spec)

    # PyArmor 난독화 (8.x: gen 명령)
    print("\n[2/4] PyArmor 난독화 중...")
    run([sys.executable, "-m", "pyarmor.cli", "gen",
         "--output", "_armored",
         "launcher.py"])

    # PyInstaller 빌드
    print("\n[3/4] PyInstaller 빌드 중...")
    armored_entry = os.path.join(BASE_DIR, "_armored", "launcher.py")

    # pyarmor_runtime 폴더 찾기 (8.x)
    runtime_dirs = [
        d for d in os.listdir(os.path.join(BASE_DIR, "_armored"))
        if d.startswith("pyarmor_runtime")
    ]
    add_data_args = []
    for rd in runtime_dirs:
        src = os.path.join(BASE_DIR, "_armored", rd)
        add_data_args += ["--add-data", f"{src};{rd}"]

    run([sys.executable, "-m", "PyInstaller",
         "--onefile",
         "--noconsole",
         "--name", "launcher",
         "--hidden-import", "requests",
         "--hidden-import", "tkinter",
         "--hidden-import", "tkinter.ttk",
         "--hidden-import", "tkinter.messagebox",
         "--hidden-import", "tkinter.filedialog",
         "--hidden-import", "tkinter.simpledialog",
         "--hidden-import", "uuid",
         *add_data_args,
         armored_entry])

    # 배포 폴더 구성
    print("\n[4/4] 배포 폴더 구성 중...")
    dist_dir = os.path.join(BASE_DIR, "dist", "ent_bot_deploy")
    os.makedirs(dist_dir, exist_ok=True)

    for fname in ["launcher.exe", ]:
        src = os.path.join(BASE_DIR, "dist", fname)
        if os.path.exists(src):
            shutil.copy2(src, dist_dir)

    for fname in ["launcher_config.json", "install_deps.bat"]:
        src = os.path.join(BASE_DIR, fname)
        if os.path.exists(src):
            shutil.copy2(src, dist_dir)

    # 임시 정리
    shutil.rmtree(os.path.join(BASE_DIR, "_armored"), ignore_errors=True)
    shutil.rmtree(os.path.join(BASE_DIR, "build"), ignore_errors=True)

    print(f"\n{'='*45}")
    print(f"  빌드 완료!")
    print(f"  배포 폴더: dist\\ent_bot_deploy\\")
    print(f"")
    print(f"  [다음 단계]")
    print(f"  1. launcher_config.json 에 NAS URL/계정 확인")
    print(f"  2. NAS /update/ 에 licenses.json 업로드")
    print(f"  3. dist\\ent_bot_deploy\\ 를 다른 PC에 복사")
    print(f"{'='*45}")

if __name__ == "__main__":
    main()
    input("\nEnter 키를 누르면 종료...")
