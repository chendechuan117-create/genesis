"""
网络健康状态可视化模块
为 GP 提供知识图谱健康状态的直观展示
"""

import json
from typing import Dict, List, Tuple
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class NetworkHealthMonitor:
    """网络健康监控器 - 为 GP 提供知识图谱健康状态的可视化界面"""
    
    def __init__(self, vault):
        self.vault = vault
        self._conn = vault._conn
    
    def generate_health_report(self) -> Dict:
        """生成完整的网络健康报告"""
        try:
            report = {
                "timestamp": datetime.now().isoformat(),
                "overall_health": self._calculate_overall_health(),
                "knowledge_distribution": self._analyze_knowledge_distribution(),
                "connection_health": self._analyze_connection_health(),
                "trap_analysis": self._analyze_trap_nodes(),
                "saturation_zones": self._analyze_saturation_zones(),
                "growth_metrics": self._analyze_growth_metrics(),
                "recommendations": self._generate_recommendations()
            }
            return report
        except Exception as e:
            logger.error(f"generate_health_report failed: {e}")
            return {"error": str(e)}
    
    def _calculate_overall_health(self) -> Dict:
        """计算整体健康评分 (0-100)"""
        try:
            # 基础统计
            total_nodes = self._conn.execute(
                "SELECT COUNT(*) as cnt FROM knowledge_nodes WHERE node_id NOT LIKE 'MEM_CONV%'"
            ).fetchone()['cnt']
            
            total_edges = self._conn.execute(
                "SELECT COUNT(*) as cnt FROM node_edges"
            ).fetchone()['cnt']
            
            active_nodes = self._conn.execute(
                "SELECT COUNT(*) as cnt FROM knowledge_nodes WHERE ablation_active = 0 AND node_id NOT LIKE 'MEM_CONV%'"
            ).fetchone()['cnt']
            
            # 计算健康指标
            connectivity_ratio = total_edges / max(total_nodes, 1)
            activity_ratio = active_nodes / max(total_nodes, 1)
            
            # 陷阱节点比例（越低越好）
            trap_nodes = self._count_trap_nodes()
            trap_ratio = trap_nodes / max(total_nodes, 1)
            
            # 综合健康评分
            health_score = (
                min(connectivity_ratio * 20, 20) +  # 连通性 (0-20分)
                min(activity_ratio * 30, 30) +      # 活跃度 (0-30分)
                max(0, 25 - trap_ratio * 25) +      # 陷阱惩罚 (0-25分)
                25  # 基础分
            )
            
            return {
                "score": round(health_score, 1),
                "total_nodes": total_nodes,
                "active_nodes": active_nodes,
                "total_edges": total_edges,
                "connectivity_ratio": round(connectivity_ratio, 3),
                "activity_ratio": round(activity_ratio, 3),
                "trap_ratio": round(trap_ratio, 3),
                "status": self._get_health_status(health_score)
            }
        except Exception as e:
            logger.error(f"_calculate_overall_health failed: {e}")
            return {"score": 0, "status": "error", "error": str(e)}
    
    def _analyze_knowledge_distribution(self) -> Dict:
        """分析知识分布情况"""
        try:
            # 按类型分布
            type_distribution = {}
            type_rows = self._conn.execute(
                "SELECT type, COUNT(*) as cnt FROM knowledge_nodes WHERE node_id NOT LIKE 'MEM_CONV%' GROUP BY type ORDER BY cnt DESC"
            ).fetchall()
            
            for row in type_rows:
                type_distribution[row['type']] = row['cnt']
            
            # 按信任层级分布
            tier_distribution = {}
            tier_rows = self._conn.execute(
                "SELECT trust_tier, COUNT(*) as cnt FROM knowledge_nodes WHERE node_id NOT LIKE 'MEM_CONV%' GROUP BY trust_tier ORDER BY cnt DESC"
            ).fetchall()
            
            for row in tier_rows:
                tier_distribution[row['trust_tier'] or 'NULL'] = row['cnt']
            
            # 入线数分布
            incoming_dist = self._analyze_incoming_distribution()
            
            return {
                "by_type": type_distribution,
                "by_trust_tier": tier_distribution,
                "incoming_distribution": incoming_dist
            }
        except Exception as e:
            logger.error(f"_analyze_knowledge_distribution failed: {e}")
            return {"error": str(e)}
    
    def _analyze_incoming_distribution(self) -> Dict:
        """分析入线数分布"""
        try:
            # 入线数分段统计
            distribution = {
                "0": 0,      # 孤立节点
                "1-2": 0,    # 低连接
                "3-5": 0,    # 中等连接
                "6-10": 0,   # 高连接
                "10+": 0     # 核心节点
            }
            
            rows = self._conn.execute(
                """SELECT inc.incoming_count, COUNT(*) as node_count
                   FROM (
                       SELECT kn.node_id, COUNT(rl.basis_point_id) as incoming_count
                       FROM knowledge_nodes kn
                       LEFT JOIN reasoning_lines rl ON kn.node_id = rl.basis_point_id
                       WHERE kn.node_id NOT LIKE 'MEM_CONV%'
                       GROUP BY kn.node_id
                   ) inc
                   GROUP BY inc.incoming_count
                   ORDER BY inc.incoming_count"""
            ).fetchall()
            
            for row in rows:
                incoming, count = row['incoming_count'], row['node_count']
                if incoming == 0:
                    distribution["0"] += count
                elif incoming <= 2:
                    distribution["1-2"] += count
                elif incoming <= 5:
                    distribution["3-5"] += count
                elif incoming <= 10:
                    distribution["6-10"] += count
                else:
                    distribution["10+"] += count
            
            return distribution
        except Exception as e:
            logger.error(f"_analyze_incoming_distribution failed: {e}")
            return {"error": str(e)}
    
    def _analyze_connection_health(self) -> Dict:
        """分析连接健康状态"""
        try:
            # 边类型分布
            edge_types = {}
            edge_rows = self._conn.execute(
                "SELECT relation, COUNT(*) as cnt FROM node_edges GROUP BY relation ORDER BY cnt DESC"
            ).fetchall()
            
            for row in edge_rows:
                edge_types[row['relation'] or 'NULL'] = row['cnt']
            
            # 矛盾边统计
            contradiction_count = edge_types.get('CONTRADICTS', 0)
            
            # 推理线统计
            reasoning_lines = self._conn.execute(
                "SELECT COUNT(*) as cnt FROM reasoning_lines WHERE same_round = 0"
            ).fetchone()['cnt']
            
            return {
                "edge_types": edge_types,
                "contradiction_count": contradiction_count,
                "reasoning_lines": reasoning_lines,
                "has_contradictions": contradiction_count > 0
            }
        except Exception as e:
            logger.error(f"_analyze_connection_health failed: {e}")
            return {"error": str(e)}
    
    def _analyze_trap_nodes(self) -> Dict:
        """分析陷阱节点"""
        try:
            trap_nodes = []
            
            rows = self._conn.execute(
                """SELECT kn.node_id, kn.title, kn.usage_success_count, kn.usage_fail_count, kn.usage_count,
                          COALESCE(inc.incoming, 0) as incoming_count
                   FROM knowledge_nodes kn
                   LEFT JOIN (
                       SELECT basis_point_id, COUNT(*) as incoming
                       FROM reasoning_lines
                       GROUP BY basis_point_id
                   ) inc ON kn.node_id = inc.basis_point_id
                   WHERE kn.node_id NOT LIKE 'MEM_CONV%'
                     AND kn.usage_count >= 3
                     AND kn.ablation_active = 0
                     AND inc.incoming >= 2
                     AND (kn.usage_success_count * 1.0 / kn.usage_count) < 0.5
                   ORDER BY inc.incoming DESC, (kn.usage_success_count * 1.0 / kn.usage_count) ASC
                   LIMIT 10"""
            ).fetchall()
            
            for row in rows:
                win_rate = (row['usage_success_count'] or 0) / max(row['usage_count'] or 1, 1)
                if win_rate < 0.5 and row['incoming_count'] >= 2:  # 陷阱定义：高入线+低胜率
                    trap_nodes.append({
                        "node_id": row['node_id'],
                        "title": row['title'][:80] + "..." if len(row['title']) > 80 else row['title'],
                        "incoming_count": row['incoming_count'],
                        "win_rate": round(win_rate, 3),
                        "usage_count": row['usage_count'],
                        "severity": "high" if win_rate < 0.3 else "medium"
                    })
            
            return {
                "trap_count": len(trap_nodes),
                "trap_nodes": trap_nodes[:5],  # 只返回前5个
                "has_traps": len(trap_nodes) > 0
            }
        except Exception as e:
            logger.error(f"_analyze_trap_nodes failed: {e}")
            return {"error": str(e)}
    
    def _analyze_saturation_zones(self) -> Dict:
        """分析饱和区域"""
        try:
            saturation_zones = []
            
            rows = self._conn.execute(
                """SELECT substr(title, 4) as area, COUNT(*) as count
                   FROM knowledge_nodes
                   WHERE type = 'CONTEXT' AND title LIKE '饱和:%'
                   GROUP BY substr(title, 4)
                   HAVING count >= 3
                   ORDER BY count DESC
                   LIMIT 5"""
            ).fetchall()
            
            for row in rows:
                saturation_zones.append({
                    "area": row['area'],
                    "virtual_point_count": row['count'],
                    "saturation_level": "high" if row['count'] >= 5 else "medium"
                })
            
            return {
                "zone_count": len(saturation_zones),
                "zones": saturation_zones,
                "has_saturation": len(saturation_zones) > 0
            }
        except Exception as e:
            logger.error(f"_analyze_saturation_zones failed: {e}")
            return {"error": str(e)}
    
    def _analyze_growth_metrics(self) -> Dict:
        """分析增长指标"""
        try:
            now = datetime.now()
            
            # 最近7天创建的节点
            week_ago = now - timedelta(days=7)
            recent_nodes = self._conn.execute(
                "SELECT COUNT(*) as cnt FROM knowledge_nodes WHERE created_at > ? AND node_id NOT LIKE 'MEM_CONV%'",
                (week_ago.isoformat(),)
            ).fetchone()['cnt']
            
            # 最近7天验证的节点
            recent_verified = self._conn.execute(
                "SELECT COUNT(*) as cnt FROM knowledge_nodes WHERE last_verified_at > ? AND node_id NOT LIKE 'MEM_CONV%'",
                (week_ago.isoformat(),)
            ).fetchone()['cnt']
            
            # VOID 任务数量
            void_count = self._conn.execute(
                "SELECT COUNT(*) as cnt FROM void_tasks WHERE status = 'open'"
            ).fetchone()['cnt'] or 0
            
            return {
                "nodes_created_last_week": recent_nodes,
                "nodes_verified_last_week": recent_verified,
                "void_tasks_count": void_count,
                "growth_rate": "healthy" if recent_nodes > 5 else "slow"
            }
        except Exception as e:
            logger.error(f"_analyze_growth_metrics failed: {e}")
            return {"error": str(e)}
    
    def _generate_recommendations(self) -> List[str]:
        """生成改进建议"""
        recommendations = []
        
        try:
            # 基于陷阱节点分析
            trap_analysis = self._analyze_trap_nodes()
            if trap_analysis.get("has_traps"):
                recommendations.append(f"发现 {trap_analysis['trap_count']} 个陷阱节点，建议运行园丁消融机制")
            
            # 基于饱和区域分析
            saturation = self._analyze_saturation_zones()
            if saturation.get("has_saturation"):
                recommendations.append(f"存在 {saturation['zone_count']} 个饱和区域，建议探索新知识方向")
            
            # 基于连接健康
            connection = self._analyze_connection_health()
            if connection.get("has_contradictions"):
                recommendations.append(f"发现 {connection['contradiction_count']} 个矛盾关系，需要人工审查")
            
            # 基于增长指标
            growth = self._analyze_growth_metrics()
            if growth.get("nodes_created_last_week", 0) < 3:
                recommendations.append("知识增长缓慢，建议增加学习活动")
            
            if not recommendations:
                recommendations.append("网络健康状态良好，继续保持当前策略")
            
            return recommendations
        except Exception as e:
            logger.error(f"_generate_recommendations failed: {e}")
            return ["无法生成建议：" + str(e)]
    
    def _count_trap_nodes(self) -> int:
        """统计陷阱节点数量"""
        try:
            count = self._conn.execute(
                """SELECT COUNT(*) as cnt
                   FROM knowledge_nodes kn
                   LEFT JOIN (
                       SELECT basis_point_id, COUNT(*) as incoming
                       FROM reasoning_lines
                       GROUP BY basis_point_id
                   ) inc ON kn.node_id = inc.basis_point_id
                   WHERE kn.node_id NOT LIKE 'MEM_CONV%'
                     AND kn.usage_count >= 3
                     AND inc.incoming >= 2
                     AND (kn.usage_success_count * 1.0 / kn.usage_count) < 0.5"""
            ).fetchone()['cnt']
            return count or 0
        except Exception:
            return 0
    
    def _get_health_status(self, score: float) -> str:
        """根据评分获取健康状态"""
        if score >= 80:
            return "excellent"
        elif score >= 60:
            return "good"
        elif score >= 40:
            return "warning"
        else:
            return "critical"
    
    def render_health_dashboard(self) -> str:
        """渲染健康仪表板（GP友好格式）"""
        report = self.generate_health_report()
        
        if "error" in report:
            return f"❌ 网络健康报告生成失败: {report['error']}"
        
        lines = []
        overall = report["overall_health"]
        
        # 整体状态
        status_emoji = {
            "excellent": "🟢",
            "good": "🟡", 
            "warning": "🟠",
            "critical": "🔴"
        }
        
        lines.append(f"📊 知识网络健康仪表板 {status_emoji.get(overall['status'], '⚪')}")
        lines.append(f"整体评分: {overall['score']}/100 ({overall['status']})")
        lines.append(f"节点总数: {overall['total_nodes']} (活跃: {overall['active_nodes']})")
        lines.append(f"连接总数: {overall['total_edges']} (连通比: {overall['connectivity_ratio']})")
        lines.append("")
        
        # 知识分布
        dist = report["knowledge_distribution"]
        lines.append("📈 知识分布:")
        for node_type, count in list(dist["by_type"].items())[:5]:
            lines.append(f"  {node_type}: {count}")
        lines.append("")
        
        # 连接健康
        conn = report["connection_health"]
        if conn.get("has_contradictions"):
            lines.append(f"⚠️ 发现 {conn['contradiction_count']} 个矛盾关系")
        lines.append(f"🔗 推理线: {conn['reasoning_lines']}")
        lines.append("")
        
        # 陷阱节点
        traps = report["trap_analysis"]
        if traps.get("has_traps"):
            lines.append(f"🚨 陷阱节点 ({traps['trap_count']} 个):")
            for trap in traps["trap_nodes"][:3]:
                lines.append(f"  • {trap['node_id']}: 入线{trap['incoming_count']}, 胜率{trap['win_rate']:.1%}")
            lines.append("")
        
        # 饱和区域
        saturation = report["saturation_zones"]
        if saturation.get("has_saturation"):
            lines.append(f"🔬 饱和区域 ({saturation['zone_count']} 个):")
            for zone in saturation["zones"][:3]:
                lines.append(f"  • {zone['area']}: {zone['virtual_point_count']} 个虚点")
            lines.append("")
        
        # 增长指标
        growth = report["growth_metrics"]
        lines.append("📊 增长指标:")
        lines.append(f"  本周新增: {growth['nodes_created_last_week']} 节点")
        lines.append(f"  本周验证: {growth['nodes_verified_last_week']} 节点")
        lines.append(f"  VOID任务: {growth['void_tasks_count']} 个")
        lines.append("")
        
        # 建议
        lines.append("💡 改进建议:")
        for rec in report["recommendations"][:3]:
            lines.append(f"  • {rec}")
        
        return "\n".join(lines)
