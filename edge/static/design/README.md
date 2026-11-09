# 设计选型

`index.html` 是选型页：三个概念并排，都是 **three.js r160 + 泛光后处理**，
数据全部来自 `/api/v1/overview` 与 `/api/v1/devices/{id}/series`。

| 文件 | 概念 | 3D 内容 |
|---|---|---|
| `d.html` | 玻璃核心 | 折射玻璃二十面体 + 内嵌光环 + 三节点轨道 + 粒子流 |
| `e.html` | 数据地形 | 12 万点阵，三条脊 = 三台设备的 24h 序列，相机贴地飞行 |
| `f.html` | 粒子树 | 树干 + 三主枝 + 末梢粒子，GPU 顶点着色器摆动 |

`core.js` 是共用底座：渲染器、相机、UnrealBloom、尺寸自适应、帧循环、
`?still=1` 单帧模式（截图与缩略图用）。

`vendor/three/` 是本地依赖，不联网；`vendor/anime.min.js` 备用。

上一轮的平面版式留在 `a.html` / `b.html` / `c.html`，仅作参考。
