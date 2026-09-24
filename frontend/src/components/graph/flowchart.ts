/**
 * mermaid 扁平主题 + 四种关系的线型：`docs/style/minimalist-flat.md` **第 8 节配方的唯一实现**。
 *
 * 复用入口（票 11 的结构冲突图示也用这里）：
 * - `FLAT_THEME_INIT`：第 8 节的 `%%{init: ...}%%` 指令字符串；
 * - `RELATION_STYLES` / `relationStyle()`：四种关系的线型与颜色（黑与强调色的实线 / 虚线）；
 * - `buildFlowchartSource()`：从「节点 + 关系」数据自行生成 mermaid 源码（画布与图例同源）。
 *
 * 配方逐条照抄第 8 节：`theme: base`（不用默认彩色分类色板）、白底、黑框黑字、自托管字体。
 * **配方之外的四处补充**（都是第 8 节正文写明、但配方本身没有开关的项）：
 * - `look: classic`：关掉 mermaid 新的 neo 观感——它给节点叠投影滤镜与渐变描边，
 *   与第 8 节「禁用…阴影主题」「零阴影 / 零渐变」直接冲突；
 * - `themeCSS` 节点→2px 黑边：base 主题把节点描边写成 1px；
 * - `themeCSS` 图内字体：配方里的 `fontFamily` 会被 mermaid 的指令净化器清空
 *   （值里的 `sans-serif` 带连字符，不在它允许的字符集里），故用 themeCSS 再钉一次；
 * - `themeCSS` 键盘聚焦：节点要能 Tab 得到且聚焦可见（不用浏览器默认蓝圈）；
 * - `sharpenLinkCorners()`：连线转弯处的 5px 倒角还原成直角（详见该函数注释）。
 */

/** 唯一强调色（风格文档第 1 节），与 `bg-[#ff3366]` 是同一个值。 */
export const ACCENT_COLOR = '#ff3366'

/** 四种关系（CONTEXT.md 第 5 节）。 */
export type RelationType = '前置依赖' | '父子包含' | '推导关系' | '相关关联'

export interface RelationStyle {
  readonly relation: RelationType
  /** mermaid 连线语法：实线 / 粗实线 / 虚线。 */
  readonly arrow: string
  /** 线色：黑或唯一强调色。 */
  readonly color: string
  /** 虚线（由 `arrow` 与图例自绘共用同一份语义）。 */
  readonly dashed: boolean
  /** 粗线（「父子包含」是实线里的粗线）。 */
  readonly thick: boolean
}

/** 第 8 节那张关系表：线型与颜色只在这里定义一次。 */
export const RELATION_STYLES: readonly RelationStyle[] = [
  { relation: '前置依赖', arrow: '-->', color: '#000000', dashed: false, thick: false },
  { relation: '父子包含', arrow: '==>', color: '#000000', dashed: false, thick: true },
  { relation: '推导关系', arrow: '-.->', color: '#000000', dashed: true, thick: false },
  { relation: '相关关联', arrow: '-.->', color: ACCENT_COLOR, dashed: true, thick: false },
]

/** 关系名不认识时的兜底线型：中性虚线黑——不把数据藏起来，也不谎报成某一种关系。 */
const UNKNOWN_RELATION: RelationStyle = {
  relation: '推导关系',
  arrow: '-.->',
  color: '#000000',
  dashed: true,
  thick: false,
}

export function relationStyle(relation: string): RelationStyle {
  return RELATION_STYLES.find((style) => style.relation === relation) ?? UNKNOWN_RELATION
}

const FLAT_THEME = {
  theme: 'base',
  /** 关掉 neo 观感：它会引入投影滤镜与渐变描边（见文件头说明）。 */
  look: 'classic',
  themeVariables: {
    background: '#ffffff',
    primaryColor: '#ffffff',
    primaryTextColor: '#000000',
    primaryBorderColor: '#000000',
    lineColor: '#000000',
    secondaryColor: '#ffffff',
    tertiaryColor: '#ffffff',
    fontFamily: 'Noto Sans SC, Space Grotesk, sans-serif',
  },
  /** 节点描边 2px + 图内字体 + 键盘聚焦可见（见文件头：配方之外的几处补充）。 */
  themeCSS: [
    '.node rect, .node polygon, .node path { stroke-width: 2px }',
    '.nodeLabel, .edgeLabel, .label text, foreignObject div' +
      ' { font-family: "Noto Sans SC", "Space Grotesk", sans-serif }',
    // 节点可键盘聚焦（FlatMermaid 会给 g.node 加 tabindex）：聚焦用强调色描边，不用浏览器默认蓝圈
    '.node:focus-visible rect, .node:focus-visible polygon, .node:focus-visible path' +
      ` { outline: none; stroke: ${ACCENT_COLOR}; stroke-width: 3px }`,
  ].join(' '),
}

/** 扁平主题指令：所有 mermaid 渲染都带它（`flatThemeSource()` 会补在最前面）。 */
export const FLAT_THEME_INIT = `%%{init: ${JSON.stringify(FLAT_THEME)}}%%`

/** 源码没自带 init 指令时补上扁平主题；自带则尊重调用方（票 11 想换方向时只改源码）。 */
export function flatThemeSource(source: string): string {
  return source.trimStart().startsWith('%%{init') ? source : `${FLAT_THEME_INIT}\n${source}`
}

export interface FlowchartNode {
  /** 业务 id（知识点 id 等）；不必是合法的 mermaid 节点名。 */
  id: string
  label: string
  /** 命中的知识点：强调色描边，不填充色块（风格文档第 7 节图谱清单）。 */
  highlighted?: boolean
}

export interface FlowchartEdge {
  from: string
  to: string
  relation: string
}

export interface FlowchartOptions {
  /** 布局方向：默认自顶向下（知识点标题较长，横排会把画布拉得很宽）。 */
  direction?: 'TB' | 'LR'
  /** 连线上写关系名：默认不写（四种关系已由线型区分，写满会糊）。 */
  showRelationLabels?: boolean
}

export interface FlowchartSource {
  /** 交给 `<FlatMermaid source={...} />` 的 mermaid 源码（含扁平主题指令）。 */
  source: string
  /** mermaid 节点名 → 业务 id：点击节点时用它翻回知识点。 */
  nodeIdByMermaidId: Record<string, string>
}

/** 节点文字里 mermaid 认得的 HTML 实体：冒号与引号会把语法弄坏，统一转义。 */
function escapeLabel(label: string): string {
  return label.replaceAll('"', '#quot;').replaceAll('\n', ' ').trim()
}

/** mermaid 画直角折线时在拐点处的倒角命令：`Q 拐点 倒角终点`。 */const ROUNDED_CORNER = /Q(-?[\d.]+),(-?[\d.]+) (-?[\d.]+),(-?[\d.]+)/g

/**
 * 把连线转弯处的 5px 倒角还原成直角（第 8 节要求「直角折线」，风格文档要求零圆角）。
 *
 * 为什么是在渲染后处理、而不是配 `flowchart.curve`：实测 mermaid 12 的流程图渲染固定走带
 * 倒角的路径函数，`flowchart.curve`（step / linear / basis 等取值逐个试过）与
 * `linkStyle … interpolate` 都不改变输出，那个配置项在这条路径上是死的。
 * 还原是无损的：倒角的控制点就是原拐点，`Q 拐点 终点` 换成 `L 拐点 L 终点` 就是原折线。
 * 只改连线（`flowchart-link`）的 `d`：节点形状（如要圆角节点）一律不碰。
 */
export function sharpenLinkCorners(svg: string): string {
  return svg.replace(/<path\b[^>]*flowchart-link[^>]*>/g, (tag) =>
    tag.replace(
      /(\sd=")([^"]*)(")/,
      (_all, head: string, d: string, tail: string) =>
        head + d.replace(ROUNDED_CORNER, 'L$1,$2 L$3,$4') + tail,
    ),
  )
}

/**
 * 从「知识点 + 关系」生成 mermaid 源码。
 *
 * 节点名用 `n0`、`n1`…：知识点 id 是 UUID（数字开头、带连字符），不能直接当 mermaid 节点名，
 * 故节点名与业务 id 的对应关系随源码一起返回（`nodeIdByMermaidId`）。
 * 端点不在节点集合里的关系不画（过滤后不留悬空连线）。
 */
export function buildFlowchartSource(
  nodes: readonly FlowchartNode[],
  edges: readonly FlowchartEdge[],
  options: FlowchartOptions = {},
): FlowchartSource {
  const { direction = 'TB', showRelationLabels = false } = options
  const mermaidIdByNodeId = new Map<string, string>()
  const reverse: Array<[string, string]> = []
  const highlighted: string[] = []

  nodes.forEach((node, index) => {
    const mermaidId = `n${index}`
    mermaidIdByNodeId.set(node.id, mermaidId)
    reverse.push([mermaidId, node.id])
    if (node.highlighted) {
      highlighted.push(mermaidId)
    }
  })

  const lines = [FLAT_THEME_INIT, `flowchart ${direction}`]
  for (const node of nodes) {
    lines.push(`    ${mermaidIdByNodeId.get(node.id)}["${escapeLabel(node.label)}"]`)
  }

  const accentEdges: number[] = []
  let drawn = 0
  for (const edge of edges) {
    const from = mermaidIdByNodeId.get(edge.from)
    const to = mermaidIdByNodeId.get(edge.to)
    if (!from || !to) {
      continue
    }
    const style = relationStyle(edge.relation)
    const label = showRelationLabels ? `|${escapeLabel(edge.relation)}|` : ''
    lines.push(`    ${from} ${style.arrow}${label} ${to}`)
    if (style.color === ACCENT_COLOR) {
      accentEdges.push(drawn)
    }
    drawn += 1
  }

  if (highlighted.length > 0) {
    lines.push(`    classDef hit stroke:${ACCENT_COLOR},stroke-width:3px`)
    lines.push(`    class ${highlighted.join(',')} hit`)
  }
  // 连线颜色：黑是主题的默认值（`lineColor`），只有「相关关联」需要覆盖成强调色。
  // 注意**不能**写 `linkStyle default stroke:#000000`：mermaid 会把 linkStyle 里的颜色
  // 拼在每条连线样式串的最前面，而箭头 marker 的颜色取的是**第一个** stroke，
  // 于是强调色连线的箭头会变成黑的（它的线是强调色、箭头却是黑）。
  if (accentEdges.length > 0) {
    lines.push(`    linkStyle ${accentEdges.join(',')} stroke:${ACCENT_COLOR}`)
  }

  return { source: lines.join('\n'), nodeIdByMermaidId: Object.fromEntries(reverse) }
}

/**
 * 让 mermaid 画的节点可以被 Tab 到（风格文档：可交互就要键盘可达、聚焦可见）。
 *
 * mermaid 只给节点画了图形，不带任何焦点语义；不补这一步，键盘用户就点不开节点详情。
 * 聚焦样式写在主题的 themeCSS 里（`.node:focus-visible …`），故这里只补语义属性。
 */
export function makeNodesFocusable(container: HTMLElement): void {
  container.querySelectorAll('g.node').forEach((node) => {
    node.setAttribute('tabindex', '0')
    node.setAttribute('role', 'button')
  })
}

/**
 * 从 mermaid 生成的节点 domId 取回节点名。
 *
 * mermaid 把节点画成 `<g class="node" id="<图 id>-flowchart-<节点名>-<序号>">`：
 * 中间那截是节点名（我们生成的是 `n0`、`n1`…），序号是它自己的计数器，
 * 前缀是本次渲染的图 id（同一页多个图时用来唯一化），故三截都可能有。
 * 在真渲染的 SVG 上验证过（jsdom + 真 mermaid），别改成从串首开始匹配。
 */
export function mermaidNodeIdFromDomId(domId: string): string | null {
  const matched = /(?:^|-)flowchart-(.+)-\d+$/.exec(domId)
  return matched ? matched[1] : null
}
