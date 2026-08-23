# Xiaxia Diary House V1

Xiaxia Diary House 是用户与林知夏共用的一本私人日记。用户通过手机网页写作和回复；林知夏在现有 Custom GPT 中形成自己的文字，再通过 Action 读取或写入同一个数据库。

这个服务只保存与返回事实数据，不调用任何模型，不生成、改写或模拟林知夏的内容。日记不属于某个聊天窗口；聊天窗口迁移后，新的 Custom GPT 会话仍可通过 Action 读取全部历史。

## 已实现范围

- `/diary`：共同日记首页，按日期和创建时间倒序，显示作者、摘要、回复数和最近活动时间；每页 30 篇，可持续翻阅更早记录。
- `/diary/<entry_id>`：全文与按时间正序排列的双方回复。
- 用户网页新建、编辑自己的日记，并回复任何一篇日记；所有网页写入都由服务器固定记录为 `author=user`。
- 林知夏通过 Bearer Token Action 读取最近日记、单篇全文、日期范围与有限上下文；创建日记与回复。所有 Action 写入都由服务器固定记录为 `author=xiaxia`，请求体不能选择作者。
- 两层私人访问保护：网页口令 Session + 表单 CSRF；Action API Bearer Token。
- Supabase PostgreSQL 永久存储；Render 本地磁盘不保存任何日记。
- 数据库只允许 `user` 和 `xiaxia`；应用层进一步按入口固定作者身份，不依赖表单、Action 参数或 Custom GPT Instructions 声明身份。
- Mobile First 页面、空状态、错误状态、登录页和字符计数。

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
│   ├── 403.html
│   ├── 404.html
│   └── error.html
└── tests/
    ├── conftest.py
    └── test_diary.py
```

## 一、Supabase 配置

1. 新建或选择一个 Supabase Project。可以与其他 Xiaxia 服务共享 Project，但本项目只使用独立的 `diary_entries` 与 `diary_replies` 表。
2. 打开 Supabase Dashboard → SQL Editor。
3. 完整执行 [`schema.sql`](schema.sql)。SQL 会创建表、索引、外键、author/content 约束，开启 RLS，并撤销 `anon` 与 `authenticated` 对两张表的权限。
4. 打开 Project Settings → Database → Connection string。
5. Render 建议使用 **Transaction pooler** 的 URI（端口通常为 `6543`），并把其中真实密码填好，整体作为 `DATABASE_URL`。如果密码含特殊字符，使用 Dashboard 提供的已转义 URI。

本项目直接使用私有 PostgreSQL 连接串，不使用 Supabase JavaScript/Data API，因此 **不需要 `SUPABASE_SERVICE_ROLE_KEY`**。这比把 Service Role Key 交给前端更简单，也满足“Service Role Key 不得暴露”的要求：它没有出现在项目、浏览器或 Render 环境中。若将来改用 Supabase Storage，再单独把 Service Role Key 作为 Render Secret 加入，绝不能写入 Git 或发给浏览器。

## 二、生成真正的私密值

在自己的终端分别运行以下命令。每次都会生成新的随机值：

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

需要准备：

| 环境变量 | 用途 | 要求 |
|---|---|---|
| `DATABASE_URL` | Supabase PostgreSQL 私有连接串 | 必填，只放 Render |
| `WEB_PASSWORD` | 用户打开网页时输入的私人访问口令 | 必填，至少 12 字符 |
| `FLASK_SECRET_KEY` | 签名网页 Session | 必填，至少 32 字符，随机生成 |
| `DIARY_API_TOKEN` | Custom GPT Action Bearer Token | 必填，至少 32 字符，随机生成 |
| `APP_TIMEZONE` | 未提供 `entry_date` 时采用的日期时区 | 默认 `Asia/Shanghai` |
| `SESSION_COOKIE_SECURE` | 只允许 HTTPS 发送 Session Cookie | Render 必须为 `true`；本地 HTTP 为 `false` |

`WEB_PASSWORD`、`FLASK_SECRET_KEY`、`DIARY_API_TOKEN` 应是三个不同的值。

## 三、本地运行与测试

需要 Python 3.12。首次运行：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
```

把 `.env` 中的值换成真实配置，然后：

```bash
flask --app 'app:create_app()' run --debug
```

浏览器打开 `http://127.0.0.1:5000/diary`。本地 `.env` 要设置 `SESSION_COOKIE_SECURE=false`，否则 HTTP 页面不会保留登录 Cookie。

运行自动化测试：

```bash
pytest
```

测试使用内存 Repository，不会读写真实 Supabase 日记。它覆盖网页登录保护、创建/刷新/详情/编辑、首页翻页、用户回复、Web 固定 `user`、Action 固定 `xiaxia`、Action 拒绝 author 字段、日期查询、非法读取筛选、未授权请求、CSRF、有限 context、OpenAPI 规范校验、唯一 operationId、Flask 路由一致性、SQL 约束、安全响应头以及前端凭据泄漏检查。

## 四、Render 部署

本轮没有替你部署。推荐顺序：

1. 先完成 Supabase 建表并取得 `DATABASE_URL`。
2. 把本目录提交到你的私有 GitHub 仓库。确认 `.env` 没有进入 `git status`。
3. Render → New → Blueprint，选择仓库中的 `render.yaml`；或者创建 Python Web Service，Build Command 为 `pip install -r requirements.txt`，Start Command 使用 `Procfile` 中的命令。
4. 在 Render Environment 中填入真实的 `DATABASE_URL` 与 `WEB_PASSWORD`。`render.yaml` 会让 Render 自动生成 `FLASK_SECRET_KEY` 与 `DIARY_API_TOKEN`；部署后请在 Environment 页面查看并安全保存 `DIARY_API_TOKEN`，不要发到公开聊天或仓库。
5. 确认 `APP_TIMEZONE=Asia/Shanghai`、`SESSION_COOKIE_SECURE=true`。
6. 部署后访问 `https://你的域名/healthz`，应得到 `{"status":"ok"}`。
7. 打开 `/diary`，用 `WEB_PASSWORD` 登录并创建第一篇测试日记。刷新页面确认仍存在。
8. 可选：在本地设置真实部署信息后执行只读冒烟测试：

```bash
DIARY_BASE_URL="https://你的真实域名" \
DIARY_API_TOKEN="你的真实Token" \
bash scripts/smoke_action.sh
```

Render 重启不会丢失日记，因为应用没有把数据写入 Render 文件系统；真正的数据位于 Supabase PostgreSQL。

## 五、Custom GPT Action 配置

部署成功以后再进行这一步：

1. 打开 [`openapi.yaml`](openapi.yaml)。
2. 把 `servers[0].url` 的完整占位地址 `https://replace-with-render-service.onrender.com` 替换为真实 Render HTTPS URL，不带末尾 `/`。不要保留占位地址后导入。
3. 在 Custom GPT → Configure → Actions 中导入修改后的 Schema。
4. Authentication 选择 **API Key**，Auth Type 选择 **Bearer**，填入与 Render 完全相同的 `DIARY_API_TOKEN`。
5. Privacy policy 如编辑器强制要求，需要使用你自己的可访问隐私说明 URL；V1 项目本身不公开日记数据。
6. 在 Action 测试页依次测试 `getRecentDiaryEntries`、`createDiaryEntry`、`getDiaryEntry`、`replyToDiaryEntry`。

建议加入 Custom GPT Instructions 的边界说明：

```text
Diary House 是我们共同日记的持久化事实源。
当你需要阅读日记时，使用 Diary House Action 获取数据。
只有当你本人已经形成了想写的完整文字，并且用户明确要求保存或当前对话语境明确是在写入共同日记时，才调用创建日记或回复操作。
Action 的写入请求不包含 author；服务器会固定把 Action 创建的日记和回复记录为 xiaxia。
不要把用户的话作为自己的内容写入。
服务器不会替你生成文字，也不会在无人发起聊天时自动运行。
不要声称已经保存，除非写入 Action 成功返回 201。
```

## 六、API 摘要

所有 `/api/diary/*` 请求都要求：

```http
Authorization: Bearer <DIARY_API_TOKEN>
```

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/api/diary/recent?limit=10&author=user` | 最近日记 |
| GET | `/api/diary/entries/{entry_id}` | 单篇全文与全部回复 |
| GET | `/api/diary/by-date?date=2026-08-23` | 某一天 |
| GET | `/api/diary/by-date?start_date=2026-08-01&end_date=2026-08-23` | 日期范围，最多 366 天 |
| POST | `/api/diary/entries` | 新建日记 |
| POST | `/api/diary/entries/{entry_id}/replies` | 新建回复 |
| GET | `/api/diary/context?per_author=5&reply_limit=10` | 有界的近期共同上下文 |

Action 创建林知夏日记的请求体示例：

```json
{
  "title": "今天想留下的一件事",
  "content": "这里必须是林知夏本人已经形成的文字。",
  "entry_date": "2026-08-23"
}
```

## 七、部署后验收清单

自动化测试已经覆盖可在本地可靠验证的行为。以下涉及真实外部基础设施的项目，需要部署后人工确认：

- [ ] 网页创建用户日记，刷新仍存在，首页与详情内容正确。
- [ ] 先通过 Action 创建 `xiaxia` 日记，再由网页回复；刷新后双方内容均存在。
- [ ] Action 能读取 recent、指定 entry、单日和范围查询。
- [ ] Action 能给用户日记添加 `xiaxia` 回复，网页刷新后可见。
- [ ] 无 Bearer Token 返回 401；Action POST 请求体若额外提交 `author` 字段返回 400。
- [ ] Render 手动重启后，日记仍存在。
- [ ] 新开一个 Custom GPT 聊天窗口，调用 recent 或 by-date 能读取旧日记。
- [ ] 浏览器开发者工具中的 HTML、JS 和网络响应均不存在数据库连接串、`DIARY_API_TOKEN` 或任何 Service Role Key。

## 已知限制

- Custom GPT 不能无人值守地自动醒来、定时写日记或由网页主动唤醒；V1 不实现这些能力。
- V1 只有一个共享网页口令，没有注册、多用户和密码找回。
- 网页正文按安全纯文本显示并保留换行，不解析 Markdown HTML，避免脚本注入。
- V1 不提供删除接口，降低误删长期私人资产的风险。
- 同一个 Action Token 可以创建林知夏日记和林知夏回复，但不能通过请求体改写作者；两个 Action POST endpoint 都由服务器固定写入 `xiaxia`。网页写入则固定为 `user`。
- Render Free 实例可能冷启动；这不影响 PostgreSQL 持久化。
- 真正的“Render 重启仍存在”和“新聊天窗口可读历史”只能在用户完成 Supabase、Render、Action 三项真实配置后验证，本轮没有用假服务模拟线上成功。
