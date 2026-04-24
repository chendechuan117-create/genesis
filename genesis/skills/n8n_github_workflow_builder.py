import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

import json
from typing import Dict, Optional, List, Any

class N8nGithubWorkflowBuilder(Tool):
    """
    构建 n8n 与 GitHub 仓库交互的自动化工作流。
    支持创建 Issues、PRs、Release、代码扫描等常见 DevOps 场景。
    """
    
    @property
    def name(self) -> str:
        return "n8n_github_workflow_builder"
        
    @property
    def description(self) -> str:
        return "构建 n8n 与 GitHub 仓库交互的自动化工作流。支持 Issue 自动创建、PR 状态监控、Release 自动化、代码扫描触发等 DevOps 场景。生成标准 n8n 工作流 JSON 可直接导入。"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "workflow_type": {
                    "type": "string",
                    "enum": [
                        "issue_auto_create",
                        "pr_status_monitor",
                        "release_automation",
                        "security_scan_trigger",
                        "dependabot_alert_handler",
                        "star_tracker",
                        "contributor_welcome"
                    ],
                    "description": "工作流类型: issue_auto_create(自动创建Issue), pr_status_monitor(PR状态监控), release_automation(Release自动化), security_scan_trigger(安全扫描触发), dependabot_alert_handler(Dependabot警报处理), star_tracker(Star追踪), contributor_welcome(贡献者欢迎)"
                },
                "github_owner": {
                    "type": "string",
                    "description": "GitHub 仓库所有者(用户名或组织名)"
                },
                "github_repo": {
                    "type": "string",
                    "description": "GitHub 仓库名称"
                },
                "github_token": {
                    "type": "string",
                    "description": "GitHub Personal Access Token(可选，可从环境变量 GITHUB_TOKEN 读取)"
                },
                "webhook_url": {
                    "type": "string",
                    "description": "外部触发用的 Webhook URL(可选)"
                },
                "custom_config": {
                    "type": "object",
                    "description": "自定义配置参数，根据工作流类型不同而变化"
                }
            },
            "required": ["workflow_type", "github_owner", "github_repo"]
        }
    
    async def execute(self, workflow_type: str, github_owner: str, github_repo: str,
                     github_token: Optional[str] = None, webhook_url: Optional[str] = None,
                     custom_config: Optional[Dict] = None) -> str:
        """
        执行工作流构建
        """
        # 从环境变量获取 token
        if not github_token:
            import os
            github_token = os.environ.get("GITHUB_TOKEN")
        
        config = custom_config or {}
        
        # 根据工作流类型生成对应的工作流
        builders = {
            "issue_auto_create": self._build_issue_auto_create_workflow,
            "pr_status_monitor": self._build_pr_status_monitor_workflow,
            "release_automation": self._build_release_automation_workflow,
            "security_scan_trigger": self._build_security_scan_workflow,
            "dependabot_alert_handler": self._build_dependabot_workflow,
            "star_tracker": self._build_star_tracker_workflow,
            "contributor_welcome": self._build_contributor_welcome_workflow
        }
        
        if workflow_type not in builders:
            return f"❌ 不支持的工作流类型: {workflow_type}"
        
        try:
            workflow_json = builders[workflow_type](
                github_owner, github_repo, github_token, webhook_url, config
            )
            
            # 保存到文件
            output_path = f"/tmp/n8n_{workflow_type}_{github_repo}.json"
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(workflow_json, f, indent=2, ensure_ascii=False)
            
            workflow_name = workflow_json.get("name", "未命名")
            node_count = len(workflow_json.get("nodes", []))
            
            result = f"✅ n8n GitHub 工作流生成成功！\n"
            result += f"=" * 60 + "\n"
            result += f"📋 工作流名称: {workflow_name}\n"
            result += f"🔧 工作流类型: {workflow_type}\n"
            result += f"📦 目标仓库: {github_owner}/{github_repo}\n"
            result += f"🔩 节点数量: {node_count}\n"
            result += f"💾 输出文件: {output_path}\n"
            result += f"=" * 60 + "\n"
            result += f"📖 导入方式:\n"
            result += f"   1. 打开 n8n 界面 → Settings → Import from File\n"
            result += f"   2. 选择: {output_path}\n"
            result += f"   3. 配置 GitHub Token 凭证\n"
            result += f"   4. 激活工作流\n"
            
            return result
            
        except Exception as e:
            return f"❌ 工作流生成失败: {str(e)}"
    
    def _build_issue_auto_create_workflow(self, owner: str, repo: str, 
                                          token: Optional[str], webhook: Optional[str],
                                          config: Dict) -> Dict:
        """构建自动创建 Issue 的工作流"""
        issue_title_template = config.get("issue_title", "[Auto] New Issue from {{ $json.source }}")
        issue_body_template = config.get("issue_body", "Automatically created by n8n workflow.")
        
        workflow = {
            "name": f"GitHub Issue Auto-Creator for {repo}",
            "active": False,
            "settings": {
                "executionOrder": "v1",
                "saveManualExecutions": True
            },
            "tags": ["github", "automation", "issues"],
            "nodes": [
                {
                    "id": "trigger-node",
                    "name": "Webhook Trigger",
                    "type": "n8n-nodes-base.webhook",
                    "typeVersion": 1,
                    "position": [250, 300],
                    "parameters": {
                        "httpMethod": "POST",
                        "path": f"github-issue-trigger-{repo}",
                        "responseMode": "responseNode",
                        "options": {}
                    },
                    "webhookId": f"github-issue-{repo}"
                },
                {
                    "id": "github-node",
                    "name": "Create GitHub Issue",
                    "type": "n8n-nodes-base.github",
                    "typeVersion": 2.1,
                    "position": [500, 300],
                    "parameters": {
                        "resource": "issue",
                        "operation": "create",
                        "owner": owner,
                        "repository": repo,
                        "title": issue_title_template,
                        "body": issue_body_template,
                        "labels": config.get("labels", ["automated", "n8n"])
                    },
                    "credentials": {
                        "githubApi": {
                            "id": "github-creds",
                            "name": "GitHub API"
                        }
                    }
                },
                {
                    "id": "respond-node",
                    "name": "Success Response",
                    "type": "n8n-nodes-base.respondToWebhook",
                    "typeVersion": 1,
                    "position": [750, 300],
                    "parameters": {
                        "options": {},
                        "respondWith": "json",
                        "responseBody": "={\"success\": true, \"issueUrl\": $json.url}"
                    }
                }
            ],
            "connections": {
                "Webhook Trigger": {
                    "main": [[{"node": "Create GitHub Issue", "type": "main", "index": 0}]]
                },
                "Create GitHub Issue": {
                    "main": [[{"node": "Success Response", "type": "main", "index": 0}]]
                }
            }
        }
        return workflow
    
    def _build_pr_status_monitor_workflow(self, owner: str, repo: str,
                                          token: Optional[str], webhook: Optional[str],
                                          config: Dict) -> Dict:
        """构建 PR 状态监控工作流"""
        check_interval = config.get("check_interval_minutes", 30)
        notify_on = config.get("notify_on", ["opened", "closed", "merged"])
        
        workflow = {
            "name": f"GitHub PR Monitor for {repo}",
            "active": False,
            "settings": {
                "executionOrder": "v1"
            },
            "tags": ["github", "monitoring", "pull-requests"],
            "nodes": [
                {
                    "id": "schedule-node",
                    "name": "Schedule Trigger",
                    "type": "n8n-nodes-base.scheduleTrigger",
                    "typeVersion": 1.1,
                    "position": [250, 300],
                    "parameters": {
                        "rule": {
                            "interval": [{"field": "minutes", "minutesInterval": check_interval}]
                        }
                    }
                },
                {
                    "id": "github-list-prs",
                    "name": "List Open PRs",
                    "type": "n8n-nodes-base.github",
                    "typeVersion": 2.1,
                    "position": [500, 300],
                    "parameters": {
                        "resource": "pullRequest",
                        "operation": "getAll",
                        "owner": owner,
                        "repository": repo,
                        "returnAll": True,
                        "filters": {
                            "state": "open"
                        }
                    }
                },
                {
                    "id": "filter-node",
                    "name": "Filter Updated PRs",
                    "type": "n8n-nodes-base.if",
                    "typeVersion": 2,
                    "position": [750, 300],
                    "parameters": {
                        "conditions": {
                            "options": {
                                "caseSensitive": True,
                                "leftValue": "",
                                "typeValidation": "strict"
                            },
                            "conditions": [{
                                "id": "cond-1",
                                "leftValue": "={{ $json.updated_at }}",
                                "rightValue": "={{ $now.minus({minutes: " + str(check_interval + 5) + "}).toISO() }}",
                                "operator": {
                                    "type": "dateTime",
                                    "operation": "after"
                                }
                            }]
                        }
                    }
                },
                {
                    "id": "notify-node",
                    "name": "Send Notification",
                    "type": "n8n-nodes-base.httpRequest",
                    "typeVersion": 4.1,
                    "position": [1000, 300],
                    "parameters": {
                        "method": "POST",
                        "url": webhook or "http://localhost:3000/notify",
                        "sendBody": True,
                        "contentType": "json",
                        "body": {
                            "message": "=PR Updated: {{ $json.title }} by {{ $json.user.login }}"
                        }
                    }
                }
            ],
            "connections": {
                "Schedule Trigger": {
                    "main": [[{"node": "List Open PRs", "type": "main", "index": 0}]]
                },
                "List Open PRs": {
                    "main": [[{"node": "Filter Updated PRs", "type": "main", "index": 0}]]
                },
                "Filter Updated PRs": {
                    "main": [[{"node": "Send Notification", "type": "main", "index": 0}]]
                }
            }
        }
        return workflow
    
    def _build_release_automation_workflow(self, owner: str, repo: str,
                                           token: Optional[str], webhook: Optional[str],
                                           config: Dict) -> Dict:
        """构建 Release 自动化工作流"""
        version_bump_type = config.get("version_bump", "patch")  # major, minor, patch
        
        workflow = {
            "name": f"GitHub Release Automation for {repo}",
            "active": False,
            "settings": {"executionOrder": "v1"},
            "tags": ["github", "release", "automation"],
            "nodes": [
                {
                    "id": "trigger",
                    "name": "Manual Trigger",
                    "type": "n8n-nodes-base.manualTrigger",
                    "typeVersion": 1,
                    "position": [250, 300]
                },
                {
                    "id": "get-latest",
                    "name": "Get Latest Release",
                    "type": "n8n-nodes-base.github",
                    "typeVersion": 2.1,
                    "position": [500, 300],
                    "parameters": {
                        "resource": "release",
                        "operation": "getAll",
                        "owner": owner,
                        "repository": repo,
                        "returnAll": False,
                        "limit": 1
                    }
                },
                {
                    "id": "calculate-version",
                    "name": "Calculate New Version",
                    "type": "n8n-nodes-base.code",
                    "typeVersion": 2,
                    "position": [750, 300],
                    "parameters": {
                        "jsCode": f"""
                        const latest = $input.first().json.tag_name || 'v0.0.0';
                        const parts = latest.replace('v', '').split('.').map(Number);
                        if ('{version_bump_type}' === 'major') parts[0]++;
                        else if ('{version_bump_type}' === 'minor') parts[1]++;
                        else parts[2]++;
                        return [{{ json: {{ newVersion: `v${{parts.join('.')}}` }} }}];
                        """
                    }
                },
                {
                    "id": "create-release",
                    "name": "Create Release",
                    "type": "n8n-nodes-base.github",
                    "typeVersion": 2.1,
                    "position": [1000, 300],
                    "parameters": {
                        "resource": "release",
                        "operation": "create",
                        "owner": owner,
                        "repository": repo,
                        "tag_name": "={{ $json.newVersion }}",
                        "name": "={{ $json.newVersion }}",
                        "body": "🚀 Automated release created by n8n"
                    }
                }
            ],
            "connections": {
                "Manual Trigger": {
                    "main": [[{"node": "Get Latest Release", "type": "main", "index": 0}]]
                },
                "Get Latest Release": {
                    "main": [[{"node": "Calculate New Version", "type": "main", "index": 0}]]
                },
                "Calculate New Version": {
                    "main": [[{"node": "Create Release", "type": "main", "index": 0}]]
                }
            }
        }
        return workflow
    
    def _build_security_scan_workflow(self, owner: str, repo: str,
                                      token: Optional[str], webhook: Optional[str],
                                      config: Dict) -> Dict:
        """构建安全扫描触发工作流"""
        workflow = {
            "name": f"GitHub Security Scan for {repo}",
            "active": False,
            "settings": {"executionOrder": "v1"},
            "tags": ["github", "security", "scanning"],
            "nodes": [
                {
                    "id": "trigger",
                    "name": "Schedule Trigger",
                    "type": "n8n-nodes-base.scheduleTrigger",
                    "typeVersion": 1.1,
                    "position": [250, 300],
                    "parameters": {
                        "rule": {
                            "interval": [{"field": "hours", "hoursInterval": 24}]
                        }
                    }
                },
                {
                    "id": "codeql-trigger",
                    "name": "Trigger CodeQL Analysis",
                    "type": "n8n-nodes-base.httpRequest",
                    "typeVersion": 4.1,
                    "position": [500, 300],
                    "parameters": {
                        "method": "POST",
                        "url": f"https://api.github.com/repos/{owner}/{repo}/actions/workflows/codeql-analysis.yml/dispatches",
                        "authentication": "genericCredentialType",
                        "genericAuthType": "httpHeaderAuth",
                        "sendBody": True,
                        "body": {"ref": "main"}
                    }
                },
                {
                    "id": "secret-scan",
                    "name": "Check Secret Scanning Alerts",
                    "type": "n8n-nodes-base.github",
                    "typeVersion": 2.1,
                    "position": [500, 500],
                    "parameters": {
                        "resource": "repository",
                        "operation": "get",
                        "owner": owner,
                        "repository": repo
                    }
                }
            ],
            "connections": {
                "Schedule Trigger": {
                    "main": [
                        [{"node": "Trigger CodeQL Analysis", "type": "main", "index": 0}],
                        [{"node": "Check Secret Scanning Alerts", "type": "main", "index": 0}]
                    ]
                }
            }
        }
        return workflow
    
    def _build_dependabot_workflow(self, owner: str, repo: str,
                                   token: Optional[str], webhook: Optional[str],
                                   config: Dict) -> Dict:
        """构建 Dependabot 警报处理工作流"""
        auto_merge_severity = config.get("auto_merge_severity", ["low", "moderate"])
        
        workflow = {
            "name": f"GitHub Dependabot Handler for {repo}",
            "active": False,
            "settings": {"executionOrder": "v1"},
            "tags": ["github", "dependabot", "security"],
            "nodes": [
                {
                    "id": "webhook",
                    "name": "Dependabot Webhook",
                    "type": "n8n-nodes-base.webhook",
                    "typeVersion": 1,
                    "position": [250, 300],
                    "parameters": {
                        "httpMethod": "POST",
                        "path": f"dependabot-{owner}-{repo}",
                        "responseMode": "onReceived"
                    }
                },
                {
                    "id": "parse",
                    "name": "Parse Alert",
                    "type": "n8n-nodes-base.code",
                    "typeVersion": 2,
                    "position": [500, 300],
                    "parameters": {
                        "jsCode": """
                        const alert = $input.first().json;
                        return [{
                            json: {
                                severity: alert.alert.security_advisory.severity,
                                package: alert.alert.dependency.package.name,
                                pr_url: alert.alert.html_url
                            }
                        }];
                        """
                    }
                },
                {
                    "id": "decide",
                    "name": "Auto-Merge Decision",
                    "type": "n8n-nodes-base.if",
                    "typeVersion": 2,
                    "position": [750, 300],
                    "parameters": {
                        "conditions": {
                            "conditions": [{
                                "leftValue": "={{ $json.severity }}",
                                "operator": {
                                    "type": "string",
                                    "operation": "equals"
                                },
                                "rightValue": "low"
                            }]
                        }
                    }
                },
                {
                    "id": "merge",
                    "name": "Auto Merge PR",
                    "type": "n8n-nodes-base.github",
                    "typeVersion": 2.1,
                    "position": [1000, 250],
                    "parameters": {
                        "resource": "pullRequest",
                        "operation": "merge",
                        "owner": owner,
                        "repository": repo
                    }
                },
                {
                    "id": "notify",
                    "name": "Notify Team",
                    "type": "n8n-nodes-base.httpRequest",
                    "typeVersion": 4.1,
                    "position": [1000, 450],
                    "parameters": {
                        "method": "POST",
                        "url": webhook or "",
                        "sendBody": True,
                        "body": {
                            "text": "=High severity Dependabot alert: {{ $json.package }}"
                        }
                    }
                }
            ],
            "connections": {
                "Dependabot Webhook": {
                    "main": [[{"node": "Parse Alert", "type": "main", "index": 0}]]
                },
                "Parse Alert": {
                    "main": [[{"node": "Auto-Merge Decision", "type": "main", "index": 0}]]
                },
                "Auto-Merge Decision": {
                    "main": [
                        [{"node": "Auto Merge PR", "type": "main", "index": 0}],
                        [{"node": "Notify Team", "type": "main", "index": 0}]
                    ]
                }
            }
        }
        return workflow
    
    def _build_star_tracker_workflow(self, owner: str, repo: str,
                                     token: Optional[str], webhook: Optional[str],
                                     config: Dict) -> Dict:
        """构建 Star 追踪工作流"""
        milestones = config.get("milestones", [100, 500, 1000, 5000, 10000])
        
        workflow = {
            "name": f"GitHub Star Tracker for {repo}",
            "active": False,
            "settings": {"executionOrder": "v1"},
            "tags": ["github", "stars", "analytics"],
            "nodes": [
                {
                    "id": "schedule",
                    "name": "Daily Check",
                    "type": "n8n-nodes-base.scheduleTrigger",
                    "typeVersion": 1.1,
                    "position": [250, 300],
                    "parameters": {
                        "rule": {
                            "interval": [{"field": "hours", "hoursInterval": 24}]
                        }
                    }
                },
                {
                    "id": "get-repo",
                    "name": "Get Repository Info",
                    "type": "n8n-nodes-base.github",
                    "typeVersion": 2.1,
                    "position": [500, 300],
                    "parameters": {
                        "resource": "repository",
                        "operation": "get",
                        "owner": owner,
                        "repository": repo
                    }
                },
                {
                    "id": "check-milestone",
                    "name": "Check Milestone",
                    "type": "n8n-nodes-base.code",
                    "typeVersion": 2,
                    "position": [750, 300],
                    "parameters": {
                        "jsCode": f"""
                        const stars = $input.first().json.stargazers_count;
                        const milestones = {json.dumps(milestones)};
                        const hit = milestones.find(m => stars >= m && stars < m + 50);
                        return [{{ json: {{ stars, hitMilestone: hit || null, shouldNotify: !!hit }} }}];
                        """
                    }
                },
                {
                    "id": "filter",
                    "name": "Filter Hits",
                    "type": "n8n-nodes-base.if",
                    "typeVersion": 2,
                    "position": [1000, 300],
                    "parameters": {
                        "conditions": {
                            "conditions": [{
                                "leftValue": "={{ $json.shouldNotify }}",
                                "operator": {"type": "boolean", "operation": "equals"},
                                "rightValue": "=true"
                            }]
                        }
                    }
                },
                {
                    "id": "celebrate",
                    "name": "Send Celebration",
                    "type": "n8n-nodes-base.httpRequest",
                    "typeVersion": 4.1,
                    "position": [1250, 300],
                    "parameters": {
                        "method": "POST",
                        "url": webhook or "",
                        "sendBody": True,
                        "body": {
                            "text": "=🎉 {repo} just hit {{ $json.hitMilestone }} stars! ({{ $json.stars }} total)"
                        }
                    }
                }
            ],
            "connections": {
                "Daily Check": {
                    "main": [[{"node": "Get Repository Info", "type": "main", "index": 0}]]
                },
                "Get Repository Info": {
                    "main": [[{"node": "Check Milestone", "type": "main", "index": 0}]]
                },
                "Check Milestone": {
                    "main": [[{"node": "Filter Hits", "type": "main", "index": 0}]]
                },
                "Filter Hits": {
                    "main": [[{"node": "Send Celebration", "type": "main", "index": 0}]]
                }
            }
        }
        return workflow
    
    def _build_contributor_welcome_workflow(self, owner: str, repo: str,
                                            token: Optional[str], webhook: Optional[str],
                                            config: Dict) -> Dict:
        """构建贡献者欢迎工作流"""
        welcome_message = config.get("welcome_message", 
            "Thanks for your first contribution! 🎉 We appreciate your help in making {repo} better!")
        
        workflow = {
            "name": f"GitHub Contributor Welcome for {repo}",
            "active": False,
            "settings": {"executionOrder": "v1"},
            "tags": ["github", "community", "onboarding"],
            "nodes": [
                {
                    "id": "webhook",
                    "name": "PR Webhook",
                    "type": "n8n-nodes-base.webhook",
                    "typeVersion": 1,
                    "position": [250, 300],
                    "parameters": {
                        "httpMethod": "POST",
                        "path": f"pr-welcome-{repo}",
                        "responseMode": "onReceived"
                    }
                },
                {
                    "id": "check-first",
                    "name": "Check First PR",
                    "type": "n8n-nodes-base.code",
                    "typeVersion": 2,
                    "position": [500, 300],
                    "parameters": {
                        "jsCode": """
                        const pr = $input.first().json.pull_request;
                        const isFirst = pr.author_association === 'FIRST_TIME_CONTRIBUTOR';
                        return [{ json: { isFirst, user: pr.user.login, pr_number: pr.number } }];
                        """
                    }
                },
                {
                    "id": "filter-first",
                    "name": "Is First PR?",
                    "type": "n8n-nodes-base.if",
                    "typeVersion": 2,
                    "position": [750, 300],
                    "parameters": {
                        "conditions": {
                            "conditions": [{
                                "leftValue": "={{ $json.isFirst }}",
                                "operator": {"type": "boolean", "operation": "equals"},
                                "rightValue": "=true"
                            }]
                        }
                    }
                },
                {
                    "id": "comment",
                    "name": "Post Welcome Comment",
                    "type": "n8n-nodes-base.github",
                    "typeVersion": 2.1,
                    "position": [1000, 300],
                    "parameters": {
                        "resource": "issue",
                        "operation": "createComment",
                        "owner": owner,
                        "repository": repo,
                        "issue_number": "={{ $json.pr_number }}",
                        "body": welcome_message.replace("{repo}", repo)
                    }
                }
            ],
            "connections": {
                "PR Webhook": {
                    "main": [[{"node": "Check First PR", "type": "main", "index": 0}]]
                },
                "Check First PR": {
                    "main": [[{"node": "Is First PR?", "type": "main", "index": 0}]]
                },
                "Is First PR?": {
                    "main": [[{"node": "Post Welcome Comment", "type": "main", "index": 0}]]
                }
            }
        }
        return workflow


# 注册工具
if __name__ == "__main__":
    tool = N8nGithubWorkflowBuilder()
    import asyncio
    result = asyncio.run(tool.execute(
        workflow_type="issue_auto_create",
        github_owner="octocat",
        github_repo="Hello-World"
    ))
    print(result)
