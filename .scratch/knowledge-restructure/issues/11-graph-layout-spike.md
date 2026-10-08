# 11: 图谱布局库 spike（dagre vs elk）

**What to build:** 用真实形状的样例图谱（百级节点、四种关系、含跨枝边）给 dagre 与 elk 各出
一版树布局 demo，一锤定音回答「选谁」：布局质量（交叉数/均衡度）、包体体积、React 19 兼容、
维护活跃度。这是回答设计问题的一次性探针，**代码不入产品**。

**Blocked by:** None (can start immediately)

**Status:** done

- [ ] 两个 demo 可运行，用同一样例数据对比（样例形状贴近真实：树骨架 + 跨枝的
  前置依赖/推导/相关边）
- [ ] 对比结论（选谁 + 为什么 + 包体/兼容数据）写进本票 `## 交付记录`
- [ ] 若两家都不达标，给出替代建议（如自写简单紧凑树布局）供 12 票裁决
- [ ] 过程稿不入库：demo 与草稿放仓库外或进 `.git/info/exclude`（仓库工单纪律第 6 条）

【Ownership】
- 可改：仓库外的 spike 目录/脚本
- 禁区：`frontend/src/`（产品代码一行不动）；后端任何文件

【约束】12 票将直接采信本票结论，不再重新调研——spike 的输出是「决定 + 依据」，
不是半成品画布。

## 交付记录(协调者代 spike lane S11 誊入,2026-10-08)

按纪律 spike 不碰仓库任何文件(含本票),结论由协调者从 worker 终报誊入。全程产物在
`/tmp/edumind-spike-11/`(VERDICT.md、双 demo、compare.mjs、metrics.mjs、10 张 SVG 预览、
final-table.txt 34 行全量数据),仓库 `git status` 零写入。

### 裁决(12 票直接采信):选 **elkjs(ELK Layered)**

- 仅喂「父子包含」边、`elk.direction='RIGHT'`;**叠加边(其余三种关系)绝不参与布局**——
  实测全喂引擎两家都凭空多 ~500 处树×树交叉、画布膨胀 2–4×。
- **布局质量**(程序化实测,同一样例 276 节点/406 边/四种关系/含跨枝边,确定性种子 20261008,
  各取 5 次中位):下钻子图(~66 节点,生产主形态)交叉数 elk **513** vs dagre 666(−23%);
  全图展开 elk **2864×3286、宽高比 0.87** vs dagre 680×11718(宽高比 0.06,竖条灾难);
  dagre 补 ~40 行手工逐分量装箱可追平画布但交叉数仍 3038 vs 2336,且为长期维护负担。
- **TB 方向两家均不可用**(宽高比 19–91),思维导图定 LR。
- **包体**:dagre 16.8KB gz vs elkjs 440KB gz(26×),但图谱区走 lazy.ts 懒加载不进首屏,
  且 12 票同票移除 mermaid(同量级),图谱区总重基本持平;elkjs 另有 worker 异步布局不阻塞主线程。
- **React 19**:两家框架无关无 peer 限制;@xyflow/react 12.12.0 peer react>=17 覆盖 19.2.8;
  elk 异步需布局序号防重入(mermaid 的 ELK 布局同款成熟模式)。
- **维护**:均活跃——dagrejs/dagre 5818★(push 2026-08-08,须用 @dagrejs/dagre 而非停更旧包);
  kieler/elkjs 2804★(push 2026-10-06)。
- **落地配置**(完整版在 VERDICT.md):`elk.algorithm='layered'`、`elk.direction='RIGHT'`、
  nodeNode=18/betweenLayers=64/edgeNode=10、`import ELK from 'elkjs/lib/elk.bundled.js'`;
  备用旋钮 `mrtree`(再省 23% 画布、层内严格对齐,交叉数回到 dagre 水平),教师视检嫌松可切换。
- **替代方案备案**:两家均达标,无需自写布局;极端 CSP 禁 worker 时降级 dagre+手工装箱。

### 验证

- 双 demo 可运行:`node demo-dagre.mjs` / `node demo-elk.mjs` / `node compare.mjs` 从清空 out/ 重跑通过。
- ELK 分层行为经按树深坐标分布核查,确认连通分量独立布局+装箱是真实能力差异而非调参伪象;
  渲染器负坐标裁剪 bug 已修复并复验。

### 遗留/注意

- 交叉数为「中心连线直线」同口径近似,真实 React Flow 平滑路由不改节点坐标,不影响选型,但绝对数值≠渲染视觉。
- elkjs 440KB gz 的成立前提是「图谱区懒加载 + mermaid 同票移除」,若 12 票改动该前提需回看。
- spike 产物在 /tmp(易失);VERDICT.md 结论已完整誊入本票,产物灭失不影响决策依据。

## 协调者复核(2026-10-08, wave-1 集成)

- 本票为仓库外技术探针,验收物=「决定+依据」与可运行 demo,均已交付并誊入。
- 四维对比数据齐备、程序化度量口径诚实(近似处已声明)、落地配置可直接实施;12 票采信成立。
- **Status: done(独立复验通过)**
