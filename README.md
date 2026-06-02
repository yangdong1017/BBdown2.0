# BBDown

Windows 图形化工具，用于批量下载 B 站视频音频，并将音视频批量转成文字。下载流程基于 BBDown，转写流程基于 AsrTools 的 `bk_asr` 模块，界面使用 PyQt5 + PyQt-Fluent-Widgets。

![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)
![Platform: Windows](https://img.shields.io/badge/Platform-Windows%2010%2F11-brightgreen)
![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-yellow)

## 功能

- 批量下载：一行一个 B 站链接，支持并发下载。
- 登录支持：支持 WEB / TV 扫码登录，适合需要登录态的视频。
- 音频输出：默认调用 `BBDown --audio-only`，输出音频文件。
- 自动衔接：下载完成后，生成的媒体文件会自动进入“批量转文字”页面。
- 批量转写：支持必剪、剪映、快手 ASR 接口。
- 多格式导出：支持 `txt`、`srt`、`ass`。
- 本地工具链：仓库默认包含 `tools/BBDown.exe`、`tools/ffmpeg.exe`、`tools/aria2c.exe`。

## 同事下载后能否直接使用

分两种情况：

1. 如果下载的是 GitHub Release 里的安装包或已打包 exe，可以直接双击使用，不需要安装 Python。
2. 如果下载的是源码仓库，需要先安装 Python 并安装依赖，然后运行项目。

当前仓库保留了 `tools/` 目录，所以源码运行时不需要同事单独安装 BBDown、FFmpeg、aria2c。但 `tools/` 里的二进制文件体积较大，仓库会比较重。如果后续不想把这些 exe 提交到 GitHub，可以把它们改为 Release 附件，并在使用前手动放回 `tools/` 目录。

## 源码运行环境

- Windows 10/11 64 位
- Python 3.10 或更高版本，建议 3.10 到 3.12
- 能访问 B 站和 ASR 接口的网络环境
- 可选：哔哩哔哩 App，用于扫码登录

## 从源码运行

```powershell
git clone https://github.com/<your-name>/BBDown.git
cd BBDown

python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

也可以在安装依赖后双击：

```text
run_source.bat
```

## 使用流程

1. 打开“批量下载”页面。
2. 粘贴 B 站视频链接，一行一个。
3. 选择保存目录和下载并发数。
4. 如视频需要登录权限，先用右侧二维码登录。
5. 点击“开始下载”。
6. 下载完成后，程序会切到“批量转文字”页面并加入本次下载的文件。
7. 选择 ASR 接口、输出格式和并发数，点击“开始转文字”。

## 打包 exe

打包前先安装依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

使用 PyInstaller 生成 onedir 版本：

```powershell
.\.venv\Scripts\python.exe -m PyInstaller build_bbdown_launcher.spec --noconfirm
```

产物位置：

```text
dist\BBDown\BBDown.exe
```

如果需要安装包，安装 Inno Setup 6 后执行：

```powershell
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
```

或者按本机安装路径替换 `ISCC.exe`。安装包产物默认在：

```text
installer_output\BBDown-Setup-1.0.0.exe
```

## 项目结构

```text
BBDown/
├─ app.py                         # 程序入口
├─ bbdown_launcher.pyw            # 无控制台入口
├─ run_source.bat                 # 源码启动脚本
├─ 启动BBDown图形界面.vbs          # 静默启动脚本
├─ requirements.txt               # Python 依赖
├─ build_bbdown_launcher.spec     # PyInstaller 配置
├─ installer.iss                  # Inno Setup 安装包脚本
├─ core/                          # 下载、配置、工具链和后台任务
├─ ui/                            # 图形界面
├─ bk_asr/                        # ASR 转写模块
└─ tools/                         # BBDown、FFmpeg、aria2c
```

## 不要提交到 GitHub 的文件

这些文件或目录由本机运行、下载、转写、打包时生成，已写入 `.gitignore`：

```text
.venv/
build/
dist/
installer_output/
bbdown_gui_config.json
bbdown_gui_logs/
bbdown_runtime/
bbdown_tools/
startup_trace.log
*.m4a
*.mp3
*.mp4
*.srt
*.ass
```

## 常见问题

### 运行源码时报 PyQt5 或 qfluentwidgets 找不到

说明还没有安装依赖，重新执行：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 下载失败或提示需要登录

先在软件右侧执行 WEB 或 TV 登录，扫码确认后再下载。部分视频可能需要账号权限、会员权限或地区权限。

### 转文字失败

转文字接口依赖第三方 ASR 服务和网络状态。可以切换必剪、剪映、快手接口重试；如果输入是视频文件，程序会先调用 FFmpeg 转成临时音频。

### GitHub 上传太慢或文件太大

`tools/ffmpeg.exe` 较大。为了让同事源码运行更省事，本仓库默认保留 `tools/`；如果更看重仓库体积，可以不提交 `tools/`，改为在 Release 中提供工具包，并让同事解压到 `tools/`。

## 第三方项目与许可

本项目整合或调用了以下项目，版权归原作者所有：

| 项目 | 用途 | 许可 |
| --- | --- | --- |
| [BBDown](https://github.com/nilaoda/BBDown) | B 站下载核心 | MIT |
| [yangdong1017/BBdown](https://github.com/yangdong1017/BBdown) | 图形化下载参考 | 以原项目为准 |
| [yangdong1017/AsrTools](https://github.com/yangdong1017/AsrTools) | ASR 转写参考 | 以原项目为准 |
| [FFmpeg](https://ffmpeg.org/) | 音视频处理 | GPL / LGPL，取决于构建方式 |
| [aria2](https://github.com/aria2/aria2) | 多连接下载 | GPLv2+ |
| [PyQt-Fluent-Widgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets) | Fluent 风格组件 | GPLv3 |

本仓库当前以 GPLv3 发布，详见 [LICENSE](LICENSE)。

## 使用声明

本工具仅供学习和内部效率使用。请遵守哔哩哔哩用户协议、内容版权规则和相关法律法规。下载和转写内容的使用责任由使用者自行承担。
