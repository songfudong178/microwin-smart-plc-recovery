# 只读静态预检工具

在生成输入后、原生导入前运行。它不是 Siemens 编译器，也不会安装软件、操作 UI、联网、连接 PLC、执行 manifest 内代码、修改输入或自动修复。

```text
python -B scripts/plc_preflight.py --manifest D:/YourProject/preflight.json
python -B scripts/test_plc_preflight.py -v
python -B scripts/test_plc_preflight.py --temp-root D:/YourProject/test-temp -v
```

路径只是示例，不是本项目配置。工具报告仅输出到 stdout，为单个 JSON；如需保存，应由调用者明确选择新报告路径，避免覆盖旧验收证据。`-B` 禁止生成 `__pycache__`。测试默认仅在 `D:/CodexData/Caches/PLC-Skill-Tests` 内创建独立临时目录，清理前解析实际绝对路径并确认它是所选临时根的严格子目录，不删除根目录；其它机器必须用 `--temp-root` 指定绝对目录，不回退到系统临时目录。

## 结果与退出码

| 字段/退出码 | 含义 |
|---|---|
| `errors` | 明确不符合已实现检查，含结构化 `code/location/message` |
| `review_required` | 不支持、无法判断或缺少人工完整性声明；不是通过 |
| `checks` | 实际做了什么、范围多大；不能据此推断检查之外也正确 |
| `hashes` | 工具、manifest、上下文、实际输入和证据的 SHA-256 |
| `successful=true` / 0 | 仅已实现的检查没有错误或待核项目 |
| 1 | 输入检查失败或仍有待核项目 |
| 2 | CLI 参数、manifest 结构/内容/路径不合法或不可读取 |
| `native_acceptance=false` | 无论静态结果如何，始终为 false |

不覆盖完整指令语法/操作数类型、参数声明语义、真实 CALL 签名、间接访问/写所有权、库内部执行、定时器/边沿动态生命周期、CPU/固件真实兼容和容量、LAD 全段显示、保存重开、过程安全及现场运行。原生往返可执行指令对照仍是独立步骤。未知 AWL 指令不会由本工具冒充编译器判定合法；包装检查通过不等于程序可编译。

## manifest v1：完整结构

JSON 使用 UTF-8。重复 JSON 键、非 JSON 数值 NaN/Infinity、未知字段或错误类型会失败。除 `inventory` 外，以下顶层字段均必填；不适用的列表明确写 `[]`，不省略。所有子对象必须恰好包含下面列出的字段。

| 字段 | 定义 |
|---|---|
| `schema_version` | 整数 `1`，不是字符串或布尔值 |
| `target` | 恰含 `vendor/family/cpu/firmware/software/software_version` 六个非空字符串。当前仅支持 `vendor="Siemens"`、`family="S7-200 SMART"`。这些是声明，不是工具探测到的硬件。`unknown/unverified/待核/未知/未核实` 产生待核。 |
| `import` | 恰含 `scope`（`partial`/`full`）、`allowed_pous`、`protected_pous`。两列表都只接受 `OB1/SBRn/INTn`，不能重复。 |
| `inputs` | 文件对象列表，`id` 全局唯一，至少一个 AWL 文件。每个对象恰含 `id/path/kind/encoding/profile` 五个非空字符串。 |
| `inventory` | 可省略，但省略或未确认会产生待核。恰含布尔 `symbol_tables_complete`、非空字符串 `basis`。声明必须包含对全部用户、I/O、系统、库符号表的核对依据；自报 true 不证明实际没有漏表。 |
| `allocations` | 非空地址/类型/写入所有者清单，每项恰含 `id/address/type/owner/count`。`id` 唯一；前四项非空字符串；`count` 是 `1..65536` 的整数。 |
| `aliases` | 有意地址视图列表，每项恰含 `left/right/reason` 三个非空字符串；left/right 是两个不同 allocation id。只豁免该显式分配对的重叠，不能取消符号重名或完全同址错误。 |
| `migrations` | 每项恰含 `old_name/new_name/address/type`。old_name/address/type 非空；new_name 是新全局符号名，或 `null` 表示改用已核对的绝对地址。不是自动重命名指令。 |
| `evidence` | 每项恰含 `id/file/sha256/context_sha256/input_sha256`。id 唯一；file 为本地文件；两个 sha256 为64位十六进制；input_sha256 是 `{输入id: SHA-256}`。 |
| `required_evidence` | 不重复的 evidence id 列表。每个必须实际声明并可读取；缺少会失败。空列表仅表示本次没有要求已有证据，不代表完成了原生验收。 |

### 输入 profile

| kind | encoding | profile | 检查范围 |
|---|---|---|---|
| `awl` | `gbk` | `microwin_awl` | GBK严格往返、无BOM、CRLF、POU/BEGIN/END/NETWORK包装及导入范围；不是完整语法编译 |
| `symbols_tsv` | `utf-8` | `clipboard_local_v1` | 三列 `符号\t地址\t注释`、无表头、CRLF、无BOM、无尾部换行/空行；注释可空但第三列必须存在 |
| `db` | `gbk`或`utf-8` | `simple_numeric_db` | 严格编码、无BOM、CRLF及下面限定的简单数值初始化 |
| `opaque` | `binary` | `hash_only` | 只计算文件哈希，同时必定产生待核；适合登记暂不能分析的原生/系统块文件 |

`clipboard_local_v1` 是本机已用的粘贴载荷工程约定，不是所有 Siemens 版本的厂家格式要求；不得把 AWL 的 GBK 文件要求套用为剪贴板编码要求。原始空文件、缺文件、未知 kind/profile/encoding 不通过。单个 manifest/input/evidence 读取上限32 MiB。禁止 HTTP/其它URL、UNC及设备路径；相对路径以 manifest 所在目录为基准，不展开环境变量、不下载内容。

### AWL 导入包装

`allowed_pous` 在本工具中既是允许集合，也是本次预期导入集合：实际各 AWL 文件的 POU 并集必须与它完全一致，防止漏块。POU标头可为 `SUBROUTINE_BLOCK SBR1` 或 `SUBROUTINE_BLOCK Name:SBR1`；不得重复。Network 必须从1连续编号；BEGIN、END和块类型必须配对。

`partial` 绝不允许 OB1，即使误把 OB1 写进 allowed_pous；`full` 必须包含 OB1。声明在 `protected_pous` 的块不得出现在输入中。受保护导出标记会报错；无法证明内容的空POU产生待核，不把桩当完整库代码。受保护标记的有限文本识别不能代替人工库存量/保护属性核查。

TITLE和常见VAR包装被识别，但参数类型和CALL签名不由此获得验证。未知 BEGIN 前语法产生待核。工具不对每条 AWL 指令进行全语言解析，也不证明剩余现有工程中没有同号POU；allowed/protected 清单需要来自目标工程。

### 地址与符号

支持直接位/字节地址 `I/Q/M/V/L/S/SM/AI/AQ` 的 `区字节.位`、`区B/W/D字节` 形式，例如 `M0.0`、`VW100`、`AIW16`；这只是解析形式，不证明该CPU允许对应实际范围。支持 `BOOL/BYTE/WORD/INT/DWORD/DINT/REAL`，要求声明类型宽度与地址宽度一致。count 是同类型连续元素数，按位半开区间检查整个分配范围。T/C/HC、字符串、结构体、其它类型/语法产生待核。

所有已声明符号表合并检查，不能只检查新表：重复名称按 casefold 保守识别；完全同址报错；部分字/位重叠必须有对应 allocation 视图的显式 alias，否则待核。不能用一个宽泛大分区掩盖符号重叠。工具不验证 alias 原因是否属实，写入冲突仍需人工/原生审查。

符号名不能数字开头，允许下划线；实现按字母、数字、下划线及扩展字符保守检查，要求可GBK编码且不超过23字节。这是中文环境的保守工程策略，不是厂家对所有 Unicode 字符的完整规则。`RESERVED` 仅为已知关键字小子集，绝非 Siemens 完整保留字表；完整关键字合法性仍由原生软件确认。符号常数或不支持的地址语法产生待核。

### 迁移残留

对声明的所有 AWL 与 DB 文本查找完整 old_name 标识符，不扫描TSV注释，不把 `//` 注释、TITLE元数据和引号字面值算作引用；识别 `//` 时保留字符串内的同形字符。未实现其它厂商的注释/语言规则。

new_name 非空时必须在已提交符号输入中存在且映射到声明地址；迁移地址/类型也必须与 allocation 一致。旧名→新名清单不能自行证明所有原生页面均已导出，状态图/趋势图等辅助引用也不在当前扫描范围，需单独核查。

### 简单数值 DB 子集

仅支持裸数值行（可有 `//` 注释），例如：

```text
VW100 +1
VW102 -2, +3
VD200 1.5
VB300 16#FF, 2#01
```

每个逗号值按 B/W/D 宽度向后推进，跨所有DB输入检查地址重复/重叠，必须由无歧义、同宽度、对齐的 allocation 类型覆盖。BYTE/WORD/DWORD检查无符号范围，INT/DINT检查有符号十进制范围，REAL要求带小数点或指数且有限、适合32位。INT/DINT的十六进制/二进制位模式存在类型解释边界，转为待核，不假装已经证明其有符号语义。

DB包装、符号地址、数组语法、重复计数语法、字符串、等号赋值（例如 `VW100 = +1`）、其它表达式和不认识的字面量均产生待核；不能将这些语法静默跳过后报通过。此处没有将等号当作已经取得官方/原生依据的 MicroWIN DB 分隔符。

### 哈希证据绑定

`sha256` 绑定证据文件本身；每项 `input_sha256` 必须恰好覆盖全部声明 inputs，不能遗漏符号、DB或其它输入，也不能引入未知id。

`context_sha256` 绑定目标身份及全部manifest决策（仅去掉顶层 evidence，避免自引用）：

```python
payload = {k: v for k, v in manifest.items() if k != 'evidence'}
context = hashlib.sha256(json.dumps(payload, sort_keys=True,
    ensure_ascii=False, separators=(',', ':')).encode('utf-8')).hexdigest()
```

变更CPU、软件版本、导入列表、地址分配、迁移/粘贴profile等，会使旧证据上下文失效。工具在首次读取时记录文件哈希；同路径再次读取发生变化立即报错，结束时再与首次值核对。工具不能保证检查结束之后文件不再变更；交付/导入前仍要绑定实际产物。

哈希并不认证证据作者、截图真实性或测试覆盖度，也不把旧编译通过升级为新目标通过。原生编译、LAD、保存重开和现场验收依然必须各有对应证据。

## 最小示例

以下是可自行填充文件的完整manifest示例，不含项目地址/站号。它没有声明原生验收证据，只可得到静态预检结论。`demo.awl` 应包含 SBR1 的合法包装；`symbols.tsv` 三列一行且末尾无换行；`data.db` 一行 `VW100 +1`；地址只是示意。

```json
{
  "schema_version": 1,
  "target": {
    "vendor": "Siemens", "family": "S7-200 SMART", "cpu": "ST40",
    "firmware": "2.8", "software": "STEP 7-Micro/WIN SMART", "software_version": "2.8"
  },
  "import": {"scope": "partial", "allowed_pous": ["SBR1"], "protected_pous": ["SBR0"]},
  "inputs": [
    {"id": "program", "path": "demo.awl", "kind": "awl", "encoding": "gbk", "profile": "microwin_awl"},
    {"id": "symbols", "path": "symbols.tsv", "kind": "symbols_tsv", "encoding": "utf-8", "profile": "clipboard_local_v1"},
    {"id": "data", "path": "data.db", "kind": "db", "encoding": "gbk", "profile": "simple_numeric_db"}
  ],
  "inventory": {"symbol_tables_complete": true, "basis": "示例输入是全部表；真实工程须填写实际核对依据"},
  "allocations": [
    {"id": "value", "address": "VW100", "type": "INT", "owner": "demo", "count": 1}
  ],
  "aliases": [], "migrations": [], "evidence": [], "required_evidence": []
}
```

符号示意行为 `Counter`、`VW100`、`示例值` 三个字段，由真正的Tab分隔。AWL示意内容如下（落盘时为GBK/CRLF）：

```text
SUBROUTINE_BLOCK SBR1
TITLE=demo
BEGIN
NETWORK 1
LD SM0.0
MOVW +1, VW100
END_SUBROUTINE_BLOCK
```

此工具检查 allocation 自身及其与符号/DB的关系；不声称已从AWL完整推断全部读写地址或所有者，因此示例 `SM0.0` 不会被冒充做全语言读写证明。

添加证据时，用真实文件SHA填写，不可照抄占位哈希：

```json
{
  "id": "native_compile",
  "file": "evidence/compile.pdf",
  "sha256": "实际证据文件的64位SHA256",
  "context_sha256": "以上公式得出的64位SHA256",
  "input_sha256": {
    "program": "demo.awl的64位SHA256",
    "symbols": "symbols.tsv的64位SHA256",
    "data": "data.db的64位SHA256"
  }
}
```

将其加入 evidence，再将id加入 required_evidence；required_evidence属于context，必须先确定再算context哈希。这些说明里的非64位文本只是填值说明，工具会拒绝它们。
