import re

path = '/workspace/genesis/skills/n8n_browser_automation.py'
with open(path, 'r', encoding='utf-8') as f:
    src = f.read()

# Fix _login_n8n: browser = None + inner try-finally
old_login = '''    async def _login_n8n(self, username: str, password: str) -> str:
        """登录n8n"""
        try:
            async with async_playwright() as p:
                # 启动浏览器，配置代理
                browser = await p.chromium.launch(
                    headless=False,
                    args=[
                        '--no-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-gpu',
                        f'--proxy-server=socks5://127.0.0.1:20170'
                    ]
                )
                
                context = await browser.new_context(
                    viewport={'width': 1280, 'height': 800},
                    proxy={
                        'server': 'socks5://127.0.0.1:20170'
                    }
                )
                
                page = await context.new_page()
                page.set_default_timeout(60000)
                
                # 访问n8n
                await page.goto('http://localhost:5679')
                
                # 等待页面加载
                await page.wait_for_load_state('networkidle')
                
                # 检查是否已经登录
                try:
                    await page.wait_for_selector('text=Workflows', timeout=5000)
                    return "已经登录到n8n"
                except:
                    pass
                
                # 查找登录表单
                await page.wait_for_selector('input[name="emailOrLdapLoginId"]', timeout=10000)
                
                # 输入用户名和密码
                await page.fill('input[name="emailOrLdapLoginId"]', username)
                await page.fill('input[name="password"]', password)
                
                # 点击登录按钮
                await page.click('button[type="submit"]')
                
                # 等待登录成功
                try:
                    await page.wait_for_selector('text=Workflows', timeout=15000)
                    # 截图保存
                    await page.screenshot(path='/tmp/n8n_login_success.png')
                    
                    # 获取cookies
                    cookies = await context.cookies()
                    cookies_json = json.dumps(cookies, indent=2)
                    
                    await browser.close()
                    
                    return f"登录成功！\\n截图保存到: /tmp/n8n_login_success.png\\nCookies: {cookies_json}"
                    
                except Exception as e:
                    # 尝试截图错误页面
                    await page.screenshot(path='/tmp/n8n_login_error.png')
                    await browser.close()
                    return f"登录失败: {str(e)}\\n错误截图保存到: /tmp/n8n_login_error.png"
                    
        except Exception as e:
            return f"浏览器自动化错误: {str(e)}"'''

new_login = '''    async def _login_n8n(self, username: str, password: str) -> str:
        """登录n8n"""
        browser = None
        try:
            async with async_playwright() as p:
                # 启动浏览器，配置代理
                browser = await p.chromium.launch(
                    headless=False,
                    args=[
                        '--no-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-gpu',
                        f'--proxy-server=socks5://127.0.0.1:20170'
                    ]
                )
                
                try:
                    context = await browser.new_context(
                        viewport={'width': 1280, 'height': 800},
                        proxy={
                            'server': 'socks5://127.0.0.1:20170'
                        }
                    )
                    
                    page = await context.new_page()
                    page.set_default_timeout(60000)
                    
                    # 访问n8n
                    await page.goto('http://localhost:5679')
                    
                    # 等待页面加载
                    await page.wait_for_load_state('networkidle')
                    
                    # 检查是否已经登录
                    try:
                        await page.wait_for_selector('text=Workflows', timeout=5000)
                        return "已经登录到n8n"
                    except:
                        pass
                    
                    # 查找登录表单
                    await page.wait_for_selector('input[name="emailOrLdapLoginId"]', timeout=10000)
                    
                    # 输入用户名和密码
                    await page.fill('input[name="emailOrLdapLoginId"]', username)
                    await page.fill('input[name="password"]', password)
                    
                    # 点击登录按钮
                    await page.click('button[type="submit"]')
                    
                    # 等待登录成功
                    try:
                        await page.wait_for_selector('text=Workflows', timeout=15000)
                        # 截图保存
                        await page.screenshot(path='/tmp/n8n_login_success.png')
                        
                        # 获取cookies
                        cookies = await context.cookies()
                        cookies_json = json.dumps(cookies, indent=2)
                        
                        return f"登录成功！\\n截图保存到: /tmp/n8n_login_success.png\\nCookies: {cookies_json}"
                        
                    except Exception as e:
                        # 尝试截图错误页面
                        await page.screenshot(path='/tmp/n8n_login_error.png')
                        return f"登录失败: {str(e)}\\n错误截图保存到: /tmp/n8n_login_error.png"
                finally:
                    if browser:
                        await browser.close()
                    
        except Exception as e:
            return f"浏览器自动化错误: {str(e)}"'''

src = src.replace(old_login, new_login)

# Fix _get_api_token: browser = None + inner try-finally
old_token = '''    async def _get_api_token(self, username: str, password: str) -> str:
        """获取API令牌"""
        try:
            async with async_playwright() as p:
                # 启动浏览器
                browser = await p.chromium.launch(
                    headless=False,
                    args=[
                        '--no-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-gpu',
                        f'--proxy-server=socks5://127.0.0.1:20170'
                    ]
                )
                
                context = await browser.new_context(
                    viewport={'width': 1280, 'height': 800},
                    proxy={
                        'server': 'socks5://127.0.0.1:20170'
                    }
                )
                
                page = await context.new_page()
                page.set_default_timeout(60000)
                
                # 访问n8n
                await page.goto('http://localhost:5679')
                await page.wait_for_load_state('networkidle')
                
                # 检查是否已经登录
                try:
                    await page.wait_for_selector('text=Workflows', timeout=5000)
                except:
                    # 需要先登录
                    await page.wait_for_selector('input[name="emailOrLdapLoginId"]', timeout=10000)
                    await page.fill('input[name="emailOrLdapLoginId"]', username)
                    await page.fill('input[name="password"]', password)
                    await page.click('button[type="submit"]')
                    await page.wait_for_selector('text=Workflows', timeout=15000)
                
                # 导航到设置页面
                await page.click('button[aria-label="User menu"]')
                await page.click('text=Settings')
                
                # 等待设置页面加载
                await page.wait_for_selector('text=API', timeout=10000)
                
                # 点击API菜单
                await page.click('text=API')
                
                # 等待API页面加载
                await page.wait_for_selector('text=Personal Access Tokens', timeout=10000)
                
                # 创建新的令牌
                await page.click('button:has-text("Create new token")')
                
                # 填写令牌信息
                await page.wait_for_selector('input[name="name"]', timeout=5000)
                await page.fill('input[name="name"]', 'Automation Token')
                
                # 生成令牌
                await page.click('button:has-text("Create")')
                
                # 等待令牌显示
                await page.wait_for_selector('code', timeout=10000)
                
                # 获取令牌
                token_element = await page.query_selector('code')
                token = await token_element.text_content()
                
                # 截图保存
                await page.screenshot(path='/tmp/n8n_api_token.png')
                
                # 保存令牌到文件
                with open('/tmp/n8n_api_token.txt', 'w') as f:
                    f.write(token)
                
                await browser.close()
                
                return f"API令牌获取成功！\\n令牌: {token}\\n已保存到: /tmp/n8n_api_token.txt\\n截图: /tmp/n8n_api_token.png"
                
        except Exception as e:
            return f"获取API令牌失败: {str(e)}"'''

new_token = '''    async def _get_api_token(self, username: str, password: str) -> str:
        """获取API令牌"""
        browser = None
        try:
            async with async_playwright() as p:
                # 启动浏览器
                browser = await p.chromium.launch(
                    headless=False,
                    args=[
                        '--no-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-gpu',
                        f'--proxy-server=socks5://127.0.0.1:20170'
                    ]
                )
                
                try:
                    context = await browser.new_context(
                        viewport={'width': 1280, 'height': 800},
                        proxy={
                            'server': 'socks5://127.0.0.1:20170'
                        }
                    )
                    
                    page = await context.new_page()
                    page.set_default_timeout(60000)
                    
                    # 访问n8n
                    await page.goto('http://localhost:5679')
                    await page.wait_for_load_state('networkidle')
                    
                    # 检查是否已经登录
                    try:
                        await page.wait_for_selector('text=Workflows', timeout=5000)
                    except:
                        # 需要先登录
                        await page.wait_for_selector('input[name="emailOrLdapLoginId"]', timeout=10000)
                        await page.fill('input[name="emailOrLdapLoginId"]', username)
                        await page.fill('input[name="password"]', password)
                        await page.click('button[type="submit"]')
                        await page.wait_for_selector('text=Workflows', timeout=15000)
                    
                    # 导航到设置页面
                    await page.click('button[aria-label="User menu"]')
                    await page.click('text=Settings')
                    
                    # 等待设置页面加载
                    await page.wait_for_selector('text=API', timeout=10000)
                    
                    # 点击API菜单
                    await page.click('text=API')
                    
                    # 等待API页面加载
                    await page.wait_for_selector('text=Personal Access Tokens', timeout=10000)
                    
                    # 创建新的令牌
                    await page.click('button:has-text("Create new token")')
                    
                    # 填写令牌信息
                    await page.wait_for_selector('input[name="name"]', timeout=5000)
                    await page.fill('input[name="name"]', 'Automation Token')
                    
                    # 生成令牌
                    await page.click('button:has-text("Create")')
                    
                    # 等待令牌显示
                    await page.wait_for_selector('code', timeout=10000)
                    
                    # 获取令牌
                    token_element = await page.query_selector('code')
                    token = await token_element.text_content()
                    
                    # 截图保存
                    await page.screenshot(path='/tmp/n8n_api_token.png')
                    
                    # 保存令牌到文件
                    with open('/tmp/n8n_api_token.txt', 'w') as f:
                        f.write(token)
                    
                    return f"API令牌获取成功！\\n令牌: {token}\\n已保存到: /tmp/n8n_api_token.txt\\n截图: /tmp/n8n_api_token.png"
                finally:
                    if browser:
                        await browser.close()
                
        except Exception as e:
            return f"获取API令牌失败: {str(e)}"'''

src = src.replace(old_token, new_token)

with open(path, 'w', encoding='utf-8') as f:
    f.write(src)

print("Fixed n8n_browser_automation.py")
