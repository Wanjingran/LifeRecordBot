# LifeRecordBot 安装说明

这是一个干净版生活助手机器人，不包含任何个人记录、API Key、Telegram Token 或历史数据。

## 你会得到什么

手机端：用 Telegram 给机器人发消息。
电脑端：电脑保持开机联网，运行 `bot.py`，负责调用 DeepSeek、记录数据、发送提醒。

支持能力包括：

- 消费 / 收入记录
- 今日、本周、本月、今年总结
- 月度 / 年度收支图
- 心情记录和趋势
- 天气查询
- 重要日期和提醒
- 今日任务 / 每日目标 / 待办
- 多模块语句捕捉，例如“早餐25，今天心情不错，帮我总结下今天”
- 删除、修改、最近记录查询
- 可选：截图 / 小票 OCR 记账

## 一、手机端准备 Telegram 机器人

1. 手机打开 Telegram。
2. 搜索 `@BotFather`，确认是 Telegram 官方 BotFather。
3. 发送 `/newbot`。
4. 按提示给机器人起名字，例如：`banana生活助手`。
5. 再给机器人设置 username，必须以 `bot` 结尾，例如：`banana_life_record_bot`。
6. BotFather 会给你一串 token，格式类似：

```text
<TELEGRAM_BOT_TOKEN_FROM_BOTFATHER>
```

这个就是 `telegram_bot_token`。

注意：不要把 Telegram 登录验证码发给任何人或任何机器人。BotFather 只给 bot token，不会要你的登录验证码。

## 二、准备 DeepSeek API Key

1. 打开 DeepSeek 开放平台。
2. 登录后进入 API keys。
3. 创建一个新的 API key。
4. 复制 key，格式通常以 `sk-` 开头。

这个就是 `deepseek_api_key`。

## 三、电脑端安装 Python

推荐安装 Python 3.11 或更新版本。

下载地址：

```text
https://www.python.org/downloads/windows/
```

安装时勾选：

```text
Add python.exe to PATH
```

安装好后，打开命令提示符或 PowerShell，输入：

```powershell
python --version
```

能看到版本号即可。

## 四、安装依赖

进入本目录，也就是 `LifeRecordBot-Release`，在地址栏输入 `cmd` 回车，或打开 PowerShell 后执行：

```powershell
cd Desktop\LifeRecordBot-Release
python -m pip install -r requirements.txt
```

说明：

- 基础聊天、记账、提醒主要使用 Python 标准库。
- `Pillow` 用于生成收支图。
- OCR 拍照记账需要额外安装 Tesseract，见后文可选项。

## 五、填写配置

1. 复制 `config.example.json`。
2. 重命名为 `config.json`。
3. 打开 `config.json`，填入你的 Telegram token 和 DeepSeek API key。

示例：

```json
{
  "telegram_bot_token": "这里填 BotFather 给你的 token",
  "deepseek_api_key": "这里填 DeepSeek API key",
  "deepseek_model": "deepseek-chat",
  "default_city": "深圳",
  "allowed_user_ids": [],
  "ocr_lang": "chi_sim+eng",
  "tesseract_cmd": ""
}
```

建议：

- `default_city` 改成你的常用城市。
- 先保持 `allowed_user_ids` 为空，测试成功后再考虑限制用户。

## 六、启动机器人

双击：

```text
start_bot.cmd
```

然后手机打开你创建的 Telegram 机器人，发送：

```text
/start
```

如果机器人回复，就说明成功。

如果窗口一闪而过，可以打开 `bot.log` 查看错误。

## 七、开机自启动

按 `Win + R`，输入：

```text
shell:startup
```

把 `start_bot_hidden.vbs` 放进打开的“启动”文件夹。

这样 Windows 登录后会自动后台启动机器人。

注意：如果你希望电脑还没登录 Windows 就启动，需要用“任务计划程序”创建开机任务；普通启动文件夹是在登录后启动。


## 八、如何像手机助手一样长期使用

这个机器人不是一个纯手机 App。它的工作方式是：

```text
手机 Telegram 发消息 -> Telegram 服务器 -> 你的电脑机器人程序 -> DeepSeek / 本地记录 -> 回复到手机
```

所以要想随时在手机上使用，必须满足三个条件：

1. 电脑开着。
2. 电脑能联网。
3. 机器人程序正在运行。

如果电脑关机、断网、睡眠，手机 Telegram 仍然能发消息，但机器人不会马上回复；等电脑重新启动并运行机器人后，才可能继续处理后续消息。

### 推荐的长期使用方式

最稳的方式是准备一台经常开着的 Windows 电脑，例如宿舍电脑、家里的台式机、迷你主机或旧笔记本。

建议：

- 台式机：可以长期插电开着，最适合当机器人主机。
- 笔记本：可以插电使用，但要设置合盖不睡眠、接通电源不睡眠。
- 不建议只靠手机运行这个项目，因为模型调用、记录文件、定时提醒都在电脑端完成。

### 设置电脑不自动睡眠

Windows 11 / Windows 10 大致步骤：

1. 打开 Windows 设置。
2. 进入 `系统`。
3. 进入 `电源和电池` 或 `电源和睡眠`。
4. 找到“屏幕和睡眠”。
5. 把“接通电源后，使设备进入睡眠状态”改成 `从不`。
6. 如果是笔记本，建议把“接通电源后关闭屏幕”设置成一个较短时间，例如 `10 分钟`，但“睡眠”保持 `从不`。

这样可以做到：屏幕可以黑掉省电，但电脑本身不睡眠，机器人还能继续工作。

### 笔记本合盖后继续运行

如果你用笔记本，并且想合上盖子后机器人仍然运行：

1. 打开控制面板。
2. 进入 `硬件和声音`。
3. 进入 `电源选项`。
4. 点击左侧 `选择关闭笔记本计算机盖的功能`。
5. 把“接通电源时，关闭盖子时”设置为 `不采取任何操作`。
6. 保存修改。

注意：笔记本长期合盖运行要注意散热，最好放在通风位置。

### 设置开机自动启动机器人

按 `Win + R`，输入：

```text
shell:startup
```

把 `start_bot_hidden.vbs` 放进打开的“启动”文件夹。

这样每次登录 Windows 后，机器人会在后台自动启动。

如果你只是把电脑开机但没有登录 Windows，启动文件夹不会运行。想做到“开机但未登录也运行”，需要使用 Windows 任务计划程序。

### 用任务计划程序实现开机运行（进阶）

1. 在开始菜单搜索 `任务计划程序`。
2. 点击右侧 `创建任务`，不要选“创建基本任务”。
3. `常规` 里填写名称，例如 `LifeRecordBot`。
4. 勾选 `不管用户是否登录都要运行`。
5. 勾选 `使用最高权限运行`。
6. `触发器` 里新建，选择 `启动时`。
7. `操作` 里新建：
   - 程序或脚本：选择本目录里的 `start_bot_hidden.vbs`
   - 起始于：填写本目录路径，例如 `C:\Users\你的用户名\Desktop\LifeRecordBot-Release`
8. 保存任务。

如果这一步觉得麻烦，可以先用启动文件夹方案，已经足够个人使用。

### 如何确认机器人还活着

手机 Telegram 里给机器人发：

```text
/start
```

或：

```text
今日任务
```

能回复就说明电脑端机器人正在运行。

如果不回复，按顺序检查：

1. 电脑有没有开机。
2. 电脑有没有联网。
3. 是否登录了 Windows。
4. 任务管理器里有没有 `python.exe`。
5. `bot.log` 里有没有错误。
6. 是否同时开了多个机器人实例，导致 409 conflict。

### 长期运行的小建议

- 不要同时双击很多次 `start_bot.cmd`，同一个 Telegram bot 只能有一个程序实例运行。
- 电脑重启后，等 1 到 2 分钟再测试机器人，给网络和启动脚本一点时间。
- 如果要出远门，确认电脑不会自动睡眠，电源和网络稳定。
- 如果电脑断电，机器人不会丢失已有记录；记录在 `records` 文件夹里。重新开机后继续使用即可。

## 九、手机怎么用

直接在 Telegram 发自然语言，例如：

```text
早餐25
工资到账3000
今天心情不错
明天天气如何
7月12日妈妈生日，提前3天提醒
提醒我明天上午九点考试
添加待办 明天交作业
今日任务
完成第二个代办
都完成了
给我看看今日总结
看一下本月收支图
删除第二条记录
/recent
```

多模块也可以一句话说：

```text
早餐25，今天心情不错，帮我总结下今天
```

机器人会尽量拆成多个动作执行。

## 十、可选：OCR 拍照记账

如果你想发小票、支付截图让机器人识别，需要安装 Tesseract OCR。

Windows 可搜索安装：

```text
Tesseract OCR Windows
```

安装后，把路径填入 `config.json`：

```json
"tesseract_cmd": "C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
```

中文识别需要安装 `chi_sim` 语言包。

## 十一、常见问题

### 机器人没反应

1. 确认电脑开机、联网。
2. 确认 `start_bot.cmd` 正在运行。
3. 查看 `bot.log`。
4. 确认同一个 bot 没有被多个程序同时运行，否则 Telegram 会报 409 conflict。

### 出现 409 conflict

说明同一个机器人启动了多个实例。

处理方法：

1. 关闭多余的命令行窗口。
2. 打开任务管理器，结束多余的 `python.exe`。
3. 只保留一个 `start_bot.cmd`。

### 天气不准或没有城市

在 `config.json` 设置：

```json
"default_city": "深圳"
```

也可以直接问：

```text
深圳明天天气如何
```

### 图表发不出来

先安装依赖：

```powershell
python -m pip install -r requirements.txt
```

### 不想让别人用我的机器人

可以后续把你的 Telegram user id 加到 `allowed_user_ids`。

先保持为空方便测试；上线给别人使用时再做权限限制。

## 十二、最终检查

你可以在电脑上运行：

```powershell
python route_regression_test.py
```

看到 `OK` 开头的输出，说明核心分流和记录功能通过回归测试。
