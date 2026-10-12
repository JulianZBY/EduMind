/**
 * 从 FastAPI app 直接 dump OpenAPI schema —— 不启动服务、不访问端口、不联网。
 *
 *   node scripts/dump-openapi.mjs        （等价于 npm run openapi:snapshot）
 *
 * 前置：`mise run setup:backend`（首次，或后端依赖变更后重跑一次）。
 * 输出：openapi/openapi.json（入库）。前端 TS 类型由它生成（npm run openapi:types），
 * 因此后端改接口后只需重跑本脚本 + 类型生成，仓库内永远不需要手抄接口类型。
 */
import { spawnSync } from 'node:child_process'
import { mkdirSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const frontendDir = resolve(scriptDir, '..')
const backendDir = resolve(frontendDir, '../backend')
const outFile = resolve(frontendDir, 'openapi/openapi.json')

// 在 backend/ 里跑（cwd 进 sys.path，故 `from app.main import app` 可直接导入）。
// 只 import app 对象取 app.openapi()，不触发 lifespan，故不会建库、不会起服务。
const PYTHON_SNIPPET = [
  'import json, sys',
  'from app.main import app',
  'json.dump(app.openapi(), sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)',
  'sys.stdout.write("\\n")',
].join('\n')

function run(candidates, args, env = {}) {
  let lastError = null
  for (const bin of candidates) {
    const result = spawnSync(bin, args, {
      cwd: backendDir,
      encoding: 'utf8',
      maxBuffer: 64 * 1024 * 1024,
      env: { ...process.env, ...env },
    })
    if (result.error) {
      lastError = result.error
      if (result.error.code === 'ENOENT') continue
      return result
    }
    return result
  }
  return { error: lastError }
}
// 用后端 venv 的 python：绝对路径，避免 PATH 上其它 python 抢先（如 pi-lens 注入的）
const venvPython =
  process.platform === 'win32'
    ? resolve(backendDir, '.venv/Scripts/python.exe')
    : resolve(backendDir, '.venv/bin/python')
const pythonBinaries = [
  venvPython,
  ...(process.platform === 'win32' ? ['python.exe', 'python'] : ['python3', 'python']),
]
// Windows 控制台默认 GBK：schema 里的中文与「•」掩码字符会炸 stdout，钉住 UTF-8
const result = run(pythonBinaries, ['-c', PYTHON_SNIPPET], { PYTHONIOENCODING: 'utf-8' })
if (result.error) {
  console.error(`[openapi:snapshot] 无法执行后端 python（${result.error.message}）。`)
  console.error('[openapi:snapshot] 请先运行：mise run setup:backend')
  process.exit(1)
}

if (result.status !== 0) {
  console.error('[openapi:snapshot] 后端 schema 导出失败：')
  console.error(result.stderr?.trim() || `退出码 ${result.status}`)
  console.error('[openapi:snapshot] 前置步骤：mise run setup:backend')
  process.exit(1)
}

let schema
try {
  schema = JSON.parse(result.stdout)
} catch {
  console.error('[openapi:snapshot] 后端输出不是合法 JSON，未写入快照。')
  process.exit(1)
}

mkdirSync(dirname(outFile), { recursive: true })
writeFileSync(outFile, `${JSON.stringify(schema, null, 2)}\n`, 'utf8')

const operations = Object.values(schema.paths ?? {}).reduce(
  (total, item) => total + Object.keys(item).length,
  0,
)
console.log(`[openapi:snapshot] 已写入 ${outFile}`)
console.log(`[openapi:snapshot] ${Object.keys(schema.paths ?? {}).length} 条路径 / ${operations} 个操作`)
console.log('[openapi:snapshot] 接着跑 npm run openapi:types 生成 TS 类型')
