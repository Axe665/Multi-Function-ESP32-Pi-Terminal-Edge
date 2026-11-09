"""生成 7 天演示数据：python3 -m edge.seed"""
from __future__ import annotations

from . import sim, store


def main() -> None:
    store.init_db()
    stats = sim.generate(7)
    print(f"已写入 {stats['batches']} 个批次，抑制 {stats['suppressed']} 个 k<5 桶，"
          f"覆盖 {stats['days']} 天")


if __name__ == "__main__":
    main()
