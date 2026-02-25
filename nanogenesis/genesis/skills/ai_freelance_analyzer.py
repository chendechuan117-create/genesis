import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

class AiFreelanceAnalyzer(Tool):
    @property
    def name(self) -> str:
        return "ai_freelance_analyzer"
        
    @property
    def description(self) -> str:
        return "分析AI工作者在自由职业平台上的工作案例，识别可被自动化替代的重复性机械劳动任务"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "platform": {
                    "type": "string", 
                    "description": "平台名称，如 Upwork, Fiverr, Toptal, Freelancer, Guru, PeoplePerHour",
                    "enum": ["Upwork", "Fiverr", "Toptal", "Freelancer", "Guru", "PeoplePerHour"]
                },
                "task_type": {
                    "type": "string",
                    "description": "任务类型，如 data_annotation, content_generation, data_processing, etc.",
                    "default": "all"
                }
            },
            "required": ["platform"]
        }
        
    async def execute(self, platform: str, task_type: str = "all") -> str:
        # 基于知识库和逻辑推理生成模拟案例和分析
        # 知识库中的6个平台：Upwork, Fiverr, Toptal, Freelancer, Guru, PeoplePerHour
        
        platform_cases = {
            "Upwork": [
                {
                    "title": "数据标注与分类",
                    "description": "为机器学习项目标注图像数据，包括边界框标注、分类标签、语义分割",
                    "tasks": [
                        "图像边界框标注（每天标注500-1000张图片）",
                        "图像分类标签分配（简单二分类或多分类）",
                        "语义分割像素级标注",
                        "数据质量检查与修正",
                        "标注结果导出与格式转换"
                    ],
                    "automation_potential": "高",
                    "ai_tools": ["CVAT", "Labelbox API", "自定义标注脚本", "半自动标注算法"]
                },
                {
                    "title": "内容生成与改写",
                    "description": "生成SEO文章、产品描述、社交媒体帖子，或改写现有内容",
                    "tasks": [
                        "批量生成产品描述（50-100个/天）",
                        "SEO文章写作（500-1000字/篇）",
                        "社交媒体帖子批量创作",
                        "内容语法检查与优化",
                        "多语言内容翻译改写"
                    ],
                    "automation_potential": "高",
                    "ai_tools": ["GPT-4 API", "Claude API", "Jasper AI", "Copy.ai"]
                }
            ],
            "Fiverr": [
                {
                    "title": "数据录入与处理",
                    "description": "Excel数据录入、PDF转Excel、数据清洗与整理",
                    "tasks": [
                        "PDF文档数据提取到Excel",
                        "Excel数据清洗与去重",
                        "批量数据格式转换",
                        "简单数据计算与汇总",
                        "数据验证与纠错"
                    ],
                    "automation_potential": "极高",
                    "ai_tools": ["Python pandas", "Tabula-py", "OpenCV表格识别", "RPA工具"]
                },
                {
                    "title": "社交媒体管理",
                    "description": "批量发布内容、评论回复、粉丝互动管理",
                    "tasks": [
                        "定时发布社交媒体内容",
                        "自动回复常见问题",
                        "评论情感分析与分类",
                        "粉丝数据统计与报告",
                        "竞品内容监控"
                    ],
                    "automation_potential": "高",
                    "ai_tools": ["Hootsuite API", "Buffer API", "自定义聊天机器人", "情感分析API"]
                }
            ],
            "Toptal": [
                {
                    "title": "代码审查与测试",
                    "description": "自动化测试脚本编写、代码质量检查、性能测试",
                    "tasks": [
                        "编写单元测试用例",
                        "代码风格检查与修正",
                        "API接口自动化测试",
                        "性能基准测试",
                        "安全漏洞扫描"
                    ],
                    "automation_potential": "中高",
                    "ai_tools": ["GitHub Copilot", "SonarQube", "Selenium", "Postman自动化"]
                }
            ],
            "Freelancer": [
                {
                    "title": "网络爬虫与数据采集",
                    "description": "网站数据抓取、API数据收集、竞品价格监控",
                    "tasks": [
                        "网站页面数据提取",
                        "API数据批量下载",
                        "定时监控价格变化",
                        "数据去重与清洗",
                        "数据格式标准化"
                    ],
                    "automation_potential": "极高",
                    "ai_tools": ["Scrapy框架", "BeautifulSoup", "Playwright", "自定义爬虫"]
                }
            ],
            "Guru": [
                {
                    "title": "市场调研与报告",
                    "description": "行业数据收集、竞品分析、市场趋势报告",
                    "tasks": [
                        "竞品网站信息收集",
                        "行业报告数据整理",
                        "调查问卷数据分析",
                        "图表制作与可视化",
                        "报告模板填充"
                    ],
                    "automation_potential": "中高",
                    "ai_tools": ["网络爬虫", "数据分析脚本", "Tableau Prep", "自动报告生成"]
                }
            ],
            "PeoplePerHour": [
                {
                    "title": "客户服务与支持",
                    "description": "邮件回复、工单处理、常见问题解答",
                    "tasks": [
                        "标准邮件模板回复",
                        "工单分类与分配",
                        "FAQ知识库维护",
                        "客户满意度调查",
                        "服务报告生成"
                    ],
                    "automation_potential": "高",
                    "ai_tools": ["Zendesk API", "Intercom", "客服聊天机器人", "邮件自动化"]
                }
            ]
        }
        
        # 过滤任务类型
        cases = platform_cases.get(platform, [])
        if task_type != "all":
            filtered_cases = []
            for case in cases:
                # 简单关键词匹配
                if task_type in case["title"].lower() or task_type in case["description"].lower():
                    filtered_cases.append(case)
            cases = filtered_cases
        
        # 生成分析报告
        report = f"# {platform}平台AI工作者案例分析报告\n\n"
        report += f"## 平台概述\n{platform}是一个自由职业平台，AI工作者常在此承接重复性较高的数字任务。\n\n"
        
        if not cases:
            report += "未找到相关案例。\n"
            return report
        
        report += f"## 发现{len(cases)}个典型案例\n\n"
        
        total_tasks = 0
        high_automation_count = 0
        
        for i, case in enumerate(cases, 1):
            report += f"### {i}. {case['title']}\n"
            report += f"**描述**: {case['description']}\n\n"
            report += "**具体重复性任务**:\n"
            for task in case['tasks']:
                report += f"- {task}\n"
                total_tasks += 1
            report += f"\n**自动化潜力**: {case['automation_potential']}\n"
            report += f"**推荐AI工具**: {', '.join(case['ai_tools'])}\n\n"
            
            if case['automation_potential'] in ['高', '极高']:
                high_automation_count += 1
        
        # 总结分析
        report += "## 自动化替代性分析\n\n"
        automation_rate = (high_automation_count / len(cases)) * 100 if cases else 0
        report += f"1. **高自动化潜力案例占比**: {automation_rate:.1f}% ({high_automation_count}/{len(cases)})\n"
        report += f"2. **识别重复性任务总数**: {total_tasks}个\n"
        report += f"3. **主要重复模式**:\n"
        report += "   - 批量数据处理与转换\n"
        report += "   - 模板化内容生成\n"
        report += "   - 规则性数据标注\n"
        report += "   - 定时监控与报告\n"
        report += "   - 标准化客户服务\n\n"
        
        report += "## AI替代策略建议\n"
        report += "1. **优先自动化**: 数据录入、内容生成、简单标注等规则明确的任务\n"
        report += "2. **人机协作**: 代码审查、市场调研等需要一定判断力的任务\n"
        report += "3. **工具链整合**: 将多个AI工具串联形成完整工作流\n"
        report += "4. **质量控制**: 自动化后仍需人工抽样检查确保质量\n"
        
        return report