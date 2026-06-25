# BBDown2.0

BBDown2.0 是一个 Windows 桌面工具，用来降低批量处理视频、音频素材的操作成本。

它支持 B站链接批量下载音频，也支持将抖音音频链接、本地音频、本地视频批量转写为文字，适合整理口播文案、字幕文本和音频内容。

## 功能

### B站批量下载

- 支持 B站链接批量下载音频
- 支持一行一个链接批量处理
- 支持 WEB / TV 扫码登录
- 下载失败或未产出音频的链接会自动保留，方便重试

### 批量转文字

支持两种模式：

1. 抖音链接转文字  
   粘贴抖音音频直链，或粘贴包含音频直链的整段文本，软件会自动提取可转写链接。

2. 音视频转文字  
   选择本地音频、视频文件，或直接选择文件夹批量转写。

支持导出格式：

- txt
- srt
- ass

## 安装方式

### 方式一：安装包安装

前往 Releases 下载：

```text
BBDown-Setup-2.0.0.exe
```

双击安装包，按照提示安装即可。

### 方式二：解压直接用

前往 Releases 下载：

```text
BBDown-2.0.0-unzip-run.zip
```

使用方法：

1. 解压 zip 文件。
2. 打开解压后的 `BBDown` 文件夹。
3. 双击 `BBDown.exe` 运行。

注意：不要只单独拷贝 `BBDown.exe`。解压后的 `_internal` 文件夹必须和 `BBDown.exe` 放在一起，否则软件无法正常启动。

## 源码运行

如果你下载的是源码，需要先安装 Python 3.10+。

打开 PowerShell，进入项目目录后执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

依赖安装完成后，后续可以直接双击：

```text
run_source.bat
```

## 项目结构

```text
BBDown2.0/
├─ app.py
├─ core/                         # 下载、配置、任务调度、转写服务
│  ├─ asr_service.py              # ASR 接口封装
│  ├─ asr_task.py                 # 转写任务处理
│  ├─ asr_file_worker.py          # 本地文件转写后台任务
│  ├─ url_asr_worker.py           # 音频链接转写后台任务
│  ├─ url_audio.py                # 音频链接识别和读取
│  ├─ task_scheduler.py           # 并发任务调度
│  └─ workers.py                  # B站下载和登录后台任务
├─ ui/                            # 图形界面
├─ bk_asr/                        # ASR 实现
├─ tools/                         # BBDown、FFmpeg、aria2c
├─ requirements.txt
├─ build_bbdown_launcher.spec
└─ installer.iss
```

## 打包

安装依赖后执行：

```powershell
.\.venv\Scripts\python.exe -m PyInstaller build_bbdown_launcher.spec --noconfirm
```

打包结果位于：

```text
dist\BBDown\BBDown.exe
```

如需生成安装包，需要先安装 Inno Setup 6，然后执行：

```powershell
ISCC.exe installer.iss
```

安装包默认输出到：

```text
installer_output\
```

## 作者声明

本仓库由作者借助人工智能工具整理、开发和维护。

未经作者许可，禁止以任何形式冒用作者身份发布本项目，禁止将本项目用于侵犯他人知识产权、违反平台规则或违反法律法规的用途。由此产生的责任由行为人自行承担。

最终解释权归作者所有。
