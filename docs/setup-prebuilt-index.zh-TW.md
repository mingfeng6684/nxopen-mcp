# 使用現成索引串接 nxopen-mcp 完整指南

> 適用情境:你拿到了一份同事建好的 `index.db`(約 500 MB),想在自己的
> 電腦上讓 Claude Code / Codex / Cursor 查詢 NXOpen API,**不需要**自己
> 花數小時建索引。
>
> ⚠️ 授權提醒:索引內含 Siemens API 文件內容,僅限**組織內有 NX 授權**
> 的人員使用,請勿外流或公開散布。

---

## 0. 你需要準備的東西

| 項目 | 說明 |
|------|------|
| Windows 電腦 | macOS/Linux 也可,路徑自行對應 |
| Python 3.11 或更新 | 檢查:`python --version`;沒有就到 https://www.python.org/downloads/ 安裝,**安裝時勾選 "Add python.exe to PATH"** |
| 磁碟空間約 3 GB | 索引 0.5 GB + BGE-M3 模型 2 GB(首次語意查詢自動下載) |
| `index.db` 檔案 | 同事給你的,約 500 MB |
| Claude Code(或 Codex / Cursor) | 任一支援 MCP 的 AI 編碼工具 |

---

## 1. 安裝 nxopen-mcp

開啟「命令提示字元」或 PowerShell:

```bash
pip install "nxopen-mcp[embed]"
```

- 用現成索引**不需要** `[reflect]`(繼承鏈已包含在索引中)
- `[embed]` 是語意搜尋必需的;安裝內容含 PyTorch,會下載一陣子

安裝完驗證:

```bash
nxopen-mcp --help
```

看到 `index` / `serve` 兩個指令即成功。若顯示「不是內部或外部命令」,
表示 Python 的 Scripts 目錄不在 PATH——最快的解法是改用完整路徑,
先找出位置:

```bash
python -c "import sysconfig; print(sysconfig.get_path('scripts'))"
```

之後所有指令中的 `nxopen-mcp` 都改成 `<那個路徑>\nxopen-mcp.exe`。

---

## 2. 放置索引檔

把拿到的 `index.db` 複製到預設位置:

```
C:\Users\<你的帳號>\.nxopen-mcp\index.db
```

`.nxopen-mcp` 資料夾不存在就自己建一個。用 PowerShell 一行完成:

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.nxopen-mcp" | Out-Null
Copy-Item "D:\下載\index.db" "$env:USERPROFILE\.nxopen-mcp\index.db"
```

> 不想放預設位置?也可以放任何地方,後面註冊時加
> `--db "D:\你的路徑\index.db"` 即可。

---

## 3. 註冊到 Claude Code

### 方法 A:CLI 一行(建議)

```bash
claude mcp add -s user nxopen -- nxopen-mcp serve
```

- `-s user`:所有專案都能用,不限單一資料夾
- 索引不在預設位置時:`claude mcp add -s user nxopen -- nxopen-mcp serve --db "D:\路徑\index.db"`

### 方法 B:找不到 `claude` 指令時,直接編設定檔

開啟 `C:\Users\<你的帳號>\.claude.json`,在最外層加入(或併入既有的)
`mcpServers` 區塊:

```json
{
  "mcpServers": {
    "nxopen": {
      "type": "stdio",
      "command": "nxopen-mcp",
      "args": ["serve"]
    }
  }
}
```

`nxopen-mcp` 不在 PATH 時,`command` 填完整路徑,例如
`C:\\Python312\\Scripts\\nxopen-mcp.exe`(JSON 中反斜線要寫兩個)。

---

## 4. 驗證串接

1. **開一個全新的 Claude Code session**(MCP 只在啟動時連線,舊視窗
   不會自動接上)
2. 輸入 `/mcp` → 應顯示 `nxopen ✓ connected`
3. 先測**精確查詢**(不需模型,應該秒回):

   > 用 nxopen 查 CavityMillingBuilder 有哪些成員

4. 再測**語意查詢**:

   > 用 nxopen 搜尋「如何設定主軸轉速」

   ⏳ **第一次語意查詢會停 1–3 分鐘**:先下載 BGE-M3 模型(約 2 GB,
   僅此一次),再載入記憶體。之後同一個 session 內都是秒回。
   **這不是當機,請不要中斷它。**

全部通過就完成了。之後正常使用即可,例如:

> 幫我寫一個建立鑽孔操作並設定進給率的 NXOpen C# 程式

Claude 會自動呼叫 nxopen 的工具查真實 API 再寫程式。

---

## 5. Codex / Cursor 串接(可選)

**Cursor**:在 `mcp.json`(專案 `.cursor/mcp.json` 或全域設定)加入與
上方方法 B 相同的 JSON 區塊。

**Codex CLI**:編輯 `~/.codex/config.toml`:

```toml
[mcp_servers.nxopen]
command = "nxopen-mcp"
args = ["serve"]
```

---

## 6. 疑難排解

| 症狀 | 原因與解法 |
|------|-----------|
| `/mcp` 顯示 not connected | 舊 session 不會自動連線 → 開新 session 或重啟工具 |
| `error: index not found at ...` | 索引不在預設位置 → 確認第 2 步的路徑,或註冊時加 `--db` |
| 第一次搜尋「卡住」幾分鐘 | 正常:一次性下載並載入 BGE-M3 模型,等它完成 |
| 模型下載失敗(公司網路) | 需要能連 huggingface.co;有 proxy 時先設 `HTTPS_PROXY` 環境變數 |
| `nxopen-mcp` 不是內部或外部命令 | Scripts 目錄不在 PATH → 見第 1 步,改用完整路徑 |
| 精確查詢很快、語意查詢每次都慢 | 正常設計:模型只在 server 存活期間常駐;重啟 session 後第一次語意查詢會重新載入(約 1 分鐘,不會重新下載) |
| 想確認索引內容 | 索引是 SQLite 檔,`members` 表約 9.8 萬筆即為完整 NX12 文件 |

---

## 7. 之後的維護

- **升級軟體**:`pip install -U "nxopen-mcp[embed]"`(索引不受影響)
- **換 NX 版本的索引**:拿到新的 `index.db` 直接覆蓋同一路徑即可,
  不用重新註冊
- **自己建索引**(有 NX 安裝時):見主 [README](../README.zh-TW.md)
  的「快速開始」

有問題請洽提供索引檔的同事,或到
https://github.com/mingfeng6684/nxopen-mcp/issues 回報。
