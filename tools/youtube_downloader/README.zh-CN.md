# YouTube 中文图形下载器

这是本仓库中独立的 Windows / 桌面图形下载工具，使用 yt-dlp 作为下载引擎；不修改原版 yt-dlp 命令行入口或核心提取器。

## Windows 启动

双击本目录的 start_windows.cmd，或在仓库根目录运行：

    py -3 tools\youtube_downloader\app.py

图形界面使用 Python 标准库 Tkinter，不依赖额外的前端或 Web 服务。

### 首次运行前

1. yt-dlp：建议从 https://github.com/yt-dlp/yt-dlp/releases/latest 下载最新版 yt-dlp.exe 加入 PATH，或在界面中选择 exe 文件。若找不到，程序回退到 python -m yt_dlp。此 Fork 的版本可能落后于上游，无法正常处理 YouTube 时优先更新独立可执行文件。
2. FFmpeg / ffprobe：安装后加入 PATH，高清画面与音轨合并、MP3 提取需要 FFmpeg。
3. Deno：较新的 yt-dlp 需要外部 JavaScript Runtime 才能完整支持 YouTube，推荐 Deno；官方 yt-dlp.exe 已包含 EJS 组件。若以 Python 包安装，请使用 yt-dlp[default]。
4. 网络：确保设备可以访问 YouTube。如确实需要代理，在界面中填写本机有效的代理地址，比如 http://127.0.0.1:7890。

进入界面后，每行粘贴一个地址 → 选择模式 → 添加到队列 → 开始下载队列。

## 下载模式

| 模式 | 输入示例 | 说明 |
| --- | --- | --- |
| 单个视频 | https://www.youtube.com/watch?v=VIDEO_ID | 只下载这个视频，即使 URL 中还包含播放列表参数 |
| 播放列表 / 系列 | https://www.youtube.com/playlist?list=PLAYLIST_ID | 下载列表所有可访问视频，并按系列与序号创建目录 |
| 作者频道全部 | https://www.youtube.com/@CHANNEL_HANDLE | 按 yt-dlp 提取逻辑下载频道所有可访问上传，不人为限制总数 |

如只需作者的一个标签页，可输入 https://www.youtube.com/@CHANNEL_HANDLE/videos、/shorts、/streams，仍选频道模式。频道全部不保证涵盖会员、私人、地区限制、已删除或平台不允许获取的视频。

## 中断续传 / 去重 / 任务队列

- 下载默认串行进行，减少大量频道视频同时下载时的资源与连接压力。
- 当前视频进度条只反映**正在下载的这一条视频**，不是整个频道的全局完成百分比。
- 不限制频道总视频条数；频道如果包含数千条视频，需要相应的存储空间与时间。
- 使用 yt-dlp 的断点续传；已成功视频写入保存目录的 .yt-dlp-archives/，文件名按来源链接分别保存。
- 重新添加同一个频道 / 播放列表链接，会跳过对应下载归档已记录的成功视频，继续尝试其余内容。
- 更改同一来源链接的画质时，归档中成功视频仍会跳过。若要重新下载不同画质，请更换保存目录或备份后删除该来源的归档文件。
- 有些不再可用的视频会被跳过，日志中保留错误。批量任务状态显示“已完成（检查跳过项）”不代表所有视频都一定成功。
- “停止当前任务”仅停止当前子进程；“停止整个队列”会保留未开始任务，可以再次启动。

## 下载选项

- 画质：最佳、最高 1080p、最高 720p、MP3 音频。限制分辨率时不偷偷放宽画质上限。
- 中文字幕 / 英文字幕：可选下载官方或自动字幕，保留为独立文件。
- Cookies：默认不使用，可选择 Chrome、Edge 或 Firefox 在拥有访问权限的前提下处理需登录内容；工具仅保存浏览器类型，不保存 Cookies 内容。
- 代理：默认不设置，不会主动改变系统代理设置。
- 输出：单视频按名称和视频 ID；列表按标题与序号；频道按作者与日期分类。

设置会保存到 %LOCALAPPDATA%\yt-dlp-desktop\settings.json（Windows），其他系统使用 ~/.config/yt-dlp-desktop/settings.json。

## 离线单元测试

从仓库根目录运行：

    py -3 -m unittest test.test_youtube_downloader_gui -v

单元测试验证地址模式、参数生成、归档路径、进度行解析，不需要 YouTube 网络连接。真实视频、系列、频道端到端下载仍须在联网且已安装依赖的设备上进行验证。

## 使用边界

只下载你有权保存的内容，遵守版权法律和 YouTube 服务条款。本工具不会尝试绕过 DRM 或突破原本无权访问的内容。
