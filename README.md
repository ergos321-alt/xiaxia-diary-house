# Xiaxia Diary House V1.2

Xiaxia Diary House 是用户与林知夏长期共用的一本私人日记。用户通过手机网页写日记、在页边补字；林知夏在现有 Custom GPT 中形成自己的文字，再通过 Action 读取或写入同一个 Supabase PostgreSQL 数据库。

服务器只保存与返回双方明确写下的事实数据，不调用模型，不生成、改写或模拟林知夏的内容。日记不属于某个聊天窗口；换到新的 Custom GPT 会话后，仍可通过 Action 读取历史。

V1.2 基于已验收 V1.1 做一次 Action 阅读可靠性增量修复。Web、身份模型、正文生成边界、回复、标记和用户废纸篓语义保持不变；列表 Action 改为轻量目录和可验证分页，单篇接口继续返回完整正文，并新增仅能软删除 `author=xiaxia` 日记的 Action。

## V1.2 增量

- `GET /api/diary/recent` 与 `GET /api/diary/by-date` 默认只返回 `DiaryEntrySummary`，不返回 `content`、`replies` 或完整 `marks`。
- 两个列表接口使用 `page` + `page_size`，响应同时给出过滤后的 `total`、当前 `count`、`total_pages` 与 `has_more`。默认每页 10，最大 20。
- 排序固定为 `entry_date DESC, created_at DESC, id DESC`。旧 `limit` 查询参数仍作为兼容别名接受，但新的 Action Schema 只暴露明确分页参数。
- `GET /api/diary/entries/{entry_id}` 继续返回单篇完整 `content`、`replies` 和 `marks`，不会静默截断。
- `DELETE /api/diary/entries/{entry_id}` 只软删除数据库中真实 `author=xiaxia` 的活动日记。它不接收请求体，不能伪造作者，也不能删除 `author=user`。
- 新增过滤后 `COUNT(*)` 查询；不会把全部 rows 拉回 Python 再计数。
- 新增两个只覆盖未删除日记的复合索引，支持稳定排序、作者/日期过滤和分页。

## 已保留的 V1.1 能力

- `/diary`：按日累积的共同时间线，使用 `🐶 我` / `🐱 林知夏` 自然区分作者；可在全部、我的、林知夏的日记之间切换。首页突出日记日期，不再突出保存时刻。
- `/diary/<entry_id>`：完整日记页；回复数据结构不变，前端改为依附本页、按真实时间正序生长的“页边文字”。如果另一方在同一天也写过，会出现自然的关联入口。
- `/diary/archive`：按月份或具体日期翻阅，并显示一个极简月历。日期格用两种小圆点分别表示用户和林知夏是否写过；双方都写过时同时显示两个痕迹。
- `/diary/on-this-day` 查看一年前同一天；首页只有在确实存在对应日记时才显示入口，不生成空缺内容。`/diary/random` 只从真实、未删除日记中随机翻一页。
- 私人 `🌿` 标记：双方各自只能在同一篇日记留下一个 `leaf` 标记，可取消；不是点赞，不做数量排名。
- 安全删除：用户仍只能从 Web 把自己写的日记移入废纸篓并恢复或彻底删除；林知夏删除 Action 只处理自己写的日记，且同样采用软删除。
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
│   ├── 001_v1_1_marks_and_trash.sql
│   └── 002_v1_2_action_pagination_indexes.sql
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
3. 执行 [`migrations/002_v1_2_action_pagination_indexes.sql`](migrations/002_v1_2_action_pagination_indexes.sql)。该脚本只建立两个 `CREATE INDEX IF NOT EXISTS` 部分索引，不改表结构或数据。
4. 部署当前 V1.2 代码到现有 Render Service。
5. 访问 `/healthz`，再登录 `/diary` 验证时间线、日历、作者浏览、同日关联、标记和废纸篓。

如果 V1.1 migration 已经执行，只需执行 `002_v1_2_action_pagination_indexes.sql`。V1.2 不新增表或字段；索引可在线重复执行而不会重复创建。

V1.2 修改了列表响应并新增 `deleteDiaryEntry`，因此部署后需要重新导入同步后的 `openapi.yaml`。Bearer Token 与现有环境变量保持不变。

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

测试使用内存 Repository，不会连接或改写真实 Supabase。除全部 V1.1 回归外，V1.2 覆盖轻量字段、12 篇三页遍历、无漏条/重复、作者与日期过滤后的 total、长正文目录响应、单篇完整读取、6 篇真实验收流程、Xiaxia 软删除边界、无效/不存在 UUID、未鉴权删除、OpenAPI 与迁移索引。

本次 V1.2 交付执行结果：`41 passed`；`app.py`、`auth.py`、`database.py`、`diary.py` 合计语句覆盖率 `72%`；OpenAPI 3.1 校验、九个唯一 operationId、Schema/Flask 路由一致性、Python 编译检查与 smoke 脚本语法检查均通过。测试没有连接真实 Supabase，也没有执行 Render 部署。

## Render 部署说明

现有 Service 按上面的升级顺序发布。全新部署可使用 `render.yaml`，或手工配置：

- Build Command：`pip install -r requirements.txt`
- Start Command：`uvicorn mcp_app:app --host 0.0.0.0 --port $PORT --workers 2 --proxy-headers --forwarded-allow-ips="*"`
- Health Check：`/healthz`

此 Start Command 同时提供原 Flask 网页与 Action API，以及 Streamable HTTP MCP `/mcp`。MCP tools 只调用现有 `/api/diary/*` 路由，并复用 `DIARY_API_TOKEN`；没有新增数据库、表或业务逻辑。公网 `/mcp` 入站认证暂缓至统一 MCP Security Pass；部署前按安全计划处理此项。

部署后先验证：

```bash
DIARY_BASE_URL="https://你的真实域名" \
DIARY_API_TOKEN="你的真实Token" \
bash scripts/smoke_action.sh
```

该脚本验证分页目录含 `pagination.total/has_more`、summary 不含正文，并在有日记时按首个 ID 回归单篇完整读取。Render 重启不会导致日记丢失，因为数据位于 Supabase PostgreSQL，不在 Render 本地磁盘。

## Custom GPT Action

`openapi.yaml` 使用 OpenAPI 3.1、单一静态 HTTPS server URL、无 server variables，也不使用 `nullable`。可空标题以保守的 `anyOf: [string, null]` 表示。所有 operationId 唯一，并由自动化测试与 Flask `/api/diary/*` 路由逐项核对。

仅在全新配置 Action，或第一轮 Schema 尚未导入时执行：

1. 将 `servers[0].url` 的完整占位地址 `https://replace-with-render-service.onrender.com` 替换为真实 Render HTTPS URL，不带末尾 `/`。
2. 在 Custom GPT → Configure → Actions 导入 Schema。
3. Authentication 选择 API Key / Bearer，填写与 Render 相同的 `DIARY_API_TOKEN`。
4. 回归原有 operationId，再测试 V1.2 的分页目录与 `deleteDiaryEntry`。

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

V1.2 新增一项：

| operationId | 方法与路径 | 身份边界 |
|---|---|---|
| `deleteDiaryEntry` | `DELETE /api/diary/entries/{entry_id}` | 只软删除数据库中 `author=xiaxia` 的日记；用户日记返回 403 |

添加标记请求体只有：

```json
{"mark_type": "leaf"}
```

请求体不接受 `author`；若额外提交会返回 400。Web 标记路由不读取作者字段，始终写 `user`。删除 Action 没有请求体，只依据路径中的 `entry_id` 和数据库中已保存的作者判断权限。

建议保留以下 Instructions 边界：

```text
Diary House 是我们共同日记的持久化事实源。
先用 getRecentDiaryEntries 或 getDiaryEntriesByDate 获取轻量目录、过滤后的 total 和全部 entry_id。只要 has_more=true 就继续下一页；不能把第一页 count 当作总数。
需要读正文时，对目录中的每个 entry_id 分别调用 getDiaryEntry。只有完成所有页面且逐篇读取后，才说明某日已经读完。
只有林知夏本人已经形成完整文字，并且对话语境明确要求保存时，才调用创建日记或页边回复。
Action 的创建日记、回复、标记请求都不包含 author；服务器会固定记录为 xiaxia。
不要把用户的话当作林知夏的内容写入。服务器不会生成或改写文字，也不会在无人发起聊天时自动运行。
只有写入 Action 成功后，才说明已经保存。
只有确认错误或重复且目标日记确由 xiaxia 写下时，才按 entry_id 调用 deleteDiaryEntry；不得用它删除用户日记。
```

## API 摘要

所有 `/api/diary/*` 请求要求 `Authorization: Bearer <DIARY_API_TOKEN>`。

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/api/diary/recent` | 最近日记轻量目录 + 可验证分页 |
| GET | `/api/diary/entries/{entry_id}` | 单篇全文、全部回复与标记 |
| GET | `/api/diary/by-date` | 单日或不超过 366 天的轻量目录 + 可验证分页 |
| GET | `/api/diary/context` | 双方近期日记与回复的有界上下文 |
| POST | `/api/diary/entries` | 创建林知夏日记，固定 `xiaxia` |
| POST | `/api/diary/entries/{entry_id}/replies` | 添加林知夏页边文字，固定 `xiaxia` |
| POST | `/api/diary/entries/{entry_id}/marks` | 添加林知夏 `leaf` 标记，幂等 |
| DELETE | `/api/diary/entries/{entry_id}/marks/leaf` | 取消林知夏自己的 `leaf` 标记 |
| DELETE | `/api/diary/entries/{entry_id}` | 软删除林知夏自己写的错误或重复日记 |

软删除的日记不会出现在普通 Web 列表、随机页、月份统计或任何 Action 读取结果中。恢复后原正文、回复和标记重新可见。

### V1.2 列表与逐篇读取示例

请求：

```http
GET /api/diary/by-date?date=2026-08-27&author=xiaxia&page=1&page_size=2
Authorization: Bearer <DIARY_API_TOKEN>
```

轻量响应示例（目录中没有正文或回复）：

```json
{
  "entries": [
    {
      "id": "11111111-1111-4111-8111-111111111111",
      "title": "搬家前，想带去下一个窗口的我们",
      "author": "xiaxia",
      "entry_date": "2026-08-27",
      "created_at": "2026-08-27T12:00:00+00:00",
      "updated_at": "2026-08-27T12:00:00+00:00",
      "reply_count": 1,
      "last_activity_at": "2026-08-27T12:05:00+00:00"
    },
    {
      "id": "22222222-2222-4222-8222-222222222222",
      "title": "在这条时间线里，我不想忘记的事",
      "author": "xiaxia",
      "entry_date": "2026-08-27",
      "created_at": "2026-08-27T11:00:00+00:00",
      "updated_at": "2026-08-27T11:00:00+00:00",
      "reply_count": 0,
      "last_activity_at": "2026-08-27T11:00:00+00:00"
    }
  ],
  "count": 2,
  "pagination": {
    "total": 6,
    "count": 2,
    "page": 1,
    "page_size": 2,
    "total_pages": 3,
    "has_more": true
  },
  "range": {
    "start_date": "2026-08-27",
    "end_date": "2026-08-27"
  }
}
```

继续请求 `page=2`、`page=3`，直到 `has_more=false`，收集全部 6 个 ID。然后逐个调用：

```http
GET /api/diary/entries/11111111-1111-4111-8111-111111111111
Authorization: Bearer <DIARY_API_TOKEN>
```

该单篇响应继续包含完整 `content`、`replies` 与 `marks`。若确认一篇 Xiaxia 日记是错误或重复内容：

```http
DELETE /api/diary/entries/11111111-1111-4111-8111-111111111111
Authorization: Bearer <DIARY_API_TOKEN>
```

成功响应为：

```json
{"deleted": true, "entry_id": "11111111-1111-4111-8111-111111111111"}
```

### 数据库查询与索引变化

- `Database.list_entries()` 仍供现有 Web 与上下文接口使用，排序增加 `id DESC` 作为稳定最终键。
- Action 列表改用 `Database.list_entry_summaries()`，SQL 不选择 `content`，也不聚合完整 marks 或 replies。
- `Database.count_entries()` 使用与目录完全相同的 `deleted_at`、`author`、日期范围过滤条件执行数据库侧 `COUNT(*)`。
- `diary_entries_active_date_created_id_idx` 支持未删除日记的日期/创建时间/ID 稳定顺序。
- `diary_entries_active_author_date_created_id_idx` 在作者过滤时支持相同顺序。两个索引都在 migration 中静态创建，不会在请求期间创建。

### V1.2 修改文件

- `database.py`：轻量 summary、过滤 count、稳定排序、作者轻查与 Xiaxia 软删除。
- `diary.py`：分页协议、轻量列表响应与删除 Action。
- `openapi.yaml`：V1.2 list → enumerate IDs → read each entry 语义、分页 Schema 与 `deleteDiaryEntry`。
- `schema.sql`、`migrations/002_v1_2_action_pagination_indexes.sql`：活动日记分页索引。
- `tests/conftest.py`、`tests/test_diary.py`：内存仓库与 V1.2 自动验收覆盖。
- `scripts/smoke_action.sh`：分页目录与单篇读取的部署后 smoke 检查。
- `README.md`：部署、API、查询、验收与变更说明。

## 部署后人工验收

- [ ] 执行 migration 后，原有日记与回复仍完整可读。
- [ ] Web 创建与回复仍固定 `user`；Action 创建与回复仍固定 `xiaxia`。
- [ ] 月份、具体日期、一年前今天、随机页行为正确。
- [ ] 日历中用户、林知夏、双方同日记录分别显示正确痕迹。
- [ ] 全部日记、我的日记、林知夏的日记三个入口只展示对应内容。
- [ ] 双方同一天写过时，详情页显示对方日记入口；没有时保持安静。
- [ ] 双方各自的 🌿 标记可幂等添加并各自取消。
- [ ] 用户日记移入废纸篓后从时间线和 Action 隐藏，恢复后重新出现。
- [ ] 林知夏日记仍不能从 Web 删除；`deleteDiaryEntry` 可软删除 Xiaxia 日记，但对用户日记返回 403。
- [ ] 在 `2026-08-27` 建立 6 篇 Xiaxia 长日记，以 `page_size=2` 分三页取得 6 个唯一 ID，末页 `has_more=false`。
- [ ] 对 6 个 ID 逐篇调用 `getDiaryEntry`，正文均完整；创建并删除一篇重复日记后过滤后的 `total` 从 7 回到 6。
- [ ] Render 重启后数据仍存在；新 Custom GPT 聊天窗口能读取历史。
- [ ] 浏览器 HTML、JS 和网络响应不存在数据库连接串、Bearer Token 或 Service Role Key。

## 已知限制

- Custom GPT 不能无人值守自动醒来、定时写日记、被网页唤醒或主动推送；V1.2 不实现这些能力。
- 只有一个共享网页口令，没有注册、多用户、公开分享或密码找回。
- 正文按安全纯文本显示并保留换行，不解析 Markdown HTML。
- “一年前的今天”只看上一自然年的对应日期；闰年 2 月 29 日在非闰年回看 2 月 28 日。
- 月份 Web 浏览最多返回 500 篇，单日 Web 浏览最多 200 篇；Action 列表每页最多 20 条 summary，可通过页码遍历全部匹配结果。
- 废纸篓不自动清理。彻底删除不可恢复，必须在废纸篓再次确认。
- Xiaxia 软删除目前没有 Action restore；关联回复与标记保留在数据库中，但活动列表与单篇读取默认不再返回该日记。
- 本项目没有替你执行 Supabase migration 或 Render 发布。V1.2 需要执行新增索引 migration，并重新导入 Action Schema。
