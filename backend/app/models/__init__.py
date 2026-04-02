"""
数据模型模块
"""

from .task import TaskManager, TaskStatus
from .project import Project, ProjectStatus, ProjectManager
from .debate import (
    AgentRole, AgentResponse, AgentThesis,
    CIOSynthesis, ConsensusScore, CrossExamination,
    DebateResult, DebateRound, DebateStatus,
    Direction, InvestmentFactor, Rebuttal,
)

__all__ = [
    'TaskManager', 'TaskStatus',
    'Project', 'ProjectStatus', 'ProjectManager',
    'AgentRole', 'AgentResponse', 'AgentThesis',
    'CIOSynthesis', 'ConsensusScore', 'CrossExamination',
    'DebateResult', 'DebateRound', 'DebateStatus',
    'Direction', 'InvestmentFactor', 'Rebuttal',
]
