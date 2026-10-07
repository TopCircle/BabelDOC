# 放置范式原型评估

日期：2026-10-08。脚本：`tools/prototype/placement_paradigm_proto.py`。  
判定函数与实现计划 Task 1 相同。分段只存在于原型里：先按 x 重叠分栏，再按字号和垂直空隙分段。不翻译，不改 `Typesetting`。

书在本机 Gabrielle Moore 目录，不进 git。命令：

```bash
python tools/prototype/placement_paradigm_proto.py
```

15 项期望，退出码 0。

| 用例 | 页 | 期望 | 结果 |
|---|---|---|---|
| Orgasmic Addiction 英文 | 19 | 正文 `rect_reflow`，「taking charge」那一段 `shaped_pocket` | 通过。锥形段 9 行，左缘从 314 收到 482，右缘约 573 |
| 同上 | 23 | 大字引语和右栏分开，都不是 `shaped_pocket` | 通过。引语左缘 54，正文左缘 246 |
| 同上 | 44 | 正文没有 `shaped_pocket` | 通过 |
| 中文单语金样 | 19 | 同样是矩形加锥形 | 通过。锥形 5 行，左缘 324 到 422，右缘约 564 |
| 中文单语金样 | 44 | 正文没有 `shaped_pocket` | 通过。左缘约 102 |
| Vagina Masterclass | 6 | 正文和项目都不是锥形 | 通过。正文左缘 36 |
| Vagina Masterclass | 8 | 侧图使各段左缘下移，但没有一段是 `shaped_pocket` | 通过。各段左缘 238 到 342，全部 `rect_reflow` |
| All Tied Up | 8 | 矩形，左缘约 56 | 通过 |
| Open Her Up | 8 | 悬挂列表不是锥形 | 通过。reason `not_taper` |
| Flirting Fingers | 8 | 矩形 | 通过 |
| G-Spot Ecstasy | 8 | 横开本正文是矩形，不是对页，不是坏编码 | 通过。页面 792×612 |
| The Perfect Trigasm | 6 | 输入门 `spread` | 通过。1224 宽 |
| Boobgasms | 6 | 输入门 `image_only` | 通过 |
| Forbidden Fruit | 6 | 输入门 `encoding` | 通过。字母比例 0.03 |
| Turn Her On Faster | 6 | 输入门 `encoding` | 通过。ASCII 字母多，但元音比例低于 0.20 |

## 门对正式实现的约束

- 锥形按段判定。VM 第 8 页整页左缘在走，每一段自己仍是矩形。Task 3 要让这些矩形在有形状时也不右钉。
- OA 第 19 页照片旁那一段是锥形，保持 `shaped_pocket`，不把已有的右钉方向改掉。
- 引语在原型里没有角色，几何上是稳定窄栏，所以标成 `rect_reflow`。正式实现里 `PULL_QUOTE` 必须是 `keep_current`。
- 元音比例和对页宽度只在原型的输入门里，不进 `select_paradigm`。
- 第 6、9 页的重复词仍是切段问题，这次没有当放置失败。

原型通过。可以按 `docs/plans/2026-10-08-layout-paradigms.md` 的 Task 1 起正式实现。
