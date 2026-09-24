/**
 * 禁用 class 扫描 —— docs/style/minimalist-flat.md 第 6 节的 10 条规则。
 *
 *   npm run check:classes        （已挂进 npm run lint 与 npm run build）
 *
 * 扫描范围：frontend/src/**\/*.{ts,tsx,css}。任一命中即失败（退出码 1），
 * 输出 文件:行:列 + 规则号 + 命中片段。允许例外只按风格文档写死，不做行内豁免。
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const frontendDir = resolve(scriptDir, '..')
const scanRoot = resolve(frontendDir, 'src')
const extensions = new Set(['.ts', '.tsx', '.css'])

/** 风格文档第 6 节表格：规则号 / 名称 / 正则 / 允许例外（命中全等即放过）。 */
const RULES = [
  { id: 1, name: '阴影', pattern: /(?<![\w-])(shadow|drop-shadow)(-[a-z0-9]+)?/g, allowed: ['shadow-none'] },
  { id: 2, name: '圆角', pattern: /(?<![\w-])rounded(-[a-z0-9]+)?/g, allowed: ['rounded-none'] },
  { id: 3, name: '渐变', pattern: /bg-gradient-|(?:^|\s)(?:from|via|to)-[a-z0-9]+/g, allowed: [] },
  { id: 4, name: '灰度底色', pattern: /bg-(?:gray|slate|zinc|neutral|stone)-\d+/g, allowed: [] },
  { id: 5, name: '半透明底色', pattern: /bg-(?:black|white)\/\d+|bg-opacity-\d+/g, allowed: [] },
  { id: 6, name: '模糊材质', pattern: /backdrop-blur(-[a-z0-9]+)?|blur-(?:sm|md|lg|xl)/g, allowed: [] },
  { id: 7, name: '越界过渡', pattern: /transition-all|transition-transform|transition-(?:shadow|filter)/g, allowed: [] },
  {
    id: 8,
    name: '超时长动效',
    pattern: /duration-(?:250|300|500|700|1000)|animate-(?:bounce|pulse|ping)/g,
    allowed: [],
  },
  {
    id: 9,
    name: '非强调彩色',
    pattern: /(?:bg|text|border)-(?:red|green|blue|yellow|orange|purple|pink|indigo|teal|cyan)-\d+/g,
    allowed: [],
  },
  { id: 10, name: '外链字体', pattern: /fonts\.googleapis\.com|fonts\.gstatic\.com/g, allowed: [] },
]

function collectFiles(dir) {
  const found = []
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name)
    if (entry.isDirectory()) {
      found.push(...collectFiles(full))
    } else if (extensions.has(full.slice(full.lastIndexOf('.')))) {
      found.push(full)
    }
  }
  return found
}

function scanFile(file) {
  const violations = []
  const lines = readFileSync(file, 'utf8').split(/\r?\n/)
  lines.forEach((line, index) => {
    for (const rule of RULES) {
      rule.pattern.lastIndex = 0
      for (const match of line.matchAll(rule.pattern)) {
        const hit = match[0]
        if (rule.allowed.includes(hit)) continue
        violations.push({
          file,
          line: index + 1,
          column: match.index + 1,
          rule,
          hit: hit.trim(),
        })
      }
    }
  })
  return violations
}

if (!statSync(scanRoot, { throwIfNoEntry: false })) {
  console.error(`[check:classes] 找不到扫描目录：${scanRoot}`)
  process.exit(1)
}

const files = collectFiles(scanRoot)
const violations = files.flatMap(scanFile)

if (violations.length > 0) {
  console.error('[check:classes] 禁用 class 扫描未通过（docs/style/minimalist-flat.md 第 6 节）：')
  for (const v of violations) {
    const where = `${relative(frontendDir, v.file)}:${v.line}:${v.column}`
    console.error(`  ✗ 规则 ${v.rule.id} ${v.rule.name} · ${where} · 命中「${v.hit}」`)
  }
  console.error(`[check:classes] 共 ${violations.length} 处违规，${files.length} 个文件已扫描。`)
  process.exit(1)
}

console.log(`[check:classes] 禁用 class 扫描通过：${files.length} 个文件，10 条规则零违规。`)
