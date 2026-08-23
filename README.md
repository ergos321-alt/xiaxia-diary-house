# Xiaxia Diary House V1.1

Xiaxia Diary House 是用户与林知夏长期共用的一本私人日记。用户通过手机网页写日记、在页边补字；林知夏在现有 Custom GPT 中形成自己的文字，再通过 Action 读取或写入同一个 Supabase PostgreSQL 数据库。

服务器只保存与返回双方明确写下的事实数据，不调用模型，不生成、改写或模拟林知夏的内容。日记不属于某个聊天窗口；换到新的 Custom GPT 会话后，仍可通过 Action 读取历史。

V1.1 是在已验收 V1 上的增量返修。第一轮加入翻旧日记、私人小标记、页边文字视觉和用户日记废纸篓；第二轮继续在同一代码上加入双人日历痕迹、作者浏览和同日关联。原有 Action 路径、行为、operationId 和身份边界全部保留。

## V1.1 已实现

- `/diary`：按日累积的共同时间线，使用 `🐶 我` / `🐱 林知夏` 自然区分作者；可在全部、我的、林知夏的日记之间切换。首页突出日记日期，不再突出保存时刻。
- `/diary/<entry_id>`：完整日记页；回复数据结构不变，前端改为依附本页、按真实时间正序生长的“页边文字”。如果另一方在同一天也写过，会出现自然的关联入口。
- `/diary/archive`：按月份或具体日期翻阅，并显示一个极简月历。日期格用两种小圆点分别表示用户和林知夏是否写过；双方都写过时同时显示两个痕迹。
- `/diary/on-this-day` 查看一年前同一天；首页只有在确实存在对应日记时才显示入口，不生成空缺内容。`/diary/random` 只从真实、未删除日记中随机翻一页。
- 私人 `🌿` 标记：双方各自只能在同一篇日记留下一个 `leaf` 标记，可取消；不是点赞，不做数量排名。
- 安全删除：用户只能把自己写的日记移入废纸篓，必须经过确认；可恢复，也可再次确认后彻底删除。林知夏没有删除 Action。
- 身份边界不变：所有 Web 创建、回复和标记均由服务器固定为 `author=user`；所有 Action 创建、回复和标记均由服务器固定为 `author=xiaxia`。Action 请求体没有 `author`。
- 原有读取能力不变：最近日记、单篇全文与回复、按日/日期范围、有界近期上下文。
- 网页口令 Session + CSRF，Action Bearer Token；日记始终存于 Supabase PostgreSQL，Render 本地磁盘不承载持久数据。

## 项目结构

```text
xiaxia-diary-house/
├── app.py
├── auth.py
├── database.py
├── diary.py
├── schema.sql
├── openapi.yaml
├── render.yaml
├── requirements.txt
├── requirements-dev.txt
├── Procfile
├── .env.example
├── .gitignore
├── pytest.ini
├── README.md
├── migrations/
│   └── 001_v1_1_marks_and_trash.sql
├── scripts/
│   └── smoke_action.sh
├── static/
│   ├── css/style.css
│   └── js/diary.js
├── templates/
│   ├── base.html
│   ├── login.html
│   ├── diary.html
│   ├── entry.html
│   ├── entry_form.html
│   ├── archive.html
│   ├── trash.html
│   ├── delete_confirm.html
│   ├── 403.html
│   ├── 404.html
│   └── error.html
└── tests/
    ├── conftest.py
    └── test_diary.py
```

## 数据库与部署升级

如果数据库仍是最初 V1，先备份，再执行第一轮已有 migration：

1. 在 Supabase Dashboard 确认 V1 数据正常，并按自己的备份策略保存数据库备份。
2. 打开 SQL Editor，完整执行 [`migrations/001_v1_1_marks_and_trash.sql`](migrations/001_v1_1_marks_and_trash.sql)。它只新增 `deleted_at`、`deleted_by`、`diary_marks` 与相关索引/RLS，不改写现有日记或回复。
3. 部署当前 V1.1 代码到现有 Render Service。
4. 访问 `/healthz`，再登录 `/diary` 验证时间线、日历、作者浏览、同日关联、标记和废纸篓。

如果第一轮 V1.1 migration 已经执行，本次第二轮增强**不需要再执行任何新 migration**。日历痕迹与同日关联直接从现有 `diary_entries.entry_date` 和 `author` 读取，不增加表或字段。

本次第二轮增强没有新增或修改 Action endpoint，`openapi.yaml` 与第一轮保持一致，因此**不需要重新导入 Custom GPT Action Schema**。部署后仍建议用原 Bearer Token 回归读取、创建、回复和标记操作。

本轮**不新增 Render 环境变量**。现有变量继续使用：

| 环境变量 | 用途 | 要求 |
|---|---|---|
| `DATABASE_URL` | Supabase PostgreSQL 私有连接串 | 必填，只放 Render |
| `WEB_PASSWORD` | 私人网页访问口令 | 必填，至少 12 字符 |
| `FLASK_SECRET_KEY` | 签名网页 Session | 必填，至少 32 字符 |
| `DIARY_API_TOKEN` | Custom GPT Action Bearer Token | 必填，至少 32 字符 |
| `APP_TIMEZONE` | 默认日记日期与“一年前今天”的时区 | 默认 `Asia/Shanghai` |
| `SESSION_COOKIE_SECURE` | 只允许 HTTPS 发送 Session Cookie | Render 为 `true`，本地 HTTP 为 `false` |

## 全新 Supabase 安装

只有全新安装才完整执行 [`schema.sql`](schema.sql)。从 V1 升级时执行 migration，不要把完整建表文件当作迁移脚本反复运行。

本项目使用私有 PostgreSQL `DATABASE_URL`，不通过浏览器访问 Supabase Data API，因此不需要 `SUPABASE_SERVICE_ROLE_KEY`。数据库连接串和所有密钥只放 Render Environment；不得写入 Git、HTML 或前端 JavaScript。

`schema.sql` 会创建逻辑隔离的三张表：

- `diary_entries`：日记与软删除状态。
- `diary_replies`：原 V1 回复结构，继续保存页边文字。
- `diary_marks`：作者、标记类型和时间；`unique(entry_id, author, mark_type)` 阻止同一作者重复留下同类标记。

三张表都启用 RLS，并撤销 `anon` / `authenticated` 的直接权限。外键使用 `on delete cascade`，仅在用户从废纸篓确认“彻底删除”时清理该日记依附的回复和标记。

## 本地运行与测试

需要 Python 3.12：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
flask --app 'app:create_app()' run --debug
```

本地 `.env` 应设置 `SESSION_COOKIE_SECURE=false`；真实值不要提交到 Git。

完整自动化测试命令：

```bash
python -m pytest -W error --cov=app --cov=auth --cov=database --cov=diary --cov-report=term-missing
```

测试使用内存 Repository，不会连接或改写真实 Supabase。覆盖原 V1 闭环、Web/Action 固定作者、月份/指定日期/一年前今天/随机页、作者浏览、日历双人痕迹、同日关联、双方标记幂等与取消、页边文字顺序、软删除隔离/恢复/彻底删除、Bearer/CSRF、OpenAPI 3.1 校验、唯一 operationId、Schema 与 Flask 路由一致性、SQL 约束和前端密钥泄漏检查。

## Render 部署说明

现有 Service 按上面的升级顺序发布。全新部署可使用 `render.yaml`，或手工配置：

- Build Command：`pip install -r requirements.txt`
- Start Command：`gunicorn "app:create_app()" --bind 0.0.0:$PORT --workers 2 --threads 4 --timeout 60 --access-logfile -`
- Health Check：`/healthz`

部署后先验证：

```bash
DIARY_BASE_URL="https://你的真实域名" \
DIARY_API_TOKEN="你的真实Token" \
bash scripts/smoke_action.sh
```

该脚本只验证原有 Action 读取连通性。Render 重启不会导致日记丢失，因为数据位于 Supabase PostgreSQL，不在 Render 本地磁盘。

## Custom GPT Action

`openapi.yaml` 使用 OpenAPI 3.1、单一静态 HTTPS server URL、无 server variables，也不使用 `nullable`。可空标题以保守的 `anyOf: [string, null]` 表示。所有 operationId 唯一，并由自动化测试与 Flask `/api/diary/*` 路由逐项核对。

仅在全新配置 Action，或第一轮 Schema 尚未导入时执行：

1. 将 `servers[0].url` 的完整占位地址 `https://replace-with-render-service.onrender.com` 替换为真实 Render HTTPS URL，不带末尾 `/`。
2. 在 Custom GPT → Configure → Actions 导入 Schema。
3. Authentication 选择 API Key / Bearer，填写与 Render 相同的 `DIARY_API_TOKEN`。
4. 先回归原六项 operationId，再测试新增的 `addDiaryMark` 与 `removeDiaryMark`。

原六项保持不变：

| operationId | 方法与路径 |
|---|---|
| `getRecentDiaryEntries` | `GET /api/diary/recent` |
| `getDiaryEntry` | `GET /api/diary/entries/{entry_id}` |
| `getDiaryEntriesByDate` | `GET /api/diary/by-date` |
| `createDiaryEntry` | `POST /api/diary/entries` |
| `replyToDiaryEntry` | `POST /api/diary/entries/{entry_id}/replies` |
| `getSharedDiaryContext` | `GET /api/diary/context` |

V1.1 新增两项：

| operationId | 方法与路径 | 身份边界 |
|---|---|---|
| `addDiaryMark` | `POST /api/diary/entries/{entry_id}/marks` | 服务器固定 `xiaxia` |
| `removeDiaryMark` | `DELETE /api/diary/entries/{entry_id}/marks/{mark_type}` | 只取消 `xiaxia` 自己的标记 |

添加标记请求体只有：

```json
{"mark_type": "leaf"}
```

请求体不接受 `author`；若额外提交会返回 400。Web 标记路由不读取作者字段，始终写 `user`。V1.1 没有任何 Action 删除日记的 endpoint。

建议保留以下 Instructions 边界：

```text
Diary House 是我们共同日记的持久化事实源。
读取时使用 Diary House Action。只有林知夏本人已经形成完整文字，并且对话语境明确要求保存时，才调用创建日记或页边回复。
Action 的创建日记、回复、标记请求都不包含 author；服务器会固定记录为 xiaxia。
不要把用户的话当作林知夏的内容写入。服务器不会生成或改写文字，也不会在无人发起聊天时自动运行。
只有写入 Action 成功后，才说明已经保存。
不要尝试删除日记；V1.1 不提供删除 Action。
```

## API 摘要

所有 `/api/diary/*` 请求要求 `Authorization: Bearer <DIARY_API_TOKEN>`。

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/api/diary/recent` | 有界的最近日记 |
| GET | `/api/diary/entries/{entry_id}` | 单篇全文、全部回复与标记 |
| GET | `/api/diary/by-date` | 单日或不超过 366 天的范围 |
| GET | `/api/diary/context` | 双方近期日记与回复的有界上下文 |
| POST | `/api/diary/entries` | 创建林知夏日记，固定 `xiaxia` |
| POST | `/api/diary/entries/{entry_id}/replies` | 添加林知夏页边文字，固定 `xiaxia` |
| POST | `/api/diary/entries/{entry_id}/marks` | 添加林知夏 `leaf` 标记，幂等 |
| DELETE | `/api/diary/entries/{entry_id}/marks/leaf` | 取消林知夏自己的 `leaf` 标记 |

软删除的日记不会出现在普通 Web 列表、随机页、月份统计或任何 Action 读取结果中。恢复后原正文、回复和标记重新可见。

## 部署后人工验收

- [ ] 执行 migration 后，原有日记与回复仍完整可读。
- [ ] Web 创建与回复仍固定 `user`；Action 创建与回复仍固定 `xiaxia`。
- [ ] 月份、具体日期、一年前今天、随机页行为正确。
- [ ] 日历中用户、林知夏、双方同日记录分别显示正确痕迹。
- [ ] 全部日记、我的日记、林知夏的日记三个入口只展示对应内容。
- [ ] 双方同一天写过时，详情页显示对方日记入口；没有时保持安静。
- [ ] 双方各自的 🌿 标记可幂等添加并各自取消。
- [ ] 用户日记移入废纸篓后从时间线和 Action 隐藏，恢复后重新出现。
- [ ] 林知夏日记不能从 Web 删除；Action 中不存在日记删除操作。
- [ ] Render 重启后数据仍存在；新 Custom GPT 聊天窗口能读取历史。
- [ ] 浏览器 HTML、JS 和网络响应不存在数据库连接串、Bearer Token 或 Service Role Key。

## 已知限制

- Custom GPT 不能无人值守自动醒来、定时写日记、被网页唤醒或主动推送；V1.1 不实现这些能力。
- 只有一个共享网页口令，没有注册、多用户、公开分享或密码找回。
- 正文按安全纯文本显示并保留换行，不解析 Markdown HTML。
- “一年前的今天”只看上一自然年的对应日期；闰年 2 月 29 日在非闰年回看 2 月 28 日。
- 月份浏览最多返回 500 篇，单日最多 200 篇；Action 查询仍维持原有有界限制。
- 废纸篓不自动清理。彻底删除不可恢复，必须在废纸篓再次确认。
- 本项目没有替你执行 Supabase migration 或 Render 发布。第二轮本身没有新 migration，也不要求重新导入 Action Schema。
