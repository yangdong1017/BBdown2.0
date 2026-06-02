# BBDown

BBDown 是一个 Windows 桌面工具，支持批量下载 B 站视频音频，并将音视频文件批量转写为文字。



## 功能特性

- 批量下载 B 站视频音频
- 支持一行一个链接批量处理
- 支持 WEB / TV 扫码登录
- 自动调用 BBDown、FFmpeg、aria2c
- 下载完成后可直接进入转文字流程
- 支持音频 / 视频文件批量转写
- 支持必剪、剪映、快手 ASR 接口
- 支持导出 txt、srt、ass 格式
- Windows 图形化界面，无需命令行操作

## 运行环境

源码运行需要：

- Windows 10 / Windows 11
- Python 3.10+
- 网络连接
- 可选：哔哩哔哩 App，用于扫码登识舰长权限视频 

如果使用已打包的 exe 或安装包，则不需要安装 Python。

## 快速开始

### 方式一：使用打包好的 exe

如果你只是想使用软件，推荐下载已经打包好的 exe 或安装包。

下载后直接双击运行即可，不需要安装 Python，也不需要手动安装依赖。

### 方式二：从源码运行

如果你下载的是源码，需要先安装 Python 环境和项目依赖。

打开 PowerShell，进入项目目录后执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py

依赖安装完成后，后续可以直接双击运行：

run_source.bat
不建议直接双击 app.py。直接双击可能不会使用项目里的 .venv 虚拟环境，容易出现依赖找不到、窗口打不开等问题。


使用方法
打开软件。
在“批量下载”页面粘贴 B 站链接，一行一个。
选择保存目录和下载并发数。
如内容需要登录权限，先使用二维码扫码登录。
点击“开始下载”。
下载完成后，文件会自动加入“批量转文字”页面。
选择 ASR 接口、输出格式和并发数。
点击“开始转文字”，等待结果生成。
输出格式
转写结果支持以下格式：

txt：普通文本
srt：字幕文件
ass：高级字幕文件
默认输出到源文件所在目录，也可以在界面中手动选择输出目录。

打包
安装依赖后执行：

.\.venv\Scripts\python.exe -m PyInstaller build_bbdown_launcher.spec --noconfirm
打包结果位于：

dist\BBDown\BBDown.exe
如需生成安装包，可安装 Inno Setup 6，然后执行：

ISCC.exe installer.iss
安装包默认输出到：

installer_output\
项目结构
BBDown/
├─ app.py
├─ core/              # 下载、配置、工具链、后台任务
├─ ui/                # 图形界面
├─ bk_asr/            # ASR 转写模块
├─ tools/             # BBDown、FFmpeg、aria2c
├─ requirements.txt
├─ build_bbdown_launcher.spec
└─ installer.iss



此仓库全部由人工智能允许，更改。作者禁止以任何形式包括但不限于使用、转载、二创、造成任何知识侵犯，需承担法律责任。

最终解释权归作者所有 


那你来根据我改写的继续进行更改，快速开始重写
