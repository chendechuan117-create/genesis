# 📦 手把手教你上传 Genesis 到 GitHub

不用担心，我已经帮你把本地所有的代码都准备好了（打好包了）。你只需要做两件事：
1. 在网页上创建一个空仓库（作为目的地）
2. 在终端运行一条命令（把代码推过去）

---

### 第一步：在 GitHub 网页上创建仓库

1.  打开浏览器，登录 [github.com](https://github.com/login)。
2.  点击右上角的 **+** 号，选择 **"New repository"**（新建仓库）。
3.  **Repository name** (仓库名): 输入 `genesis`
4.  **Description** (描述): 可以写 "My self-evolving AI agent" (选填)
5.  **Public/Private**: 选择 **Public** (公开) 或 **Private** (私有) 都可以。
    *   *注意：如果选 Private，也是免费的。*
6.  **Initialize this repository with**: **千万不要勾选** 任何选项 (README, .gitignore, License 都不要选！因为本地我已经帮你生成好了)。
7.  点击最下方的绿色按钮 **"Create repository"**。

---

### 第二步：获取仓库地址

创建成功后，你会看到一个全是代码命令的页面。
找到 **"Quick setup"** 方框，点击 **HTTPS** 按钮，复制那个链接。
*   链接长这样：`https://github.com/你的用户名/genesis.git`

---

### 第三步：生成访问令牌 (如果你还没有)

GitHub 现在不支持用账号密码在终端登录了，你需要一个 "Token" (令牌)。

1.  点击右上角头像 -> **Settings** (设置)。
2.  左侧栏滑到底，点击 **Developer settings**。
3.  左侧选择 **Personal access tokens** -> **Tokens (classic)**。
4.  点击 **Generate new token** -> **Generate new token (classic)**。
5.  **Note**: 随便填，比如 "genesis_push"。
6.  **Expiration**: 选 "No expiration" (不过期) 或者 30天。
7.  **Select scopes**: **必须勾选 `repo`** (全选 repo 下面的子选项)。
8.  拉到底点击 **Generate token**。
9.  **复制这个以 `ghp_` 开头的长串字符**。这是你的专用密码，只显示一次！

---

### 第四步：在终端上传代码

回到 VS Code 的终端 (Terminal)，确保你在 `~/Genesis/nanogenesis` 目录下（你应该已经在可以通过输入 `pwd` 确认）。

输入以下命令（把地址换成你第二步复制的地址）：

```bash
# 1. 关联远程仓库 (替换 URL)
git remote add origin https://github.com/你的用户名/genesis.git

# 2. 推送代码
git push -u origin main
```

**此时终端会让你输入用户名和密码：**
- **Username**: 输入你的 GitHub 用户名 (例如 `chendechusn`)
- **Password**: **粘贴你第三步生成的 Token (`ghp_...`)**
  *   *注意：粘贴密码时，屏幕上不会显示任何星号或字符，这是正常的。粘贴后直接回车。*

---

### 🎉 成功！
如果看到类似 `Branch 'main' set up to track remote branch 'main'` 的提示，说明上传成功了！
刷新 GitHub 网页，你应该能看到所有代码文件。
