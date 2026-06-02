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

使用安装包或“解压直接用”版本不需要安装 Python。

运行软件需要：

- Windows 10 / Windows 11
- 网络连接
- 可选：哔哩哔哩 App，用于扫码登录舰长权限视频或其他需要登录权限的视频

如果需要从源码运行或自行打包，则需要额外安装 Python 3.10+。

## 安装方式

### 方式一：安装包安装

前往 Releases 下载：

```text
BBDown-Setup-1.0.0.exe
```

双击安装包，按照提示安装即可。

这种方式会创建软件安装目录和快捷方式，适合大多数用户。

### 方式二：解压直接用

前往 Releases 下载：

```text
BBDown-1.0.0-unzip-run.zip
```

使用方法：

1. 解压 zip 文件。
2. 打开解压后的 `BBDown` 文件夹。
3. 双击 `BBDown.exe` 运行。

注意：不要只单独拷贝 `BBDown.exe`。解压后的 `_internal` 文件夹必须和 `BBDown.exe` 放在一起，否则软件无法正常启动。

## 源码运行

如果你下载的是源码，需要先安装 Python 环境和项目依赖。

打开 PowerShell，进入项目目录后执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

依赖安装完成后，后续可以直接双击运行：

```text
run_source.bat
```

不建议直接双击 `app.py`。直接双击可能不会使用项目里的 `.venv` 虚拟环境，容易出现依赖找不到、窗口打不开等问题。

## 使用方法

1. 打开软件。
2. 在“批量下载”页面粘贴 B 站链接，一行一个。
3. 选择保存目录和下载并发数。
4. 如内容需要登录权限，先使用二维码扫码登录。
5. 点击“开始下载”。
6. 下载完成后，文件会自动加入“批量转文字”页面。
7. 选择 ASR 接口、输出格式和并发数。
8. 点击“开始转文字”，等待结果生成。

## 输出格式

转写结果支持以下格式：

- `txt`：普通文本
- `srt`：字幕文件
- `ass`：高级字幕文件

默认输出到源文件所在目录，也可以在界面中手动选择输出目录。

## 打包

安装依赖后执行：

```powershell
.\.venv\Scripts\python.exe -m PyInstaller build_bbdown_launcher.spec --noconfirm
```

打包结果位于：

```text
dist\BBDown\BBDown.exe
```

如需生成安装包，可安装 Inno Setup 6，然后执行：

```powershell
ISCC.exe installer.iss
```

安装包默认输出到：

```text
installer_output\
```

## 项目结构

```text
BBDown/
├─ app.py
├─ core/              # 下载、配置、工具链、后台任务
├─ ui/                # 图形界面
├─ bk_asr/            # ASR 转写模块
├─ tools/             # BBDown、FFmpeg、aria2c
├─ requirements.txt
├─ build_bbdown_launcher.spec
└─ installer.iss
```

## 作者声明

本仓库由作者借助人工智能工具整理、开发和维护。

未经作者许可，禁止以任何形式冒用作者身份发布本项目，禁止将本项目用于侵犯他人知识产权、违反平台规则或违反法律法规的用途。由此产生的责任由行为人自行承担。

最终解释权归作者所有。
