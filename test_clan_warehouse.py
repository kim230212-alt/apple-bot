"""혈맹 창고 루틴 단독 테스트"""
import time
from ent_bot_config import BotConfig
from ent_bot_engine import BotEngine

CONFIG_PATH = "ent_config.json"

config = BotConfig(CONFIG_PATH)
config.use_clan_warehouse = True  # 강제 활성화

print("=== 혈맹 창고 루틴 테스트 ===")
print(f"  두루마리 클릭: {config.clan_warehouse_scroll_click}")
print(f"  NPC 클릭:     {config.clan_warehouse_npc_click}")
print(f"  맡기기 클릭:  {config.clan_warehouse_deposit_click}")
print(f"  OK 클릭:      {config.clan_warehouse_ok_click}")
print(f"  복귀 클릭:    {config.scroll_click}")
print()
print("5초 후 시작합니다... 게임 창을 준비하세요!")
print("(Ctrl+C로 취소)")

try:
    for i in range(5, 0, -1):
        print(f"  {i}...")
        time.sleep(1)
except KeyboardInterrupt:
    print("\n취소됨")
    exit()

engine = BotEngine(config, log_callback=lambda msg: print(msg))
engine.initialize()

print("\n>>> 혈맹 창고 루틴 실행!")
engine._run_clan_warehouse()
print("\n>>> 테스트 완료!")
