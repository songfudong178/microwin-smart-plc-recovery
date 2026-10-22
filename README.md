# S7-200 SMART PLC 编写与恢复技能

面向 Codex 等支持 SKILL.md 的 AI 助手，用于西门子 S7-200 SMART / STEP 7-Micro/WIN SMART 的程序编写、修改、审查和梯形图恢复。整理自供气站、空压站工程实践。

## 主要内容

- 编写前确认地址、数据类型、写入归属、扫描顺序、首次扫描及保持行为。
- 按可转换为梯形图的结构生成 AWL/STL，保留厂家库、符号和数据块。
- 检查导入文件的编码、程序块范围、符号迁移和地址重叠。
- 分别记录静态检查、原生梯形图显示、完整编译、保存重开和现场验收。
- 使用通俗中文描述程序，不把命令发出误写成设备已经执行。

## 安装到 Codex

将本仓库完整下载或克隆到 Codex 技能目录中的 `microwin-smart-plc-recovery` 文件夹。默认位置为 `~/.codex/skills/microwin-smart-plc-recovery`；如果设置了 CODEX_HOME，则使用该目录下的 `skills` 文件夹。保留 `SKILL.md`、`references`、`scripts` 和 `agents` 的目录关系，重新启动 Codex 后使用。

也可以告诉 Codex：

```text
请安装 https://github.com/songfudong178/microwin-smart-plc-recovery 中的技能。
```

## 使用

```text
使用 $microwin-smart-plc-recovery 审查这个 S7-200 SMART 工程。
先确认 CPU、MicroWIN SMART 版本、库和地址分配，再提出修改方案。
```

技能入口见 [SKILL.md](SKILL.md)，编写规则见 [programming-rules.md](references/programming-rules.md)，静态检查的输入格式见 [preflight-tool.md](references/preflight-tool.md)。

## 检查脚本

需要 Python 3，脚本仅使用标准库。在仓库目录运行：

```text
python -B scripts/plc_preflight.py --manifest D:/YourProject/preflight.json
python -B scripts/test_plc_preflight.py --temp-root D:/CodexData/Caches/PLC-Skill-Tests -v
```

其他操作系统请把示例路径替换为本机绝对路径，测试使用 `--temp-root` 指定临时目录。

## 适用范围与验证边界

这是 AI 工作指引与静态检查工具，不是西门子编译器，也不包含 MicroWIN SMART 软件或现场 PLC 工程。它不会连接、下载或操作 PLC。生成的工程仍需在对应版本 MicroWIN SMART 中完成编译、梯形图检查和保存重开验证；现场操作须另行获得授权。

参考资料中的历史验收是特定工程记录，不代表本仓库能够保证任意程序首次编译通过或现场运行成功。公开版不包含内部工程证据文件，相关说明保留了这一边界。
